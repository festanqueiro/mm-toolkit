# Split app.py into ui/ package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 2,333-line `mm_toolkit/app.py` (the entire PySide6 GUI) into a `mm_toolkit/ui/` package, one file per tab/worker-group, with no behavior change.

**Architecture:** Pure relocation refactor. Build the complete new `mm_toolkit/ui/` package first while `mm_toolkit/app.py` stays untouched and fully working (each intermediate commit leaves the app in a working state). Only the final task deletes code from `app.py`, replacing it with a two-line re-export shim, after every new module has been verified to import cleanly on its own.

**Tech Stack:** Python 3.13, PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-08-17-ui-module-split-design.md`

## Global Constraints

- No behavior changes to any tab, worker, or dialog — this is a move, not a rewrite. If a step calls for anything beyond relocating existing code (there are exactly two: extracting `VideoGeneratorTab` in Task 9, and rewiring `MainWindow.__init__` in Task 10), the plan spells out the exact resulting code.
- `mm_toolkit/core.py` and `mm_toolkit/versioning.py` are out of scope — do not modify them.
- Every source line range cited below (e.g. `app.py:154-165`) refers to the **current, unmodified** `mm_toolkit/app.py` at the time this plan was written. Since Tasks 1-10 only ever *read* from `app.py` and *create* new files, those line numbers stay valid through Task 10. Task 11 is the only task that edits `app.py`.
- **Git:** stage changes at the end of each task but do **not** run `git commit` — per this project's standing instruction, commits happen only when the user explicitly asks. Each task's "Commit" step below means `git add <files>` and stopping there.
- **Import fix-up loop** (used in every task): after creating a new module, run `python -c "import mm_toolkit.ui.<module>"` from the repo root (venv activated). If it fails with `NameError: name 'X' is not defined` or `ImportError`, look up `X` in the Symbol Reference table below, add the matching import line, and re-run. Repeat until the import succeeds with no output.

### Symbol Reference (for the fix-up loop)

| Symbol(s) | Import line |
|---|---|
| `Qt`, `QUrl`, `QByteArray`, `QSize`, `QSettings`, `QThread`, `Signal` | `from PySide6.QtCore import ...` |
| `QDesktopServices`, `QFont`, `QIcon`, `QImage`, `QPainter`, `QPalette`, `QPixmap` | `from PySide6.QtGui import ...` |
| `QAudioOutput`, `QMediaPlayer` | `from PySide6.QtMultimedia import ...` |
| `QVideoWidget` | `from PySide6.QtMultimediaWidgets import QVideoWidget` |
| `QNetworkAccessManager`, `QNetworkReply`, `QNetworkRequest` | `from PySide6.QtNetwork import ...` |
| `QSvgRenderer` | `from PySide6.QtSvg import QSvgRenderer` |
| Any other `Q*` widget/layout class (`QWidget`, `QLabel`, `QPushButton`, `QVBoxLayout`, etc.) | `from PySide6.QtWidgets import ...` |
| `AUDIO_OUTPUT_FORMATS`, `CancelledError`, `ClipRequest`, `RenderSettings`, `VIDEO_OUTPUT_FORMATS`, `convert_media`, `cut_media_clips`, `detect_drop_starts`, `find_audio_files`, `format_timestamp`, `generate_videos`, `media_kind`, `parse_timestamp`, `validate_visual`, `validate_media_source`, `validate_video` | `from mm_toolkit.core import ...` |
| `__version__` | `from mm_toolkit import __version__` |
| `is_newer_version` | `from mm_toolkit.versioning import is_newer_version` |
| `material_icon`, `bundled_asset`, `TIMESTAMP_FIELD_STYLE`, `TIMESTAMP_BUTTON_STYLE`, `ICON_BUTTON_STYLE` | `from mm_toolkit.ui.style import ...` |
| `open_preview`, `show_error`, `show_completion`, `section_group`, `page_title` | `from mm_toolkit.ui.helpers import ...` |
| `PathRow` | `from mm_toolkit.ui.widgets import PathRow` |
| stdlib: `os`, `html`, `json`, `shutil`, `sys`, `traceback`, `Path`, `datetime`, `cv2` | `import os` / `import html` / `import json` / `import shutil` / `import sys` / `import traceback` / `from pathlib import Path` / `from datetime import datetime` / `import cv2` |
| `from __future__ import annotations` | add to every new module, as the first line after its docstring (matches existing `app.py` convention) |

---

### Task 1: `mm_toolkit/ui/style.py`

**Files:**
- Create: `mm_toolkit/ui/__init__.py` (empty file)
- Create: `mm_toolkit/ui/style.py`
- Source (read-only): `mm_toolkit/app.py:77-91` (three style constants), `mm_toolkit/app.py:122-126` (`bundled_asset`), `mm_toolkit/app.py:154-165` (`material_icon`)

**Interfaces:**
- Produces: `TIMESTAMP_FIELD_STYLE: str`, `TIMESTAMP_BUTTON_STYLE: str`, `ICON_BUTTON_STYLE: str`, `bundled_asset(name: str) -> Path`, `material_icon(name: str, color: str) -> QIcon`

- [ ] **Step 1: Create the package marker**

Create `mm_toolkit/ui/__init__.py` as an empty file (no content needed — it's just a package marker).

- [ ] **Step 2: Create `style.py`**

Copy `app.py:77-91` (the three `*_STYLE` constants) and `app.py:122-126` (`bundled_asset`) and `app.py:154-165` (`material_icon`) verbatim into a new `mm_toolkit/ui/style.py`, in that order. Add this header before them:

```python
"""Shared Qt style-sheet constants and icon helpers for MM Toolkit's UI."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
```

- [ ] **Step 3: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.style"
```

Expected: no output (success). If it fails, consult the Symbol Reference table above and add the missing import.

- [ ] **Step 4: Run the test suite (regression check)**

```bash
python -m pytest -q
```

Expected: unchanged, 28 passed (this task never touches `core.py`, so this just confirms nothing else broke).

- [ ] **Step 5: Stage**

```bash
git add mm_toolkit/ui/__init__.py mm_toolkit/ui/style.py
```

---

### Task 2: `mm_toolkit/ui/helpers.py`

**Files:**
- Create: `mm_toolkit/ui/helpers.py`
- Source (read-only): `mm_toolkit/app.py:95-121` (`open_preview`, `show_error`, `show_completion`), `mm_toolkit/app.py:127-153` (`section_group`, `page_title`)

**Interfaces:**
- Consumes: nothing from Task 1 (independent leaf module)
- Produces: `open_preview(parent, path) -> None`, `show_error(parent, title, message, details) -> None`, `show_completion(parent, title, outputs) -> None`, `section_group(title, content_layout) -> QGroupBox`, `page_title(text: str) -> QLabel`

- [ ] **Step 1: Create `helpers.py`**

Copy `app.py:95-121` and `app.py:127-153` verbatim, in that order, into `mm_toolkit/ui/helpers.py`. Add this header:

```python
"""Shared dialog and layout helpers for MM Toolkit's UI tabs."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QGroupBox, QLabel, QMessageBox, QWidget
```

- [ ] **Step 2: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.helpers"
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest -q
```

