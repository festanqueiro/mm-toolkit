import re

from mm_toolkit import __version__


def test_version_is_semantic() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_first_public_version() -> None:
    assert __version__ == "1.0.0"
