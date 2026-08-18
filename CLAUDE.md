# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev setup
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt   # installs requirements.txt too

# Run the app
python -m mm_toolkit

# Tests (fast, no Qt/GUI dependency)
python -m pytest -q
python -m pytest tests/test_core.py::test_parse_timestamp -q   # single test
python -m pytest -k drop_time -q                               # by keyword

# Package the desktop app (PyInstaller)
./scripts/build_macos.sh          # macOS only -> dist/MM Toolkit.app
./scripts/build_windows.ps1       # Windows only -> dist/MM Toolkit/
```

FFmpeg must be resolvable at runtime: a system install (`brew install ffmpeg`) is used first, falling back to the bundled `imageio-ffmpeg` binary (see `core.require_ffmpeg`). PyInstaller must build on the target OS — a Windows executable cannot be produced from macOS.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `<type>: <description>`, e.g. `feat: add drop detection to Media Cutter`, `fix: correct bundled_asset path depth`, `docs: update README build steps`. Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `build`. Scope the subject to what actually changed; keep it imperative and under ~72 chars.

## Architecture

The codebase is a strict two-layer split:

- **`mm_toolkit/core.py`** — platform-neutral media engine. Pure functions and frozen dataclasses (`RenderSettings`, `ClipRequest`) with no Qt dependency; shells out to FFmpeg via `subprocess` and uses moviepy/opencv/numpy/scipy for the promo-video render pipeline (bass-driven radial blur/zoom synced to an audio envelope, drop detection via a low-pass RMS scan). This is the only module covered by `tests/`.
- **`mm_toolkit/app.py`** — a two-line re-export shim (`from mm_toolkit.ui.main_window import main`) kept for backwards-compatible imports/entry points.
- **`mm_toolkit/ui/`** — the PySide6 GUI, split into one module per concern: `style.py` (shared style constants + icon helpers), `helpers.py` (shared dialog/layout helpers), `widgets.py` (shared `PathRow` widget), one file per tab — `clips_tab.py` (Media Cutter, `ClipsTab`), `converter_tab.py` (Media Converter, `ConverterTab`), `settings_tab.py` (`SettingsTab`), `about_tab.py` (`AboutTab`), `history_tab.py` (`HistoryTab`), `video_generator.py` (Video Generator, `VideoGeneratorTab`) — and `main_window.py` (`MainWindow` + `main()`, assembles all tabs and owns cross-tab coordination like history and settings propagation). Each tab's `QThread` worker subclass (`RenderWorker`, `DropDetectionWorker`, `ClipWorker`, `ConverterWorker`) lives alongside its tab in the same file rather than in a shared location. Long-running `core.py` calls are wrapped in these workers, which emit progress signals back to the UI thread — never call `core.py`'s FFmpeg/moviepy functions directly from a UI callback. Widgets use `palette(...)` Qt stylesheet references rather than hardcoded colors so the UI follows the OS light/dark theme.

Entry points: `python -m mm_toolkit` runs `mm_toolkit/__main__.py` → `app.main()` for development. The packaged app instead runs `run_app.py`, a separate PyInstaller-friendly entry point referenced by `MMToolkit.spec` (`Analysis([... "run_app.py"])`).

`mm_toolkit.__version__` (in `__init__.py`) is the single source of truth for the app version: it's baked into the PyInstaller bundle's `Info.plist` (`MMToolkit.spec`), drives the in-app update check (`versioning.is_newer_version`), and becomes the release tag/package filenames in `.github/workflows/main-release.yml`. Bump it before publishing a release — see Versioning below.

## Versioning

Every push to `main` (i.e. every release) bumps `mm_toolkit.__version__`: **patch** by default (`1.0.0` → `1.0.1`), **minor** or **major** only when explicitly requested by the user for that release (minor: `1.0.0` → `1.1.0`, resetting patch to 0; major: `1.0.0` → `2.0.0`, resetting minor/patch to 0).

### Release flow

- `develop-ci.yml`: on PRs/pushes to `develop` — secret scan, `pytest`, then a matrix build (macOS + Windows) to verify the PyInstaller bundle produces `dist/MM Toolkit.app` / `dist/MM Toolkit/MM Toolkit.exe`.
- `main-release.yml`: on push to `main` — builds, code-signs and notarizes the macOS app (Apple secrets) and signs the Windows exe/installer (`scripts/windows-installer.iss`, Inno Setup) when the relevant certificate secrets are configured, then publishes a GitHub Release tagged `v<mm_toolkit.__version__>` with the macOS ZIP/DMG and Windows ZIP/installer attached.

## Codex config detected

An OpenAI Codex config was found at `~/.codex/config.toml`. Reply `/import` to scan it for importable items (MCP servers, slash commands, subagents, skills, instructions), then `/import --yes=<digest>` to apply the user-level ones.