- [ ] **Step 4: Stage**

```bash
git add mm_toolkit/ui/helpers.py
```

---

### Task 3: `mm_toolkit/ui/widgets.py`

**Files:**
- Create: `mm_toolkit/ui/widgets.py`
- Source (read-only): `mm_toolkit/app.py:297-361` (`PathRow`)

**Interfaces:**
- Consumes: nothing from Tasks 1-2 (independent leaf module)
- Produces: `PathRow(QWidget)` — constructor `PathRow(dialog_title: str, mode: str, file_filter: str = "")`, signal `changed = Signal(str)`, property `.path`, methods `.set_path()`, `.set_enabled()`

- [ ] **Step 1: Create `widgets.py`**

Copy `app.py:297-361` verbatim into `mm_toolkit/ui/widgets.py`. Add this header:

```python
"""Shared widgets used across MM Toolkit's UI tabs."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget
```

- [ ] **Step 2: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.widgets"
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest -q
```

- [ ] **Step 4: Stage**

```bash
git add mm_toolkit/ui/widgets.py
```

---

### Task 4: `mm_toolkit/ui/clips_tab.py`

**Files:**
- Create: `mm_toolkit/ui/clips_tab.py`
- Source (read-only): `mm_toolkit/app.py:229-262` (`ClipWorker`), `mm_toolkit/app.py:362-369` (`ClipField`), `mm_toolkit/app.py:370-382` (`VideoPreviewWidget`), `mm_toolkit/app.py:449-1032` (`ClipsTab`)

**Interfaces:**
- Consumes: `mm_toolkit.ui.style.{TIMESTAMP_FIELD_STYLE, TIMESTAMP_BUTTON_STYLE, ICON_BUTTON_STYLE, material_icon}`, `mm_toolkit.ui.helpers.{open_preview, show_error, show_completion, section_group, page_title}`, `mm_toolkit.ui.widgets.PathRow`, `mm_toolkit.core.{CancelledError, ClipRequest, cut_media_clips, format_timestamp, media_kind, parse_timestamp, validate_media_source}`
- Produces: `ClipWorker(QThread)`, `ClipField(QLineEdit)`, `VideoPreviewWidget(QVideoWidget)`, `ClipsTab(QWidget)` — constructor `ClipsTab(settings: QSettings)`, signal `job_completed = Signal(object)`

- [ ] **Step 1: Create `clips_tab.py`**

Copy, in this order: `app.py:229-262` (`ClipWorker`), `app.py:362-369` (`ClipField`), `app.py:370-382` (`VideoPreviewWidget`), `app.py:449-1032` (`ClipsTab`) verbatim into `mm_toolkit/ui/clips_tab.py`. Add this header:

```python
"""Media Cutter tab: clip a source file into precisely timed exports."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mm_toolkit.core import (
    CancelledError,
    ClipRequest,
    cut_media_clips,
    format_timestamp,
    media_kind,
    parse_timestamp,
    validate_media_source,
)
from mm_toolkit.ui.helpers import open_preview, page_title, section_group, show_completion, show_error
from mm_toolkit.ui.style import ICON_BUTTON_STYLE, TIMESTAMP_BUTTON_STYLE, TIMESTAMP_FIELD_STYLE, material_icon
from mm_toolkit.ui.widgets import PathRow
```

- [ ] **Step 2: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.clips_tab"
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest -q
```

- [ ] **Step 4: Stage**

```bash
git add mm_toolkit/ui/clips_tab.py
```

---

### Task 5: `mm_toolkit/ui/converter_tab.py`

**Files:**
- Create: `mm_toolkit/ui/converter_tab.py`
- Source (read-only): `mm_toolkit/app.py:263-296` (`ConverterWorker`), `mm_toolkit/app.py:1033-1304` (`ConverterTab`)

**Interfaces:**
- Consumes: `mm_toolkit.ui.helpers.{open_preview, page_title, section_group, show_completion, show_error}`, `mm_toolkit.ui.widgets.PathRow`, `mm_toolkit.core.{AUDIO_OUTPUT_FORMATS, CancelledError, VIDEO_OUTPUT_FORMATS, convert_media, media_kind}`
- Produces: `ConverterWorker(QThread)`, `ConverterTab(QWidget)` — constructor `ConverterTab(settings: QSettings)`, signal `job_completed = Signal(object)`

- [ ] **Step 1: Create `converter_tab.py`**

Copy, in this order: `app.py:263-296` (`ConverterWorker`), `app.py:1033-1304` (`ConverterTab`) verbatim into `mm_toolkit/ui/converter_tab.py`. Add this header:

```python
"""Media Converter tab: batch-convert audio/video between formats."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mm_toolkit.core import AUDIO_OUTPUT_FORMATS, CancelledError, VIDEO_OUTPUT_FORMATS, convert_media, media_kind
from mm_toolkit.ui.helpers import open_preview, page_title, section_group, show_completion, show_error
from mm_toolkit.ui.widgets import PathRow
```

- [ ] **Step 2: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.converter_tab"
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest -q
```

