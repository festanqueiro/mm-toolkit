from pathlib import Path

import pytest
from PIL import Image

from media_tools_for_record_labels.core import (
    AUDIO_EXTENSIONS,
    RenderSettings,
    _load_artwork,
    find_audio_files,
    format_timestamp,
    parse_timestamp,
    validate_cover,
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


def test_media_validation(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    Image.new("RGB", (8, 8), "blue").save(cover)
    video = tmp_path / "source.mp4"
    video.touch()
    assert validate_cover(cover)[0]
    assert validate_video(video)[0]
    assert not validate_video(tmp_path / "source.txt")[0]
