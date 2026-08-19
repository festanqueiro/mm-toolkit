"""Platform-neutral promo-video generation engine."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable

import cv2
import imageio_ffmpeg
import numpy as np
import soundfile as sf
from moviepy import AudioFileClip, CompositeAudioClip, VideoClip, VideoFileClip
from moviepy.audio.fx import AudioFadeIn, AudioFadeOut, AudioLoop
from moviepy.video.fx import FadeIn, FadeOut
from PIL import Image, ImageOps
from proglog import ProgressBarLogger
from scipy.signal import butter, sosfiltfilt

from mm_toolkit.effects import (
    EffectSettings,
    apply_effect_chain,
    build_background_frame,
    fit_overlay_frame,
    load_overlay_image,
)

AUDIO_EXTENSIONS = {".wav", ".wave", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".aac", ".ogg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
AUDIO_OUTPUT_FORMATS = ("mp3", "wav", "aiff", "flac", "m4a", "aac", "ogg")
VIDEO_OUTPUT_FORMATS = ("mp4", "mov", "mkv", "avi", "webm")

BASS_CUTOFF_HZ = 150
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
    mute_original_video_audio: bool = True
    audio_fade: bool = True
    video_fade: bool = True
    output_size: tuple[int, int] | None = None
    preset: str = "medium"
    crf: int = 18
    audio_bitrate: str = "320k"
    effects: EffectSettings = EffectSettings()


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
        return False, "The source video could not be found."
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        return False, "The selected file is not a supported video."
    return True, "Source video ready."


def validate_media_source(path: str | Path) -> tuple[bool, str]:
    source = Path(path).expanduser()
    if not source.is_file():
        return False, "The source media could not be found."
    kind = media_kind(source)
    if kind is None:
        return False, "The selected file is not supported audio or video."
    return True, f"Source {kind} ready."


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
        return False, "The image could not be found."
    if cover.suffix.lower() not in IMAGE_EXTENSIONS:
        return False, "The selected file is not a supported image."
    try:
        with Image.open(cover) as image:
            image.verify()
    except Exception:
        return False, "The selected artwork could not be read."
    return True, "Artwork ready."


def validate_visual(path: str | Path) -> tuple[bool, str]:
    visual = Path(path).expanduser()
    if visual.suffix.lower() in IMAGE_EXTENSIONS:
        valid, message = validate_cover(visual)
        return valid, "Image ready." if valid else message.replace("Artwork", "Image")
    if visual.suffix.lower() in VIDEO_EXTENSIONS:
        if not visual.is_file():
            return False, "The video could not be found."
        capture = cv2.VideoCapture(os.fspath(visual))
        readable, _frame = capture.read()
        capture.release()
        return (True, "Video ready.") if readable else (False, "The selected video could not be read.")
    return False, "The selected file cannot be used as an image or video."


def media_kind(path: str | Path) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return None


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


def detect_drop_starts(
    sources: Iterable[Path],
    seconds_before: float = 2.0,
    callback: ProgressCallback | None = None,
    should_cancel: CancelCheck = lambda: False,
) -> dict[Path, float]:
    """Detect a suggested promo start for each source without blocking the UI."""
    files = list(sources)
    ffmpeg = require_ffmpeg()
    starts: dict[Path, float] = {}
    with tempfile.TemporaryDirectory(prefix="promo-drop-analysis-") as scratch:
        scratch_path = Path(scratch)
        for index, source in enumerate(files):
            if should_cancel():
                raise CancelledError("Drop analysis cancelled.")
            if callback:
                callback(round(index / max(1, len(files)) * 100), f"Detecting drop in {source.name}")
            normalised = scratch_path / f"source-{index}.wav"
            _normalise_audio(source, normalised, ffmpeg)
            starts[source] = max(0.0, detect_drop_time(normalised) - seconds_before)
    if callback:
        callback(100, "Drop detection finished")
    return starts


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


def _load_artwork(
    cover_path: Path,
    size: int | None,
    output_size: tuple[int, int] | None = None,
    canvas_background: np.ndarray | None = None,
) -> np.ndarray:
    with Image.open(cover_path) as image:
        artwork = image.convert("RGB")
        if size is not None:
            artwork = artwork.resize((size, size), Image.Resampling.LANCZOS)
        elif output_size is not None:
            width, height = output_size
            fitted = ImageOps.contain(artwork, (width, height), Image.Resampling.LANCZOS)
            canvas = (
                Image.fromarray(canvas_background)
                if canvas_background is not None
                else Image.new("RGB", (width, height), (25, 25, 29))
            )
            canvas.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
            artwork = canvas
        elif artwork.width % 2 or artwork.height % 2:
            # H.264 yuv420p requires even dimensions. At most one edge pixel is removed.
            artwork = artwork.crop((0, 0, artwork.width - artwork.width % 2, artwork.height - artwork.height % 2))
        return np.array(artwork, dtype=np.uint8)


def _fit_visual_frame(
    frame: np.ndarray,
    size: int | None,
    output_size: tuple[int, int] | None,
    canvas_background: np.ndarray | None = None,
) -> np.ndarray:
    image = Image.fromarray(np.asarray(frame, dtype=np.uint8)).convert("RGB")
    if size is not None:
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    elif output_size is not None:
        width, height = output_size
        fitted = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
        canvas = (
            Image.fromarray(canvas_background)
            if canvas_background is not None
            else Image.new("RGB", (width, height), (25, 25, 29))
        )
        canvas.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
        image = canvas
    elif image.width % 2 or image.height % 2:
        image = image.crop((0, 0, image.width - image.width % 2, image.height - image.height % 2))
    return np.array(image, dtype=np.uint8)


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
    start_time: float | None = None,
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
        if start_time is None:
            drop_time = detect_drop_time(normalised)
            start_time = max(0.0, drop_time - settings.pre_drop)
        _extract_audio(normalised, max(0.0, start_time), settings.duration, trimmed, ffmpeg)
        actual_duration = min(settings.duration, sf.info(trimmed).duration)
        if actual_duration <= 0:
            raise RuntimeError(f"{source.name} contains no usable audio.")
        envelope = (
            _build_bass_envelope(trimmed, settings.fps, actual_duration)
            if settings.effects.bass_blur.enabled
            else None
        )
        visual_clip: VideoFileClip | None = None
        if cover_path.suffix.lower() in VIDEO_EXTENSIONS:
            visual_clip = VideoFileClip(
                os.fspath(cover_path),
                audio=not settings.mute_original_video_audio,
            )
            if visual_clip.duration <= 0:
                raise RuntimeError(f"{cover_path.name} contains no usable video.")
            native_size = visual_clip.size
            background = None
        else:
            with Image.open(cover_path) as probe:
                native_size = probe.size

        if settings.output_size is not None:
            canvas_size = settings.output_size
        elif settings.size is not None:
            canvas_size = (settings.size, settings.size)
        else:
            width, height = native_size
            canvas_size = (width - width % 2, height - height % 2)
        effect_background = build_background_frame(canvas_size, settings.effects.background)

        if visual_clip is None:
            background = _load_artwork(cover_path, settings.size, settings.output_size, effect_background)

        overlay_settings = settings.effects.overlay
        overlay_clip: VideoFileClip | None = None
        overlay_image: np.ndarray | None = None
        if overlay_settings.enabled and overlay_settings.media_path:
            overlay_path = Path(overlay_settings.media_path)
            if overlay_path.suffix.lower() in VIDEO_EXTENSIONS:
                overlay_clip = VideoFileClip(os.fspath(overlay_path), audio=False)
            elif overlay_path.is_file():
                overlay_image = load_overlay_image(overlay_path, canvas_size)

        def overlay_frame_at(time: float) -> np.ndarray | None:
            if overlay_clip is not None:
                frame = overlay_clip.get_frame(time % overlay_clip.duration)
                rgba = np.dstack([frame, np.full(frame.shape[:2], 255, dtype=np.uint8)])
                return fit_overlay_frame(rgba, canvas_size)
            return overlay_image

        def visual_frame(time: float) -> np.ndarray:
            if visual_clip is None:
                assert background is not None
                return background
            frame = visual_clip.get_frame(time % visual_clip.duration)
            return _fit_visual_frame(frame, settings.size, settings.output_size, effect_background)

        def make_frame(time: float) -> np.ndarray:
            if should_cancel():
                raise CancelledError("Generation cancelled.")
            frame = visual_frame(time)
            bass_strength = None
            if envelope is not None:
                index = min(int(time * settings.fps), len(envelope) - 1)
                bass_strength = float(envelope[index])
            overlay = overlay_frame_at(time) if overlay_settings.enabled else None
            return apply_effect_chain(frame, time, settings.effects, effect_background, bass_strength, overlay)

        fade = min(settings.fade, actual_duration / 2)
        music_audio = AudioFileClip(os.fspath(trimmed))
        if settings.audio_fade:
            music_audio = AudioFadeOut(fade).apply(AudioFadeIn(fade).apply(music_audio))
        audio = music_audio
        if visual_clip is not None and visual_clip.audio is not None and not settings.mute_original_video_audio:
            original_audio = AudioLoop(duration=actual_duration).apply(visual_clip.audio)
            audio = CompositeAudioClip([music_audio, original_audio]).with_duration(actual_duration)
        video = VideoClip(make_frame, duration=actual_duration)
        if settings.video_fade:
            video = FadeOut(fade).apply(FadeIn(fade).apply(video))
        video = video.with_audio(audio)
        # MoviePy otherwise derives a relative temporary-audio filename from the
        # output name. A packaged macOS app can start in its read-only bundle,
        # causing FFmpeg to fail with "Read-only file system" / "Broken pipe".
        temp_audio = scratch_path / "moviepy-audio.m4a"
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
                temp_audiofile=os.fspath(temp_audio),
                remove_temp=True,
                ffmpeg_params=["-pix_fmt", "yuv420p", "-crf", str(settings.crf)],
                logger=_MoviePyLogger(progress),
            )
        finally:
            video.close()
            audio.close()
            if audio is not music_audio:
                music_audio.close()
            if visual_clip is not None:
                visual_clip.close()
            if overlay_clip is not None:
                overlay_clip.close()
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
    track_options: dict[Path, tuple[float | None, float]] | None = None,
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
            start_time, duration = (track_options or {}).get(source, (None, settings.duration))
            track_settings = replace(settings, duration=duration)
            render_track(source, cover_path, output, track_settings, ffmpeg, track_progress, should_cancel, start_time)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        outputs.append(output)
    if callback:
        callback(100, f"Finished {len(outputs)} video{'s' if len(outputs) != 1 else ''}")
    return outputs


def cut_media_clips(
    source: Path,
    clips: Iterable[ClipRequest],
    output_dir: Path,
    callback: ProgressCallback | None = None,
    naming_template: str = "{source} - {title}",
    conflict_policy: str = "rename",
    should_cancel: CancelCheck = lambda: False,
) -> list[Path]:
    """Create accurately timed audio or broadly compatible H.264/AAC video clips."""
    requests = list(clips)
    if not requests:
        raise ValueError("Add at least one clip.")
    ffmpeg = require_ffmpeg()
    kind = media_kind(source)
    if kind is None or not source.is_file():
        raise ValueError("Choose a supported audio or video source.")
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
        audio_format = {".wave": "wav", ".aif": "aiff"}.get(source.suffix.lower(), source.suffix.lower().lstrip("."))
        output_format = "mp4" if kind == "video" else audio_format
        output = resolve_output(output_dir / f"{safe_filename(output_name)}.{output_format}", conflict_policy)
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
        ]
        if kind == "video":
            command.extend([
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "fast",
                "-crf", "18", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart",
                "-pix_fmt", "yuv420p",
            ])
        else:
            audio_args = {
                "mp3": ["-vn", "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "320k"],
                "wav": ["-vn", "-map", "0:a:0", "-c:a", "pcm_s24le"],
                "aiff": ["-vn", "-map", "0:a:0", "-c:a", "pcm_s24be"],
                "flac": ["-vn", "-map", "0:a:0", "-c:a", "flac"],
                "m4a": ["-vn", "-map", "0:a:0", "-c:a", "aac", "-b:a", "320k"],
                "aac": ["-vn", "-map", "0:a:0", "-c:a", "aac", "-b:a", "320k"],
                "ogg": ["-vn", "-map", "0:a:0", "-c:a", "libvorbis", "-q:a", "8"],
            }
            command.extend(audio_args[output_format])
        command.extend(["-progress", "pipe:1", "-nostats", os.fspath(output)])
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


# Backward-compatible public name for integrations using the original video-only API.
cut_video_clips = cut_media_clips


def convert_media(
    sources: Iterable[Path],
    output_dir: Path,
    output_format: str,
    callback: ProgressCallback | None = None,
    conflict_policy: str = "rename",
    should_cancel: CancelCheck = lambda: False,
    audio_bitrate: str = "320k",
) -> list[Path]:
    """Batch-convert audio or video files with FFmpeg."""
    files = list(sources)
    if not files:
        raise ValueError("Choose at least one media file.")
    kinds = {media_kind(path) for path in files}
    if None in kinds or len(kinds) != 1:
        raise ValueError("Choose either audio files or video files, not a mixed selection.")
    kind = kinds.pop()
    allowed = AUDIO_OUTPUT_FORMATS if kind == "audio" else VIDEO_OUTPUT_FORMATS
    output_format = output_format.lower().lstrip(".")
    if output_format not in allowed:
        raise ValueError(f"{output_format.upper()} is not a supported {kind} output format.")
    if audio_bitrate not in {"128k", "192k", "256k", "320k"}:
        raise ValueError("Audio bitrate must be 128k, 192k, 256k, or 320k.")
    ffmpeg = require_ffmpeg()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    audio_args = {
        "mp3": ["-vn", "-c:a", "libmp3lame", "-b:a", audio_bitrate],
        "wav": ["-vn", "-c:a", "pcm_s24le"],
        "aiff": ["-vn", "-c:a", "pcm_s24be"],
        "flac": ["-vn", "-c:a", "flac"],
        "m4a": ["-vn", "-c:a", "aac", "-b:a", "256k"],
        "aac": ["-vn", "-c:a", "aac", "-b:a", "256k"],
        "ogg": ["-vn", "-c:a", "libvorbis", "-q:a", "6"],
    }
    video_args = {
        "mp4": ["-c:v", "libx264", "-crf", "18", "-preset", "fast", "-c:a", "aac", "-b:a", "256k", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        "mov": ["-c:v", "libx264", "-crf", "18", "-preset", "fast", "-c:a", "aac", "-b:a", "256k", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        "mkv": ["-c:v", "libx264", "-crf", "18", "-preset", "fast", "-c:a", "aac", "-b:a", "256k", "-pix_fmt", "yuv420p"],
        "avi": ["-c:v", "mpeg4", "-q:v", "3", "-c:a", "libmp3lame", "-q:a", "2"],
        "webm": ["-c:v", "libvpx-vp9", "-crf", "28", "-b:v", "0", "-c:a", "libopus", "-b:a", "192k"],
    }
    for index, source in enumerate(files):
        if should_cancel():
            raise CancelledError("Conversion cancelled.")
        output = resolve_output(output_dir / f"{source.stem}.{output_format}", conflict_policy)
        if output is None:
            continue
        if callback:
            callback(round(index / len(files) * 100), f"Converting {source.name} ({index + 1} of {len(files)})")
        command = [ffmpeg, "-y", "-v", "error", "-i", os.fspath(source)]
        command.extend(audio_args[output_format] if kind == "audio" else video_args[output_format])
        command.append(os.fspath(output))
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        while process.poll() is None:
            if should_cancel():
                process.terminate()
                process.wait()
                output.unlink(missing_ok=True)
                raise CancelledError("Conversion cancelled.")
            time.sleep(0.1)
        stderr = process.stderr.read() if process.stderr else ""
        if process.returncode != 0:
            output.unlink(missing_ok=True)
            raise RuntimeError(stderr.strip() or f"FFmpeg failed while converting {source.name}.")
        outputs.append(output)
    if callback:
        callback(100, f"Finished {len(outputs)} conversion{'s' if len(outputs) != 1 else ''}")
    return outputs