- [ ] **Step 4: Stage**

```bash
git add mm_toolkit/ui/converter_tab.py
```

---

### Task 6: `mm_toolkit/ui/settings_tab.py`

**Files:**
- Create: `mm_toolkit/ui/settings_tab.py`
- Source (read-only): `mm_toolkit/app.py:1305-1400` (`SettingsTab`)

**Interfaces:**
- Consumes: `mm_toolkit.ui.helpers.{page_title, section_group}`, `mm_toolkit.ui.widgets.PathRow`
- Produces: `SettingsTab(QWidget)` — constructor `SettingsTab(settings: QSettings)`, signal `changed = Signal()`

- [ ] **Step 1: Create `settings_tab.py`**

Copy `app.py:1305-1400` verbatim into `mm_toolkit/ui/settings_tab.py`. Add this header:

```python
"""Settings tab: app-wide defaults (output folder, naming, conflict policy)."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from mm_toolkit.ui.helpers import page_title, section_group
from mm_toolkit.ui.widgets import PathRow
```

- [ ] **Step 2: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.settings_tab"
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest -q
```

- [ ] **Step 4: Stage**

```bash
git add mm_toolkit/ui/settings_tab.py
```

---

### Task 7: `mm_toolkit/ui/about_tab.py`

**Files:**
- Create: `mm_toolkit/ui/about_tab.py`
- Source (read-only): `mm_toolkit/app.py:1401-1488` (`AboutTab`)

**Interfaces:**
- Consumes: `mm_toolkit.ui.style.bundled_asset`, `mm_toolkit.ui.helpers.page_title`, `mm_toolkit.__version__`, `mm_toolkit.versioning.is_newer_version`
- Produces: `AboutTab(QWidget)` — constructor `AboutTab()`

- [ ] **Step 1: Create `about_tab.py`**

Copy `app.py:1401-1488` verbatim into `mm_toolkit/ui/about_tab.py`. Add this header:

```python
"""About tab: app info, logo, and update check."""

