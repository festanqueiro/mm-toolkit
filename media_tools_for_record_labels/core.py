"""Platform-neutral promo-video generation engine."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import cv2
import imageio_ffmpeg
import numpy as np
import soundfile as sf
from moviepy import AudioFileClip, VideoClip
from moviepy.audio.fx import AudioFadeIn, AudioFadeOut
from moviepy.video.fx import FadeIn, FadeOut
from PIL import Image, ImageOps
from proglog import ProgressBarLogger
from scipy.signal import butter, sosfiltfilt

AUDIO_EXTENSIONS = {".wav", ".wave", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".aac", ".ogg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}

BASS_CUTOFF_HZ = 150
BLUR_SAMPLES = 6
MAX_ZOOM = 0.10
STRENGTH_FLOOR = 0.05
ENVELOPE_POWER = 1.6
DROP_SEARCH_BIN_S = 0.5
DROP_SEARCH_SKIP_S = 20
DROP_WINDOW_S = 8

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


class CancelledError(RuntimeError):
    """Raised when the user cancels an active media job."""


@dataclass(frozen=True)
class RenderSettings:
    size: int | None = None
    fps: int = 24
    duration: float = 60.0
    pre_drop: float = 2.0
    fade: float = 0.5
    bass_effect: bool = True
    output_size: tuple[int, int] | None = None
    preset: str = "medium"
    crf: int = 18
    audio_bitrate: str = "256k"


@dataclass(frozen=True)
class ClipRequest:
    start: float
    duration: float
    title: str = ""


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value).strip(" .")
    return cleaned or "Untitled"


def resolve_output(path: Path, conflict_policy: str) -> Path | None:
    if not path.exists() or conflict_policy == "overwrite":
        return path
    if conflict_policy == "skip":
        return None
    if conflict_policy != "rename":
        raise ValueError(f"Unknown conflict policy: {conflict_policy}")
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def parse_timestamp(value: str) -> float:
    """Parse seconds, MM:SS, or HH:MM:SS into seconds."""
    text = value.strip()
    if not text:
        raise ValueError("Timestamp cannot be empty.")
    parts = text.split(":")
    if len(parts) > 3 or any(not re.fullmatch(r"\d+(?:\.\d+)?", part.strip()) for part in parts):
        raise ValueError(f"Invalid timestamp: {value}")
    numbers = [float(part) for part in parts]
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
    elif len(numbers) == 2:
        hours, minutes, seconds = 0.0, numbers[0], numbers[1]
    else:
        hours, minutes, seconds = 0.0, 0.0, numbers[0]
    if minutes >= 60 or (seconds >= 60 and len(numbers) > 1):
        raise ValueError(f"Invalid timestamp: {value}")
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def validate_video(path: str | Path) -> tuple[bool, str]:
    source = Path(path).expanduser()
    if not source.is_file():
        return False, "Choose a source video."
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        return False, "Choose an MP4, MOV, M4V, MKV, AVI, or WebM video."
    return True, "Source video ready."


def find_audio_files(folder: str | Path) -> list[Path]:
    path = Path(folder).expanduser()
    if path.is_file():
        return [path] if path.suffix.lower() in AUDIO_EXTENSIONS else []
    if not path.is_dir():
        return []
    return sorted(
        (item for item in path.iterdir() if item.is_file() and item.suffix.lower() in AUDIO_EXTENSIONS),
        key=lambda item: item.name.casefold(),
    )


def validate_cover(path: str | Path) -> tuple[bool, str]:
    cover = Path(path).expanduser()
    if not cover.is_file():
        return False, "Choose an artwork image."
    if cover.suffix.lower() not in IMAGE_EXTENSIONS:
        return False, "Artwork must be PNG, JPG, WebP, or TIFF."
    try:
        with Image.open(cover) as image:
            image.verify()
    except Exception:
        return False, "The selected artwork could not be read."
    return True, "Artwork ready."


def require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    for candidate in (Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return os.fspath(candidate)
    try:
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).is_file():
            return bundled
    except Exception as exc:
        raise RuntimeError("FFmpeg could not be located by the application.") from exc
    raise RuntimeError("FFmpeg could not be located by the application.")


def _read_mono(path: Path) -> tuple[np.ndarray, int]:
    samples, sample_rate = sf.read(path, always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return samples, sample_rate


def detect_drop_time(wav_path: Path) -> float:
    samples, sample_rate = _read_mono(wav_path)
    nyquist = sample_rate / 2
    cutoff = min(BASS_CUTOFF_HZ / nyquist, 0.99)
    bass = sosfiltfilt(butter(4, cutoff, btype="low", output="sos"), samples)
    window = max(1, int(DROP_SEARCH_BIN_S * sample_rate))
    count = len(bass) // window
    if count < 2:
        return 0.0
    rms = np.sqrt(np.mean(bass[: count * window].reshape(count, window) ** 2, axis=1))
    scan_window = max(1, int(DROP_WINDOW_S / DROP_SEARCH_BIN_S))
    start = min(int(DROP_SEARCH_SKIP_S / DROP_SEARCH_BIN_S), max(0, count - 1))
    best_index, best_score = start, float("-inf")
    for index in range(start, max(start + 1, count - scan_window)):
        before = rms[max(0, index - scan_window) : index]
        after = rms[index : index + scan_window]
        score = float(after.mean() - (before.mean() if len(before) else 0.0))
        if score > best_score:
            best_index, best_score = index, score
    return best_index * DROP_SEARCH_BIN_S


def _build_bass_envelope(wav_path: Path, fps: int, duration: float) -> np.ndarray:
    samples, sample_rate = _read_mono(wav_path)
    cutoff = min(BASS_CUTOFF_HZ / (sample_rate / 2), 0.99)
    bass = sosfiltfilt(butter(4, cutoff, btype="low", output="sos"), samples)
    frame_count = max(1, int(duration * fps))
    window = max(1, int(sample_rate / fps))
    envelope = np.zeros(frame_count)
    for index in range(frame_count):
        segment = bass[index * window : (index + 1) * window]
        if len(segment):
            envelope[index] = np.sqrt(np.mean(segment**2))
    peak = envelope.max()
    if peak > 0:
        envelope /= peak
    return np.clip(envelope, 0.0, 1.0) ** ENVELOPE_POWER


def _radial_blur(image: np.ndarray, strength: float) -> np.ndarray:
    if strength <= STRENGTH_FLOOR:
        return image
    height, width = image.shape[:2]
    accumulator = np.zeros_like(image, dtype=np.float32)
    for index in range(1, BLUR_SAMPLES + 1):
        zoom = 1.0 + MAX_ZOOM * strength * index / BLUR_SAMPLES
        resized = cv2.resize(
            image,
            (int(round(width * zoom)), int(round(height * zoom))),
            interpolation=cv2.INTER_LINEAR,
        )
        y = (resized.shape[0] - height) // 2
        x = (resized.shape[1] - width) // 2
        accumulator += resized[y : y + height, x : x + width].astype(np.float32)
    return (accumulator / BLUR_SAMPLES).astype(np.uint8)


def _load_artwork(
    cover_path: Path,
    size: int | None,
    output_size: tuple[int, int] | None = None,
) -> np.ndarray:
    with Image.open(cover_path) as image:
        artwork = image.convert("RGB")
        if size is not None:
            artwork = artwork.resize((size, size), Image.Resampling.LANCZOS)
        elif output_size is not None:
            width, height = output_size
            fitted = ImageOps.contain(artwork, (width, height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (width, height), (25, 25, 29))
            canvas.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
            artwork = canvas
        elif artwork.width % 2 or artwork.height % 2:
            # H.264 yuv420p requires even dimensions. At most one edge pixel is removed.
            artwork = artwork.crop((0, 0, artwork.width - artwork.width % 2, artwork.height - artwork.height % 2))
        return np.array(artwork, dtype=np.uint8)


class _MoviePyLogger(ProgressBarLogger):
    def __init__(self, callback: Callable[[float], None]):
        super().__init__()
        self.progress_callback = callback

    def bars_callback(self, bar, attr, value, old_value=None):  # noqa: ANN001
        if bar != "frame_index" or attr != "index":
            return
        total = self.bars.get(bar, {}).get("total") or 1
        self.progress_callback(min(1.0, value / total))


def _normalise_audio(source: Path, destination: Path, ffmpeg: str) -> None:
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", os.fspath(source), "-ac", "2", "-c:a", "pcm_s16le", os.fspath(destination)],
        check=True,
        capture_output=True,
    )


def _extract_audio(source: Path, start: float, duration: float, destination: Path, ffmpeg: str) -> None:
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-ss", str(start), "-i", os.fspath(source), "-t", str(duration), "-c:a", "pcm_s16le", os.fspath(destination)],
        check=True,
        capture_output=True,
    )


def render_track(
    source: Path,
    cover_path: Path,
    output_path: Path,
    settings: RenderSettings,
    ffmpeg: str,
    progress: Callable[[float], None],
    should_cancel: CancelCheck = lambda: False,
) -> None:
    with tempfile.TemporaryDirectory(prefix="promo-video-") as scratch:
        scratch_path = Path(scratch)
        normalised = scratch_path / "source.wav"
        trimmed = scratch_path / "snippet.wav"
        if should_cancel():
            raise CancelledError("Generation cancelled.")
        _normalise_audio(source, normalised, ffmpeg)
        if should_cancel():
            raise CancelledError("Generation cancelled.")
        drop_time = detect_drop_time(normalised)
        _extract_audio(normalised, max(0.0, drop_time - settings.pre_drop), settings.duration, trimmed, ffmpeg)
        actual_duration = min(settings.duration, sf.info(trimmed).duration)
        if actual_duration <= 0:
            raise RuntimeError(f"{source.name} contains no usable audio.")
        envelope = (
            _build_bass_envelope(trimmed, settings.fps, actual_duration)
            if settings.bass_effect
            else None
        )
        background = _load_artwork(cover_path, settings.size, settings.output_size)

        def make_frame(time: float) -> np.ndarray:
            if should_cancel():
                raise CancelledError("Generation cancelled.")
            if envelope is None:
                return background
            index = min(int(time * settings.fps), len(envelope) - 1)
            return _radial_blur(background, float(envelope[index]))

        fade = min(settings.fade, actual_duration / 2)
        audio = AudioFadeOut(fade).apply(AudioFadeIn(fade).apply(AudioFileClip(os.fspath(trimmed))))
        video = VideoClip(make_frame, duration=actual_duration)
        video = FadeOut(fade).apply(FadeIn(fade).apply(video)).with_audio(audio)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            video.write_videofile(
                os.fspath(output_path),
                fps=settings.fps,
                codec="libx264",
                audio_codec="aac",
                audio_bitrate=settings.audio_bitrate,
                preset=settings.preset,
                threads=max(1, min(4, os.cpu_count() or 1)),
                ffmpeg_params=["-pix_fmt", "yuv420p", "-crf", str(settings.crf)],
                logger=_MoviePyLogger(progress),
            )
        finally:
            audio.close()
            video.close()
            if should_cancel():
                output_path.unlink(missing_ok=True)


def generate_videos(
    audio_files: Iterable[Path],
    cover_path: Path,
    output_dir: Path,
    settings: RenderSettings = RenderSettings(),
    callback: ProgressCallback | None = None,
    naming_template: str = "{track} - Promo Snippet",
    conflict_policy: str = "rename",
    should_cancel: CancelCheck = lambda: False,
) -> list[Path]:
    files = list(audio_files)
    if not files:
        raise ValueError("No audio files were provided.")
    ffmpeg = require_ffmpeg()
    outputs: list[Path] = []
    for track_index, source in enumerate(files):
        if should_cancel():
            raise CancelledError("Generation cancelled.")
        if callback:
            callback(round(track_index / len(files) * 100), f"Analysing {source.name}")
        try:
            output_name = naming_template.format(track=source.stem, number=track_index + 1)
        except (KeyError, ValueError) as exc:
            raise ValueError("Invalid promo naming template. Use {track} and optionally {number}.") from exc
        output = resolve_output(output_dir / f"{safe_filename(output_name)}.mp4", conflict_policy)
        if output is None:
            continue

        def track_progress(fraction: float, index: int = track_index, name: str = source.name) -> None:
            overall = round((index + fraction) / len(files) * 100)
            if callback:
                callback(overall, f"Rendering {name}")

        try:
            render_track(source, cover_path, output, settings, ffmpeg, track_progress, should_cancel)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        outputs.append(output)
    if callback:
        callback(100, f"Finished {len(outputs)} video{'s' if len(outputs) != 1 else ''}")
    return outputs


def cut_video_clips(
    source: Path,
    clips: Iterable[ClipRequest],
    output_dir: Path,
    callback: ProgressCallback | None = None,
    naming_template: str = "{source} - {title}",
    conflict_policy: str = "rename",
    should_cancel: CancelCheck = lambda: False,
) -> list[Path]:
    """Create accurately timed, broadly compatible H.264/AAC clips."""
    requests = list(clips)
    if not requests:
        raise ValueError("Add at least one clip.")
    ffmpeg = require_ffmpeg()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index, clip in enumerate(requests):
        if should_cancel():
            raise CancelledError("Clip creation cancelled.")
        if clip.start < 0 or clip.duration <= 0:
            raise ValueError(f"Clip {index + 1} has an invalid start or duration.")
        title = clip.title.strip() or f"Clip {index + 1:02d}"
        try:
            output_name = naming_template.format(source=source.stem, title=title, number=index + 1)
        except (KeyError, ValueError) as exc:
            raise ValueError("Invalid clip naming template. Use {source}, {title}, and {number}.") from exc
        output = resolve_output(output_dir / f"{safe_filename(output_name)}.mp4", conflict_policy)
        if output is None:
            continue
        command = [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-ss",
            str(clip.start),
            "-i",
            os.fspath(source),
            "-t",
            str(clip.duration),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "256k",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            "-progress",
            "pipe:1",
            "-nostats",
            os.fspath(output),
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            if should_cancel():
                process.terminate()
                process.wait()
                output.unlink(missing_ok=True)
                raise CancelledError("Clip creation cancelled.")
            key, _, value = line.strip().partition("=")
            if key in {"out_time_us", "out_time_ms"}:
                try:
                    fraction = min(1.0, int(value) / 1_000_000 / clip.duration)
                    percent = round((index + fraction) / len(requests) * 100)
                    if callback:
                        callback(percent, f"Creating clip {index + 1} of {len(requests)}")
                except ValueError:
                    pass
        stderr = process.stderr.read() if process.stderr else ""
        if process.wait() != 0:
            output.unlink(missing_ok=True)
            raise RuntimeError(stderr.strip() or f"FFmpeg failed while creating clip {index + 1}.")
        outputs.append(output)
    if callback:
        callback(100, f"Finished {len(outputs)} clip{'s' if len(outputs) != 1 else ''}")
    return outputs
