import re

from mm_toolkit import __version__
from mm_toolkit.versioning import is_newer_version, version_tuple


def test_version_is_semantic() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_version_tuple_accepts_release_tag() -> None:
    assert version_tuple("v1.2.3") == (1, 2, 3)


def test_update_check_only_accepts_newer_semantic_version() -> None:
    assert is_newer_version("1.0.0", "v1.0.1")
    assert not is_newer_version("1.0.0", "v1.0.0")
    assert not is_newer_version("1.0.0", "release-12")