from __future__ import annotations

import html
import json
import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from mm_toolkit import __version__
from mm_toolkit.ui.helpers import page_title
from mm_toolkit.ui.style import bundled_asset
from mm_toolkit.versioning import is_newer_version
```

- [ ] **Step 2: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.about_tab"
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest -q
```

- [ ] **Step 4: Stage**

```bash
git add mm_toolkit/ui/about_tab.py
```

---

### Task 8: `mm_toolkit/ui/history_tab.py`

**Files:**
- Create: `mm_toolkit/ui/history_tab.py`
- Source (read-only): `mm_toolkit/app.py:1489-1556` (`HistoryTab`)

**Interfaces:**
- Consumes: nothing from other `ui` modules
- Produces: `HistoryTab(QWidget)` — constructor `HistoryTab(settings: QSettings)`, signal `load_requested = Signal(object)`, method `.refresh()`

- [ ] **Step 1: Create `history_tab.py`**

Copy `app.py:1489-1556` verbatim into `mm_toolkit/ui/history_tab.py`. Add this header:

```python
"""History tab: recent job list, reload-into-tab support."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget
```

- [ ] **Step 2: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.history_tab"
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest -q
```

- [ ] **Step 4: Stage**

```bash
git add mm_toolkit/ui/history_tab.py
```

---

### Task 9: `mm_toolkit/ui/video_generator.py`

This is the one non-mechanical extraction: today the Video Generator UI is built directly inside `MainWindow.__init__` rather than as its own tab class. This task turns it into `VideoGeneratorTab(QWidget)`, mirroring `ClipsTab`/`ConverterTab`'s shape (constructor takes `settings`, builds its layout directly on `self` instead of a separate `container` widget, and reports finished jobs via a `job_completed` signal instead of calling a MainWindow method directly).

**Files:**
- Create: `mm_toolkit/ui/video_generator.py`
- Source (read-only): `mm_toolkit/app.py:166-203` (`RenderWorker`), `mm_toolkit/app.py:204-228` (`DropDetectionWorker`), `mm_toolkit/app.py:383-416` (`DropStartField`), `mm_toolkit/app.py:417-448` (`DropDetectionDialog`), `mm_toolkit/app.py:1567-1751` (widget construction, minus the other-tab/tab-assembly lines noted below), `mm_toolkit/app.py:1771-1782` (`restore_paths`), `mm_toolkit/app.py:1847-2063` (`on_music_changed` through `set_drop_buttons_enabled`), `mm_toolkit/app.py:2063-2309` (`validate` through `worker_finished` — NOT `closeEvent`, which stays in `MainWindow`)

**Interfaces:**
- Consumes: `mm_toolkit.ui.style.{ICON_BUTTON_STYLE, TIMESTAMP_FIELD_STYLE, material_icon}`, `mm_toolkit.ui.helpers.{page_title, section_group, show_completion, show_error}`, `mm_toolkit.ui.widgets.PathRow`, `mm_toolkit.core.{CancelledError, RenderSettings, detect_drop_starts, find_audio_files, format_timestamp, generate_videos, parse_timestamp, validate_visual}`
- Produces: `RenderWorker(QThread)`, `DropDetectionWorker(QThread)`, `DropStartField(QWidget)`, `DropDetectionDialog(QDialog)`, `VideoGeneratorTab(QWidget)` — constructor `VideoGeneratorTab(settings: QSettings)`, signal `job_completed = Signal(object)`, attributes `.worker: RenderWorker | None`, `.analysis_worker: DropDetectionWorker | None`, method `.stop_promo_preview()`

- [ ] **Step 1: Copy the four standalone classes**

Copy, in this order, verbatim: `app.py:166-203` (`RenderWorker`), `app.py:204-228` (`DropDetectionWorker`), `app.py:383-416` (`DropStartField`), `app.py:417-448` (`DropDetectionDialog`) into a new `mm_toolkit/ui/video_generator.py`. Add this header above them:

```python
"""Video Generator tab: render a promo video from audio + artwork/video."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Qt, QUrl, Signal
from PySide6.QtGui import QImage, QPalette, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
import cv2

from mm_toolkit.core import (
    CancelledError,
    RenderSettings,
    detect_drop_starts,
    find_audio_files,
    format_timestamp,
    generate_videos,
    parse_timestamp,
    validate_visual,
)
from mm_toolkit.ui.helpers import page_title, section_group, show_completion, show_error
from mm_toolkit.ui.style import ICON_BUTTON_STYLE, TIMESTAMP_FIELD_STYLE, material_icon
from mm_toolkit.ui.widgets import PathRow
```

- [ ] **Step 2: Add the `VideoGeneratorTab` class**

Append this class to the same file. It's assembled from the exact code currently in `MainWindow` (cited per-section below) with two structural changes from the original: (a) it builds its layout directly on `self` instead of a separate `container` widget — copy the body of `app.py:1710-1743` but change `container = QWidget()` / `layout = QVBoxLayout(container)` to just `layout = QVBoxLayout(self)`, and drop the `container` variable entirely; (b) `on_success` (`app.py:2270-2292`) emits `self.job_completed` instead of calling `self.add_history(...)` — copy it verbatim except changing the first line from `self.add_history({` to `self.job_completed.emit({`.

```python
class VideoGeneratorTab(QWidget):
    job_completed = Signal(object)

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.worker: RenderWorker | None = None
        self.analysis_worker: DropDetectionWorker | None = None

        # --- app.py:1567-1709 verbatim (title, subtitle, all self.* field
        #     construction: music/cover/output PathRows, checkboxes, promo_tracks
        #     table, promo preview player, profile/duration/fps/crf/encoding_speed/
        #     audio_bitrate controls, form layouts, generate/clear/cancel buttons,
        #     progress bar) goes here unchanged.

        # --- app.py:1710-1743, MODIFIED per (a) above: ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        feature_columns = QHBoxLayout()
        feature_columns.setSpacing(14)
        input_column = QVBoxLayout()
        self.promo_input_group = section_group("Input", input_form)
        self.promo_input_group.setMinimumHeight(250)
        input_column.addWidget(self.promo_input_group)
        self.promo_clips_group = section_group("Audio timestamps", promo_clips_layout)
        input_column.addWidget(self.promo_clips_group, 1)
        input_column.addStretch()
        settings_column = QVBoxLayout()
        self.post_effects_group = section_group("Post-Effects", effects_form)
        self.output_group = section_group("Output", output_form)
        settings_column.addWidget(self.post_effects_group)
        settings_column.addWidget(self.output_group)
        settings_column.addStretch()
        feature_columns.addLayout(input_column, 1)
        feature_columns.addLayout(settings_column, 1)
        layout.addLayout(feature_columns, 1)
        layout.addWidget(divider)
        layout.addWidget(self.progress_status)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        actions.addWidget(self.clear_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.generate_requirements, 1)
        actions.addWidget(self.generate)
        layout.addLayout(actions)

        self.music.changed.connect(self.on_music_changed)
        self.cover.changed.connect(self.validate)
        self.output.changed.connect(self.validate)
        self.restore_paths()
        self.refresh_promo_tracks()
        self.validate()

    # --- app.py:1771-1782 (restore_paths), unchanged ---
    # --- app.py:1847-2063: on_music_changed, refresh_promo_tracks,
    #     on_promo_timing_changed, update_promo_preview_button,
    #     toggle_promo_preview, on_promo_preview_media_status,
    #     start_promo_preview_playback, on_promo_preview_position,
    #     on_promo_preview_state, stop_promo_preview, promo_track_options,
    #     start_drop_detection, on_drop_detection_success,
    #     on_drop_detection_finished, set_drop_buttons_enabled — all unchanged ---
    # --- app.py:2063-2219: validate, update_artwork_preview,
    #     set_inputs_enabled, cancel, clear — all unchanged ---
    # --- app.py:2219-2266: start_generation, on_progress — unchanged ---

    def on_success(self, outputs: list[str]) -> None:
        self.job_completed.emit({
            # ... exact dict body from app.py:2271-2289, unchanged ...
        })
        if self.settings.value("general/notify_finished", True, type=bool):
            show_completion(self, "Videos generated", outputs)

    # --- app.py:2294-2307: on_failure, on_cancelled, worker_finished — unchanged ---
```

Do not copy `app.py`'s `closeEvent` (`2309-2319`) — that stays in `MainWindow` (Task 10). Do not copy the lines that construct other tabs or the `QTabWidget` (`app.py:1744-1757`, `1759-1769` except the three lines noted above) — those also stay in `MainWindow`.

- [ ] **Step 3: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.video_generator"
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest -q
```

- [ ] **Step 5: Stage**

```bash
git add mm_toolkit/ui/video_generator.py
```

---

### Task 10: `mm_toolkit/ui/main_window.py`

**Files:**
- Create: `mm_toolkit/ui/main_window.py`
- Source (read-only): `mm_toolkit/app.py:1557-1770` (constructor shell — see rewrite below), `mm_toolkit/app.py:1783-1846` (`apply_app_settings`, `add_history`, `load_history_job`), `mm_toolkit/app.py:2309-2319` (`closeEvent`), `mm_toolkit/app.py:2322-2333` (`main()` + `__main__` guard)

**Interfaces:**
- Consumes: `mm_toolkit.ui.style.material_icon`, `mm_toolkit.ui.video_generator.VideoGeneratorTab`, `mm_toolkit.ui.clips_tab.ClipsTab`, `mm_toolkit.ui.converter_tab.ConverterTab`, `mm_toolkit.ui.settings_tab.SettingsTab`, `mm_toolkit.ui.about_tab.AboutTab`, `mm_toolkit.ui.history_tab.HistoryTab`, `mm_toolkit.ui.style.bundled_asset`
- Produces: `MainWindow(QMainWindow)`, `main() -> int`

- [ ] **Step 1: Create `main_window.py` with the rewritten constructor**

```python
"""Main window: assembles all tabs and owns cross-tab coordination."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget

