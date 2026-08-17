"""Desktop interface for Media Tools for Record Labels."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .core import (
    ClipRequest,
    RenderSettings,
    cut_video_clips,
    find_audio_files,
    generate_videos,
    parse_timestamp,
    validate_cover,
    validate_video,
)
from . import __version__


def open_preview(parent: QWidget, path: str | Path) -> None:
    target = Path(path).expanduser()
    if not target.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(target))):
        QMessageBox.warning(parent, "Preview unavailable", f"Could not open:\n{target}")


def bundled_asset(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets" / name


def section_group(title: str, content_layout) -> QGroupBox:  # noqa: ANN001
    group = QGroupBox(title)
    group.setLayout(content_layout)
    group.setStyleSheet(
        "QGroupBox {"
        "  font-weight: 600;"
        "  border: 1px solid rgba(127, 127, 127, 0.28);"
        "  border-radius: 10px;"
        "  margin-top: 8px;"
        "  padding-top: 10px;"
        "  background-color: rgba(127, 127, 127, 0.06);"
        "}"
        "QGroupBox::title {"
        "  subcontrol-origin: margin;"
        "  left: 12px;"
        "  padding: 0 6px;"
        "}"
    )
    return group


class RenderWorker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, tracks: list[Path], cover: Path, output: Path, settings: RenderSettings):
        super().__init__()
        self.tracks = tracks
        self.cover = cover
        self.output = output
        self.settings = settings

    def run(self) -> None:
        try:
            results = generate_videos(
                self.tracks,
                self.cover,
                self.output,
                self.settings,
                lambda percent, status: self.progress.emit(percent, status),
            )
            self.succeeded.emit([os.fspath(path) for path in results])
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc))


class ClipWorker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, source: Path, clips: list[ClipRequest], output: Path):
        super().__init__()
        self.source = source
        self.clips = clips
        self.output = output

    def run(self) -> None:
        try:
            results = cut_video_clips(
                self.source,
                self.clips,
                self.output,
                lambda percent, status: self.progress.emit(percent, status),
            )
            self.succeeded.emit([os.fspath(path) for path in results])
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc))


class PathRow(QWidget):
    changed = Signal(str)

    def __init__(self, dialog_title: str, mode: str, file_filter: str = ""):
        super().__init__()
        self.dialog_title = dialog_title
        self.mode = mode
        self.file_filter = file_filter
        self.edit = QLineEdit()
        self.edit.setReadOnly(True)
        self.edit.setPlaceholderText("Nothing selected")
        self.button = QPushButton("Choose…")
        self.button.clicked.connect(self.choose)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    @property
    def path(self) -> str:
        return self.edit.text()

    def set_path(self, path: str) -> None:
        self.edit.setText(path)
        self.changed.emit(path)

    def choose(self) -> None:
        start = self.path or str(Path.home())
        if self.mode == "file":
            selected, _ = QFileDialog.getOpenFileName(self, self.dialog_title, start, self.file_filter)
        else:
            selected = QFileDialog.getExistingDirectory(self, self.dialog_title, start)
        if selected:
            self.set_path(selected)

    def set_enabled(self, enabled: bool) -> None:
        self.button.setEnabled(enabled)


class ClipsTab(QWidget):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.worker: ClipWorker | None = None
        title = QLabel("Livestream Clips")
        title.setFont(QFont("", 24, QFont.Weight.DemiBold))
        subtitle = QLabel(
            "Create precisely timed social clips from a long recording. "
            "Use HH:MM:SS, MM:SS, or seconds. End is optional; duration defaults to 60 seconds."
        )
        subtitle.setWordWrap(True)
        self.source = PathRow(
            "Choose source video",
            "file",
            "Videos (*.mp4 *.mov *.m4v *.mkv *.avi *.webm)",
        )
        self.output = PathRow("Choose clip export folder", "directory")
        self.source_status = QLabel("Choose a source video.")
        self.output_status = QLabel("Choose an export folder.")
        self.preview_source = QPushButton("▶ Play Source Video")
        self.preview_source.setEnabled(False)
        self.preview_source.clicked.connect(lambda: open_preview(self, self.source.path))

        input_form = QFormLayout()
        input_form.setSpacing(10)
        input_form.addRow("Source video", self.source)
        input_form.addRow("", self.source_status)
        input_form.addRow("Preview", self.preview_source)

        output_form = QFormLayout()
        output_form.setSpacing(10)
        output_form.addRow("Export folder", self.output)
        output_form.addRow("", self.output_status)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Start", "End (optional)", "Duration", ""])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(170)
        self.add_button = QPushButton("+ Add clip")
        self.add_button.clicked.connect(lambda: self.add_row())
        self.clip_status = QLabel("")
        self.generate = QPushButton("Create Clips")
        self.generate.setMinimumHeight(44)
        self.generate.clicked.connect(self.start_generation)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.progress_status = QLabel("")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        self.progress_status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        clip_input_layout = QVBoxLayout()
        clip_input_layout.addLayout(input_form)
        clip_input_layout.addWidget(QLabel("Clip timestamps"))
        clip_input_layout.addWidget(self.table)
        clip_input_layout.addWidget(self.add_button)
        clip_input_layout.addWidget(self.clip_status)
        layout.addWidget(section_group("Input", clip_input_layout))
        layout.addWidget(section_group("Output", output_form))
        layout.addWidget(self.progress_status)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        actions.addWidget(self.clear_button)
        actions.addStretch()
        actions.addWidget(self.generate)
        layout.addLayout(actions)

        self.source.changed.connect(self.validate)
        self.output.changed.connect(self.validate)
        for row, key in ((self.source, "clips/source"), (self.output, "clips/output")):
            value = self.settings.value(key, "")
            if value and Path(value).exists():
                row.edit.setText(value)
        self.add_row()
        self.validate()

    def add_row(self, start: str = "", end: str = "", duration: str = "60") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value, placeholder in (
            (0, start, "00:03:15"),
            (1, end, "Optional"),
            (2, duration, "60"),
        ):
            edit = QLineEdit(value)
            edit.setPlaceholderText(placeholder)
            edit.textChanged.connect(self.validate)
            self.table.setCellWidget(row, column, edit)
        remove = QPushButton("Remove")
        remove.clicked.connect(lambda _checked=False, button=remove: self.remove_row(button))
        self.table.setCellWidget(row, 3, remove)
        self.validate()

    def remove_row(self, button: QPushButton) -> None:
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 3) is button:
                self.table.removeRow(row)
                break
        if self.table.rowCount() == 0:
            self.add_row()
        self.validate()

    def parsed_clips(self) -> tuple[list[ClipRequest], str]:
        clips: list[ClipRequest] = []
        for row in range(self.table.rowCount()):
            start_text = self.table.cellWidget(row, 0).text().strip()
            end_text = self.table.cellWidget(row, 1).text().strip()
            duration_text = self.table.cellWidget(row, 2).text().strip()
            if not start_text:
                return [], f"Clip {row + 1}: enter a start timestamp."
            try:
                start = parse_timestamp(start_text)
                if end_text:
                    duration = parse_timestamp(end_text) - start
                    if duration <= 0:
                        raise ValueError("End must be later than start.")
                else:
                    duration = parse_timestamp(duration_text or "60")
                    if duration <= 0:
                        raise ValueError("Duration must be greater than zero.")
            except ValueError as exc:
                return [], f"Clip {row + 1}: {exc}"
            clips.append(ClipRequest(start, duration))
        return clips, f"✓ {len(clips)} clip{'s' if len(clips) != 1 else ''} ready."

    def validate(self) -> bool:
        source_ok, source_message = validate_video(self.source.path)
        self.source_status.setText(("✓ " if source_ok else "") + source_message)
        output_path = Path(self.output.path).expanduser() if self.output.path else None
        output_ok = bool(output_path and output_path.is_dir() and os.access(output_path, os.W_OK))
        self.output_status.setText("✓ Export folder is writable." if output_ok else "Choose a writable export folder.")
        clips, clip_message = self.parsed_clips()
        self.clip_status.setText(clip_message)
        ready = source_ok and output_ok and bool(clips) and self.worker is None
        self.preview_source.setEnabled(source_ok and self.worker is None)
        self.generate.setEnabled(ready)
        return ready

    def set_inputs_enabled(self, enabled: bool) -> None:
        self.source.set_enabled(enabled)
        self.output.set_enabled(enabled)
        self.add_button.setEnabled(enabled)
        self.table.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        if not enabled:
            self.preview_source.setEnabled(False)

    def clear(self) -> None:
        self.source.set_path("")
        self.output.set_path("")
        self.table.setRowCount(0)
        self.add_row()
        self.progress.setValue(0)
        self.progress.hide()
        self.progress_status.clear()
        self.progress_status.hide()
        self.settings.remove("clips/source")
        self.settings.remove("clips/output")
        self.validate()

    def start_generation(self) -> None:
        if not self.validate():
            return
        clips, _ = self.parsed_clips()
        self.settings.setValue("clips/source", self.source.path)
        self.settings.setValue("clips/output", self.output.path)
        self.worker = ClipWorker(Path(self.source.path), clips, Path(self.output.path))
        self.worker.progress.connect(self.on_progress)
        self.worker.succeeded.connect(self.on_success)
        self.worker.failed.connect(self.on_failure)
        self.worker.finished.connect(self.worker_finished)
        self.progress.setValue(0)
        self.progress.show()
        self.progress_status.setText("Preparing clips…")
        self.progress_status.show()
        self.set_inputs_enabled(False)
        self.generate.setEnabled(False)
        self.worker.start()

    def on_progress(self, percent: int, status: str) -> None:
        self.progress.setValue(percent)
        self.progress_status.setText(status)

    def on_success(self, outputs: list[str]) -> None:
        QMessageBox.information(
            self,
            "Clips created",
            f"Created {len(outputs)} clip{'s' if len(outputs) != 1 else ''} in:\n{self.output.path}",
        )

    def on_failure(self, message: str) -> None:
        QMessageBox.critical(self, "Clip creation failed", message)

    def worker_finished(self) -> None:
        worker = self.worker
        self.worker = None
        self.set_inputs_enabled(True)
        self.validate()
        if worker:
            worker.deleteLater()


class AboutTab(QWidget):
    def __init__(self):
        super().__init__()
        logo = QLabel()
        pixmap = QPixmap(os.fspath(bundled_asset("Media tools app - full logo no bg.png")))
        logo.setPixmap(
            pixmap.scaled(
                300,
                300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Media Tools for Record Labels")
        title.setFont(QFont("", 22, QFont.Weight.DemiBold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version = QLabel(f"Version {__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel(
            "Open-source desktop utilities for creating music promo videos "
            "and cutting clips from long recordings."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        repository = QLabel(
            '<a href="https://github.com/festanqueiro/record-label-mediatools">'
            "github.com/festanqueiro/record-label-mediatools</a>"
        )
        repository.setOpenExternalLinks(True)
        repository.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 28, 40, 28)
        layout.addStretch()
        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addWidget(repository)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: RenderWorker | None = None
        self.settings = QSettings("Media Tools for Record Labels", "Media Tools for Record Labels")
        self.setWindowTitle("Media Tools for Record Labels")
        self.setMinimumSize(780, 570)

        title = QLabel("Promo Videos")
        title.setFont(QFont("", 24, QFont.Weight.DemiBold))
        subtitle = QLabel("Turn audio and cover artwork into promo videos at the artwork's native resolution.")
        subtitle.setWordWrap(True)

        self.music = PathRow("Choose folder containing music", "directory")
        self.cover = PathRow(
            "Choose cover artwork",
            "file",
            "Images (*.png *.jpg *.jpeg *.webp *.tif *.tiff)",
        )
        self.output = PathRow("Choose export folder", "directory")
        self.music_status = QLabel("Choose a music folder.")
        self.cover_status = QLabel("Choose artwork.")
        self.output_status = QLabel("Choose an export folder.")
        self.artwork_preview = QLabel("Artwork preview")
        self.artwork_preview.setFixedSize(104, 104)
        self.artwork_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork_preview.setWordWrap(True)
        self.artwork_preview.setStyleSheet(
            "QLabel { border: 1px solid palette(mid); border-radius: 8px; padding: 4px; }"
        )
        self.preview_audio = QPushButton("▶ Play First Track")
        self.preview_audio.setEnabled(False)
        self.preview_audio.clicked.connect(self.play_first_track)
        self.bass_effect = QCheckBox("Bass-reactive zoom blur")
        self.bass_effect.setChecked(True)
        self.pre_drop = QDoubleSpinBox()
        self.pre_drop.setRange(0.0, 60.0)
        self.pre_drop.setDecimals(1)
        self.pre_drop.setSingleStep(0.5)
        self.pre_drop.setSuffix(" seconds")
        self.pre_drop.setValue(2.0)

        input_form = QFormLayout()
        input_form.setSpacing(12)
        input_form.addRow("Music folder", self.music)
        input_form.addRow("", self.music_status)
        artwork_row = QWidget()
        artwork_layout = QHBoxLayout(artwork_row)
        artwork_layout.setContentsMargins(0, 0, 0, 0)
        artwork_layout.addWidget(self.cover, 1)
        artwork_layout.addWidget(self.artwork_preview)
        input_form.addRow("Artwork", artwork_row)
        input_form.addRow("", self.cover_status)
        input_form.addRow("Audio preview", self.preview_audio)
        input_form.addRow("Visual effect", self.bass_effect)
        input_form.addRow("Before detected drop", self.pre_drop)

        output_form = QFormLayout()
        output_form.setSpacing(12)
        output_form.addRow("Export folder", self.output)
        output_form.addRow("", self.output_status)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        self.generate = QPushButton("Generate Promo Videos")
        self.generate.setMinimumHeight(44)
        self.generate.setEnabled(False)
        self.generate.clicked.connect(self.start_generation)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        self.progress_status = QLabel("")
        self.progress_status.hide()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addWidget(section_group("Input", input_form))
        layout.addWidget(section_group("Output", output_form))
        layout.addWidget(divider)
        layout.addWidget(self.progress_status)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        actions.addWidget(self.clear_button)
        actions.addStretch()
        actions.addWidget(self.generate)
        layout.addLayout(actions)
        layout.addStretch()
        self.clips = ClipsTab(self.settings)
        self.about = AboutTab()
        tabs = QTabWidget()
        tabs.addTab(container, "Promo Videos")
        tabs.addTab(self.clips, "Livestream Clips")
        tabs.addTab(self.about, "About")
        self.setCentralWidget(tabs)

        self.music.changed.connect(self.validate)
        self.cover.changed.connect(self.validate)
        self.output.changed.connect(self.validate)
        self.restore_paths()
        self.validate()

    def restore_paths(self) -> None:
        for row, key in ((self.music, "music"), (self.cover, "cover"), (self.output, "output")):
            value = self.settings.value(key, "")
            if value and Path(value).exists():
                row.edit.setText(value)
        self.bass_effect.setChecked(self.settings.value("promo/bass_effect", True, type=bool))
        self.pre_drop.setValue(self.settings.value("promo/pre_drop", 2.0, type=float))

    def validate(self) -> bool:
        tracks = find_audio_files(self.music.path)
        music_ok = bool(tracks)
        self.music_status.setText(
            f"✓ Found {len(tracks)} supported audio file{'s' if len(tracks) != 1 else ''}."
            if music_ok
            else "No supported audio files found (WAV, AIFF, FLAC, MP3, M4A, AAC, OGG)."
        )
        cover_ok, cover_message = validate_cover(self.cover.path)
        self.cover_status.setText(("✓ " if cover_ok else "") + cover_message)
        self.update_artwork_preview(cover_ok)
        output_path = Path(self.output.path).expanduser() if self.output.path else None
        output_ok = bool(output_path and output_path.is_dir() and os.access(output_path, os.W_OK))
        self.output_status.setText("✓ Export folder is writable." if output_ok else "Choose a writable export folder.")
        ready = music_ok and cover_ok and output_ok and self.worker is None
        self.preview_audio.setEnabled(music_ok and self.worker is None)
        self.generate.setEnabled(ready)
        return ready

    def play_first_track(self) -> None:
        tracks = find_audio_files(self.music.path)
        if tracks:
            open_preview(self, tracks[0])

    def update_artwork_preview(self, cover_ok: bool) -> None:
        if not cover_ok:
            self.artwork_preview.setPixmap(QPixmap())
            self.artwork_preview.setText("Artwork preview")
            return
        pixmap = QPixmap(self.cover.path)
        self.artwork_preview.setText("")
        self.artwork_preview.setPixmap(
            pixmap.scaled(
                94,
                94,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def set_inputs_enabled(self, enabled: bool) -> None:
        for row in (self.music, self.cover, self.output):
            row.set_enabled(enabled)
        self.bass_effect.setEnabled(enabled)
        self.pre_drop.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        if not enabled:
            self.preview_audio.setEnabled(False)

    def clear(self) -> None:
        self.music.set_path("")
        self.cover.set_path("")
        self.output.set_path("")
        self.bass_effect.setChecked(True)
        self.pre_drop.setValue(2.0)
        self.progress.setValue(0)
        self.progress.hide()
        self.progress_status.clear()
        self.progress_status.hide()
        for key in ("music", "cover", "output", "promo/bass_effect", "promo/pre_drop"):
            self.settings.remove(key)
        self.validate()

    def start_generation(self) -> None:
        if not self.validate():
            return
        tracks = find_audio_files(self.music.path)
        for key, value in (("music", self.music.path), ("cover", self.cover.path), ("output", self.output.path)):
            self.settings.setValue(key, value)
        render_settings = RenderSettings(
            pre_drop=self.pre_drop.value(),
            bass_effect=self.bass_effect.isChecked(),
        )
        self.settings.setValue("promo/bass_effect", self.bass_effect.isChecked())
        self.settings.setValue("promo/pre_drop", self.pre_drop.value())
        self.worker = RenderWorker(
            tracks,
            Path(self.cover.path),
            Path(self.output.path),
            render_settings,
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.succeeded.connect(self.on_success)
        self.worker.failed.connect(self.on_failure)
        self.worker.finished.connect(self.worker_finished)
        self.progress.setValue(0)
        self.progress.show()
        self.progress_status.setText("Preparing…")
        self.progress_status.show()
        self.set_inputs_enabled(False)
        self.generate.setEnabled(False)
        self.worker.start()

    def on_progress(self, percent: int, status: str) -> None:
        self.progress.setValue(percent)
        self.progress_status.setText(status)

    def on_success(self, outputs: list[str]) -> None:
        QMessageBox.information(
            self,
            "Videos generated",
            f"Created {len(outputs)} promo video{'s' if len(outputs) != 1 else ''} in:\n{self.output.path}",
        )

    def on_failure(self, message: str) -> None:
        QMessageBox.critical(self, "Generation failed", message)

    def worker_finished(self) -> None:
        worker = self.worker
        self.worker = None
        self.set_inputs_enabled(True)
        self.validate()
        if worker:
            worker.deleteLater()

    def closeEvent(self, event):  # noqa: N802, ANN001
        promo_running = self.worker and self.worker.isRunning()
        clips_running = self.clips.worker and self.clips.worker.isRunning()
        if promo_running or clips_running:
            QMessageBox.warning(self, "Rendering in progress", "Wait for rendering to finish before closing the app.")
            event.ignore()
            return
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Media Tools for Record Labels")
    app.setOrganizationName("Media Tools for Record Labels")
    app.setWindowIcon(QIcon(os.fspath(bundled_asset("media-tools-app-icon.png"))))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
