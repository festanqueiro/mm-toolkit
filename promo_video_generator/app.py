"""Desktop interface for Media Tools for Record Labels."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
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


def open_preview(parent: QWidget, path: str | Path) -> None:
    target = Path(path).expanduser()
    if not target.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(target))):
        QMessageBox.warning(parent, "Preview unavailable", f"Could not open:\n{target}")


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

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Source video", self.source)
        form.addRow("", self.source_status)
        form.addRow("Preview", self.preview_source)
        form.addRow("Export folder", self.output)
        form.addRow("", self.output_status)

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
        layout.addLayout(form)
        layout.addWidget(QLabel("Clip timestamps"))
        layout.addWidget(self.table)
        layout.addWidget(self.add_button)
        layout.addWidget(self.clip_status)
        layout.addWidget(self.progress_status)
        layout.addWidget(self.progress)
        layout.addWidget(self.generate)

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
        if not enabled:
            self.preview_source.setEnabled(False)

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: RenderWorker | None = None
        self.settings = QSettings("Record Label Media Tools", "Media Tools for Record Labels")
        self.setWindowTitle("Media Tools for Record Labels")
        self.setMinimumSize(780, 570)

        title = QLabel("Promo Videos")
        title.setFont(QFont("", 24, QFont.Weight.DemiBold))
        subtitle = QLabel("Turn audio masters and cover artwork into square promo videos.")
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
        self.preview_artwork = QPushButton("View Artwork")
        self.preview_artwork.setEnabled(False)
        self.preview_artwork.clicked.connect(lambda: open_preview(self, self.cover.path))
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

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Music folder", self.music)
        form.addRow("", self.music_status)
        form.addRow("Artwork", self.cover)
        form.addRow("", self.cover_status)
        preview_row = QWidget()
        preview_layout = QHBoxLayout(preview_row)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self.preview_artwork)
        preview_layout.addWidget(self.preview_audio)
        preview_layout.addStretch()
        form.addRow("Preview", preview_row)
        form.addRow("Export folder", self.output)
        form.addRow("", self.output_status)
        form.addRow("Visual effect", self.bass_effect)
        form.addRow("Before detected drop", self.pre_drop)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        self.generate = QPushButton("Generate Promo Videos")
        self.generate.setMinimumHeight(44)
        self.generate.setEnabled(False)
        self.generate.clicked.connect(self.start_generation)
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
        layout.addLayout(form)
        layout.addWidget(divider)
        layout.addWidget(self.progress_status)
        layout.addWidget(self.progress)
        layout.addWidget(self.generate)
        layout.addStretch()
        self.clips = ClipsTab(self.settings)
        tabs = QTabWidget()
        tabs.addTab(container, "Promo Videos")
        tabs.addTab(self.clips, "Livestream Clips")
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
        output_path = Path(self.output.path).expanduser() if self.output.path else None
        output_ok = bool(output_path and output_path.is_dir() and os.access(output_path, os.W_OK))
        self.output_status.setText("✓ Export folder is writable." if output_ok else "Choose a writable export folder.")
        ready = music_ok and cover_ok and output_ok and self.worker is None
        self.preview_artwork.setEnabled(cover_ok and self.worker is None)
        self.preview_audio.setEnabled(music_ok and self.worker is None)
        self.generate.setEnabled(ready)
        return ready

    def play_first_track(self) -> None:
        tracks = find_audio_files(self.music.path)
        if tracks:
            open_preview(self, tracks[0])

    def set_inputs_enabled(self, enabled: bool) -> None:
        for row in (self.music, self.cover, self.output):
            row.set_enabled(enabled)
        self.bass_effect.setEnabled(enabled)
        self.pre_drop.setEnabled(enabled)
        if not enabled:
            self.preview_artwork.setEnabled(False)
            self.preview_audio.setEnabled(False)

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
    app.setOrganizationName("Record Label Media Tools")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
