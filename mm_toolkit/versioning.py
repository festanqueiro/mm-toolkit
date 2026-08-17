"""Semantic-version helpers used by the update check and release tooling."""

from __future__ import annotations

import re


_SEMANTIC_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def version_tuple(value: str) -> tuple[int, int, int] | None:
    """Return a comparable semantic version, accepting an optional ``v`` tag prefix."""
    match = _SEMANTIC_VERSION.fullmatch(value.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer_version(current: str, candidate: str) -> bool:
    """Return whether candidate is a valid semantic version newer than current."""
    current_version = version_tuple(current)
    candidate_version = version_tuple(candidate)
    return bool(
        current_version is not None
        and candidate_version is not None
        and candidate_version > current_version
    )