from mm_toolkit.core import format_timestamp
from mm_toolkit.ui.about_tab import AboutTab
from mm_toolkit.ui.clips_tab import ClipsTab
from mm_toolkit.ui.converter_tab import ConverterTab
from mm_toolkit.ui.history_tab import HistoryTab
from mm_toolkit.ui.settings_tab import SettingsTab
from mm_toolkit.ui.style import bundled_asset, material_icon
from mm_toolkit.ui.video_generator import VideoGeneratorTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MM Toolkit", "MM Toolkit")
        self.setWindowTitle("MM Toolkit")
        self.setMinimumSize(820, 620)
        self.resize(1100, 820)

        self.video_generator = VideoGeneratorTab(self.settings)
        self.clips = ClipsTab(self.settings)
        self.converter = ConverterTab(self.settings)
        self.app_settings = SettingsTab(self.settings)
        self.history = HistoryTab(self.settings)
        self.about = AboutTab()
        self.tabs = QTabWidget()
        icon_color = self.palette().color(QPalette.ColorRole.WindowText).name()
        self.tabs.addTab(self.video_generator, material_icon("music_video", icon_color), "Video Generator")
        self.tabs.addTab(self.clips, material_icon("content_cut", icon_color), "Media Cutter")
        self.tabs.addTab(self.converter, material_icon("swap_horiz", icon_color), "Media Converter")
        self.tabs.addTab(self.history, material_icon("history", icon_color), "History")
        self.tabs.addTab(self.app_settings, material_icon("settings", icon_color), "Settings")
        self.tabs.addTab(self.about, material_icon("info", icon_color), "About")
        self.setCentralWidget(self.tabs)

        self.app_settings.changed.connect(self.apply_app_settings)
        self.video_generator.job_completed.connect(self.add_history)
        self.clips.job_completed.connect(self.add_history)
        self.converter.job_completed.connect(self.add_history)
        self.history.load_requested.connect(self.load_history_job)
        self.apply_app_settings()
