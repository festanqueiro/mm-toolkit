from pathlib import Path

import numpy as np
import pytest
import cv2
from PIL import Image
import soundfile as sf

from media_tools_for_record_labels.core import (
    AUDIO_EXTENSIONS,
    RenderSettings,
    _load_artwork,
    convert_media,
    find_audio_files,
    format_timestamp,
    generate_videos,
    media_kind,
    parse_timestamp,
    resolve_output,
    safe_filename,
    validate_cover,
    validate_visual,
    validate_video,
)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("195", 195), ("03:15", 195), ("00:03:15", 195), ("1:02:03.5", 3723.5)],
)
def test_parse_timestamp(text: str, seconds: float) -> None:
    assert parse_timestamp(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "-1", "1:60", "00:01:60", "1:2:3:4"])
def test_parse_timestamp_rejects_invalid_values(text: str) -> None:
    with pytest.raises(ValueError):
        parse_timestamp(text)


def test_format_timestamp() -> None:
    assert format_timestamp(195) == "00:03:15"


def test_render_defaults_preserve_original_effect() -> None:
    settings = RenderSettings()
    assert settings.bass_effect is True
    assert settings.mute_original_video_audio is True
    assert settings.pre_drop == 2.0
    assert settings.duration == 60.0
    assert settings.size is None


def test_artwork_keeps_native_aspect_ratio_and_h264_dimensions(tmp_path: Path) -> None:
    portrait = tmp_path / "portrait.png"
    Image.new("RGB", (801, 1201), "magenta").save(portrait)
    artwork = _load_artwork(portrait, None)
    assert artwork.shape == (1200, 800, 3)


def test_find_audio_files_is_filtered_and_sorted(tmp_path: Path) -> None:
    (tmp_path / "B.mp3").touch()
    (tmp_path / "a.wav").touch()
    (tmp_path / "notes.txt").touch()
    assert [path.name for path in find_audio_files(tmp_path)] == ["a.wav", "B.mp3"]
    assert ".aiff" in AUDIO_EXTENSIONS


def test_find_audio_files_accepts_one_audio_file(tmp_path: Path) -> None:
    audio = tmp_path / "single.flac"
    audio.touch()
    unsupported = tmp_path / "notes.txt"
    unsupported.touch()
    assert find_audio_files(audio) == [audio]
    assert find_audio_files(unsupported) == []


def test_media_validation(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    Image.new("RGB", (8, 8), "blue").save(cover)
    video = tmp_path / "source.mp4"
    video.touch()
    assert validate_cover(cover)[0]
    assert validate_visual(cover)[0]
    assert validate_video(video)[0]
    assert not validate_video(tmp_path / "source.txt")[0]


def test_video_visual_is_readable(tmp_path: Path) -> None:
    visual = tmp_path / "visual.avi"
    writer = cv2.VideoWriter(str(visual), cv2.VideoWriter_fourcc(*"MJPG"), 12, (64, 48))
    assert writer.isOpened()
    writer.write(np.full((48, 64, 3), (20, 80, 180), dtype=np.uint8))
    writer.release()

    valid, message = validate_visual(visual)
    assert valid
    assert message == "Video ready."


def test_safe_filename_and_conflict_policies(tmp_path: Path) -> None:
    assert safe_filename('Artist: Track?/Name') == "Artist- Track--Name"
    existing = tmp_path / "video.mp4"
    existing.touch()
    assert resolve_output(existing, "skip") is None
    assert resolve_output(existing, "overwrite") == existing
    assert resolve_output(existing, "rename") == tmp_path / "video (2).mp4"


def test_artwork_output_profile_letterboxes_without_distortion(tmp_path: Path) -> None:
    artwork_path = tmp_path / "wide.png"
    Image.new("RGB", (400, 200), "magenta").save(artwork_path)
    artwork = _load_artwork(artwork_path, None, (108, 192))
    assert artwork.shape == (192, 108, 3)


def test_media_kind_detects_audio_and_video() -> None:
    assert media_kind("track.aiff") == "audio"
    assert media_kind("track.mp3") == "audio"
    assert media_kind("recording.mkv") == "video"
    assert media_kind("notes.txt") is None


def test_convert_audio_wav_to_flac(tmp_path: Path) -> None:
    source = tmp_path / "Source Audio.wav"
    samples = np.zeros(2205, dtype=np.float32)
    sf.write(source, samples, 44100)
    output_dir = tmp_path / "exports"
    results = convert_media([source], output_dir, "flac")
    assert results == [output_dir / "Source Audio.flac"]
    assert results[0].is_file()


def test_converter_rejects_unknown_audio_bitrate(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    source.touch()
    with pytest.raises(ValueError, match="Audio bitrate"):
        convert_media([source], tmp_path, "mp3", audio_bitrate="999k")


def test_promo_track_options_override_start_and_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "track.wav"
    source.touch()
    captured = {}

    def fake_render(source_path, _cover, _output, settings, _ffmpeg, _progress, _cancel, start_time):
        captured["source"] = source_path
        captured["start"] = start_time
        captured["duration"] = settings.duration

    monkeypatch.setattr("media_tools_for_record_labels.core.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr("media_tools_for_record_labels.core.render_track", fake_render)
    generate_videos(
        [source],
        tmp_path / "cover.png",
        tmp_path / "exports",
        track_options={source: (12.5, 34.0)},
    )
    assert captured == {"source": source, "start": 12.5, "duration": 34.0}
