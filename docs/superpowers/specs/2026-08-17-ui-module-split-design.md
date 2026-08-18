# Design: Split `mm_toolkit/app.py` into a `ui/` package

## Context

`mm_toolkit/app.py` is a single 2,333-line file containing the entire PySide6
GUI: shared style constants, shared helper functions, shared widgets,
five tab classes, four `QThread` worker classes, `MainWindow`, and `main()`.
This is purely a navigation/readability problem — the app's behavior,
public entry points, and build process are unaffected. Goal: make each
piece easy to find and reason about in isolation, without introducing
reuse indirection where none currently exists.

`mm_toolkit/core.py` (the platform-neutral media engine) and
`mm_toolkit/versioning.py` are out of scope — they're already
well-isolated and covered by `tests/`.

## Reuse analysis

Grepped every call site of each shared helper/widget/worker in `app.py`
to confirm actual (not assumed) reuse before assigning module ownership:

| Symbol | Used by |
|---|---|
| `PathRow`, `page_title`, `section_group`, `material_icon`, `open_preview`, `show_error`, `show_completion`, `bundled_asset`, style constants | 3+ tabs / MainWindow each — genuinely shared |
| `ClipField`, `VideoPreviewWidget`, `ClipWorker` | `ClipsTab` only |
| `RenderWorker`, `DropDetectionDialog`, `DropStartField`, `DropDetectionWorker` | Video Generator section (built inline in `MainWindow`) only |
| `ConverterWorker` | `ConverterTab` only |

Single-consumer widgets/workers move with their tab rather than into a
shared module — splitting them out would add import indirection with no
reuse benefit.

## Target layout

New package `mm_toolkit/ui/`:

- `__init__.py` — empty (package marker)
- `style.py` — `TIMESTAMP_FIELD_STYLE`, `TIMESTAMP_BUTTON_STYLE`,
  `ICON_BUTTON_STYLE`, `material_icon()`, `bundled_asset()`
- `helpers.py` — `open_preview()`, `show_error()`, `show_completion()`,
  `section_group()`, `page_title()`
- `widgets.py` — `PathRow` (the only widget shared across every tab)
- `video_generator.py` — the Video Generator tab content (currently
  built inline inside `MainWindow.__init__`, lines ~1557-1751 of the
  current `app.py`) extracted into a `VideoGeneratorTab(QWidget)` class
  for symmetry with the other tabs, plus its dedicated `RenderWorker`,
  `DropDetectionDialog`, `DropStartField`, `DropDetectionWorker`
- `clips_tab.py` — `ClipsTab` + `ClipField`, `VideoPreviewWidget`,
  `ClipWorker`
- `converter_tab.py` — `ConverterTab` + `ConverterWorker`
- `settings_tab.py` — `SettingsTab`
- `about_tab.py` — `AboutTab`
- `history_tab.py` — `HistoryTab`
- `main_window.py` — `MainWindow`, `main()`

`mm_toolkit/app.py` becomes a thin re-export shim:

```python
from .ui.main_window import main

__all__ = ["main"]
```

This keeps `mm_toolkit/__main__.py` (`from .app import main`) and
`run_app.py` (`from mm_toolkit.app import main`) working unchanged, and
`MMToolkit.spec`'s `Analysis(["run_app.py"], ...)` entry point needs no
edits — PyInstaller resolves the new `mm_toolkit.ui.*` submodules via
normal import discovery from that entry point.

## Extracting `VideoGeneratorTab`

This is the one non-mechanical step: today the Video Generator's UI is
built directly inside `MainWindow.__init__` rather than as its own
`QWidget` subclass. It gets pulled out into a `VideoGeneratorTab(QWidget)`
class (mirroring `ClipsTab`/`ConverterTab`), constructed once in
`MainWindow.__init__` and added via `self.tabs.addTab(...)` like the
other tabs. Its internal behavior (drop detection, promo rendering)
is unchanged — only the container class changes.

## Migration approach

Mechanical, file-by-file move (not a rewrite):

1. Create `mm_toolkit/ui/` and the shared modules first (`style.py`,
   `helpers.py`, `widgets.py`) since every tab module depends on them.
2. Move each tab (and its single-consumer widgets/workers) into its own
   module, updating imports to pull shared code from `ui.style` /
   `ui.helpers` / `ui.widgets` and domain code from `mm_toolkit.core`.
3. Extract `VideoGeneratorTab` into `video_generator.py`.
4. Move `MainWindow` + `main()` into `main_window.py`, importing each
   tab class from its new module.
5. Replace `mm_toolkit/app.py` with the re-export shim.

## Testing / verification

- `pytest` — unaffected (only imports `mm_toolkit.core`), must stay green.
- Manual: launch `python -m mm_toolkit`, open every tab (Video
  Generator, Media Cutter, Media Converter, History, Settings, About),
  confirm no import errors and existing functionality (drop detection
  dialog, clip preview, converter run) still works.
- No changes expected to `MMToolkit.spec`, `requirements*.txt`, or
  `.github/workflows/*` — confirm by re-reading `MMToolkit.spec`'s
  `hiddenimports` after the move in case PyInstaller's static analysis
  needs an explicit entry for a submodule it can't discover.

## Out of scope

- No behavior changes to any tab, worker, or dialog.
- No changes to `core.py`, `versioning.py`, or the build/release
  pipeline.
- No renaming of existing public symbols beyond adding the new
  `VideoGeneratorTab` class name.