```

This replaces the old `app.py:1557-1770`: the video-generator-specific widget construction (`app.py:1567-1751`'s non-tab-assembly parts) is gone from here — it now lives in `VideoGeneratorTab.__init__` (Task 9). `self.worker` / `self.analysis_worker` no longer exist on `MainWindow` — they're now `self.video_generator.worker` / `self.video_generator.analysis_worker` (see `closeEvent` below).

- [ ] **Step 2: Add the cross-tab coordination methods**

Copy verbatim, in this order: `app.py:1783-1791` (`apply_app_settings`), `app.py:1793-1801` (`add_history`), `app.py:1802-1845` (`load_history_job`) — no changes needed, they already only reference `self.clips`, `self.converter`, `self.history`, `self.settings`.

- [ ] **Step 3: Add `closeEvent`, updated for the new attribute locations**

```python
    def closeEvent(self, event):  # noqa: N802, ANN001
        promo_running = self.video_generator.worker and self.video_generator.worker.isRunning()
        analysis_running = self.video_generator.analysis_worker and self.video_generator.analysis_worker.isRunning()
        clips_running = self.clips.worker and self.clips.worker.isRunning()
        converter_running = self.converter.worker and self.converter.worker.isRunning()
        if promo_running or analysis_running or clips_running or converter_running:
            QMessageBox.warning(self, "Rendering in progress", "Wait for rendering to finish before closing the app.")
            event.ignore()
            return
        self.video_generator.stop_promo_preview()
        event.accept()
