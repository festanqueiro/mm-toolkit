"""Semantic-version helpers used by the update check and release tooling."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


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


def dev_build_label() -> str | None:
    """Return a local dev-build tag (short git commit, +dirty if uncommitted changes), or None.

    Only meaningful when running from a source checkout: PyInstaller-packaged
    builds (``sys.frozen``) always return None, so this never appears in a
    released build and never factors into the GitHub-release version check.
    """
    if getattr(sys, "frozen", False):
        return None
    repo_root = Path(__file__).resolve().parent.parent
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if not commit:
        return None
    return f"{commit}+dirty" if dirty else commit