```

- [ ] **Step 4: Add `main()`**

Copy `app.py:2322-2333` (`main()` and the `if __name__ == "__main__":` guard) verbatim to the end of the file.

- [ ] **Step 5: Run the import fix-up loop**

```bash
python -c "import mm_toolkit.ui.main_window"
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest -q
```

- [ ] **Step 7: Stage**

```bash
git add mm_toolkit/ui/main_window.py
```

---

### Task 11: Replace `app.py` with the shim, verify the whole app

**Files:**
- Modify: `mm_toolkit/app.py` (replace entire contents)
- Verify (read-only): `MMToolkit.spec`

**Interfaces:**
- Consumes: `mm_toolkit.ui.main_window.main`
- Produces: `mm_toolkit.app.main` (unchanged public name, now re-exported)

- [ ] **Step 1: Replace `app.py`'s contents**

```python
"""Desktop interface for MM Toolkit."""

from __future__ import annotations

from mm_toolkit.ui.main_window import main

__all__ = ["main"]
```

- [ ] **Step 2: Confirm the existing entry points still resolve**

```bash
python -c "from mm_toolkit.app import main; print(main)"
python -c "from mm_toolkit.__main__ import *" 2>&1 | tail -5   # only errors if it tries to actually run the app; a clean import is fine
```

Expected: the first command prints `<function main at 0x...>` with no traceback.

- [ ] **Step 3: Confirm `MMToolkit.spec` needs no changes**

Read `MMToolkit.spec` and confirm `hiddenimports` still only lists `mm_toolkit.core` and the `moviepy.*` fx modules (no reference to `mm_toolkit.app` internals). The `Analysis(["run_app.py"], ...)` entry point discovers `mm_toolkit.ui.*` automatically via `run_app.py` → `mm_toolkit.app` → `mm_toolkit.ui.main_window` → ... import chain, so no edit is expected. If it turns out something needs adding, add `"mm_toolkit.ui.<module>"` entries to `hiddenimports` for any module PyInstaller's static analysis can't resolve.

- [ ] **Step 4: Run the full test suite**

```bash
python -m pytest -q
```

Expected: 28 passed (unchanged from before this plan started).

- [ ] **Step 5: Launch the app and manually verify every tab**

```bash
python -m mm_toolkit
```

Click through: Video Generator (choose an audio file + image, confirm the form populates and Generate enables once export folder is set), Media Cutter, Media Converter, History, Settings, About. Confirm no import errors on launch and no visual/behavioral regressions vs. the pre-split app.

- [ ] **Step 6: Stage**

```bash
git add mm_toolkit/app.py
```
