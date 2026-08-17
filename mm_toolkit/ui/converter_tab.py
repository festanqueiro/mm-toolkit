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


class ConverterWorker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(list)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(self, sources: list[Path], output: Path, output_format: str, conflict: str, audio_bitrate: str):
        super().__init__()
        self.sources = sources
        self.output = output
        self.output_format = output_format
        self.conflict = conflict
        self.audio_bitrate = audio_bitrate

    def run(self) -> None:
        try:
            results = convert_media(
                self.sources,
                self.output,
                self.output_format,
                lambda percent, status: self.progress.emit(percent, status),
                self.conflict,
                self.isInterruptionRequested,
                self.audio_bitrate,
            )
            self.succeeded.emit([os.fspath(path) for path in results])
        except CancelledError:
            self.cancelled.emit()
        except Exception as exc:
            details = traceback.format_exc()
            print(details, file=sys.stderr)
            self.failed.emit(str(exc), details)


class ConverterTab(QWidget):
    job_completed = Signal(object)

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.worker: ConverterWorker | None = None
        title = page_title("Media Converter")
        subtitle = QLabel("Convert batches of audio or video files into another common format.")
        self.files = QListWidget()
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.choose_button = QPushButton("Choose Audio or Video Files…")
        self.choose_button.clicked.connect(self.choose_files)
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self.remove_selected)
        self.preview_button = QPushButton("▶ Preview Selected")
        self.preview_button.clicked.connect(self.preview_selected)
        self.input_status = QLabel("")
        self.input_status.setWordWrap(True)
        self.media_type = QLabel("Not detected")
        self.output_format = QComboBox()
        self.output_format.currentIndexChanged.connect(self.validate)
        self.mp3_bitrate = QComboBox()
        for bitrate in ("128k", "192k", "256k", "320k"):
            self.mp3_bitrate.addItem(f"{bitrate[:-1]} kbps", bitrate)
        self.mp3_bitrate.setCurrentIndex(self.mp3_bitrate.findData("320k"))
        self.mp3_bitrate.currentIndexChanged.connect(self.validate)
        self.mp3_bitrate_label = QLabel("MP3 bitrate")
        self.output = PathRow("Choose media converter export folder", "directory")
        self.output.changed.connect(self.validate)
        self.output_status = QLabel("")
        self.output_status.setWordWrap(True)

        input_layout = QVBoxLayout()
        input_layout.addWidget(self.choose_button)
        input_layout.addWidget(self.files, 1)
        input_actions = QHBoxLayout()
        input_actions.addWidget(self.remove_button)
        input_actions.addWidget(self.preview_button)
        input_layout.addLayout(input_actions)
        input_layout.addWidget(self.input_status)
        output_form = QFormLayout()
        output_form.setSpacing(12)
        output_form.addRow("Detected media", self.media_type)
        output_form.addRow("Convert to", self.output_format)
        output_form.addRow(self.mp3_bitrate_label, self.mp3_bitrate)
        output_form.addRow("Export folder", self.output)
        output_form.addRow("", self.output_status)

        self.progress_status = QLabel("")
        self.progress_status.hide()
        self.progress = QProgressBar()
        self.progress.hide()
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.hide()
        self.requirements = QLabel("")
        self.requirements.setWordWrap(True)
        self.convert_button = QPushButton("Convert Files")
        self.convert_button.setMinimumHeight(44)
        self.convert_button.clicked.connect(self.start_conversion)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        columns = QHBoxLayout()
        columns.setSpacing(14)
        columns.addWidget(section_group("Input", input_layout), 1)
        output_column = QVBoxLayout()
        self.converter_output_group = section_group("Output", output_form)
        output_column.addWidget(self.converter_output_group)
        output_column.addStretch()
        columns.addLayout(output_column, 1)
        layout.addLayout(columns, 1)
        layout.addWidget(self.progress_status)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        actions.addWidget(self.clear_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.requirements, 1)
        actions.addWidget(self.convert_button)
        layout.addLayout(actions)

        default_output = self.settings.value("general/default_output", "")
        if default_output and Path(default_output).is_dir():
            self.output.edit.setText(default_output)
        self.update_formats(None)
        self.validate()

    def source_paths(self) -> list[Path]:
        return [Path(self.files.item(index).data(Qt.ItemDataRole.UserRole)) for index in range(self.files.count())]

    def set_files(self, paths: list[str | Path]) -> None:
        self.files.clear()
        for path in paths:
            source = Path(path)
            item = QListWidgetItem(source.name)
            item.setToolTip(os.fspath(source))
            item.setData(Qt.ItemDataRole.UserRole, os.fspath(source))
            self.files.addItem(item)
        if self.files.count():
            self.files.setCurrentRow(0)
        self.validate()

    def choose_files(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose audio or video files",
            str(Path.home()),
            "Media (*.mp3 *.wav *.wave *.aif *.aiff *.flac *.m4a *.aac *.ogg *.mp4 *.mov *.m4v *.mkv *.avi *.webm)",
        )
        if selected:
            self.set_files(selected)

    def remove_selected(self) -> None:
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))
        self.validate()

    def preview_selected(self) -> None:
        item = self.files.currentItem()
        if item:
            open_preview(self, item.data(Qt.ItemDataRole.UserRole))

    def update_formats(self, kind: str | None) -> None:
        previous = self.output_format.currentText().lower()
        formats = AUDIO_OUTPUT_FORMATS if kind == "audio" else VIDEO_OUTPUT_FORMATS if kind == "video" else ()
        self.output_format.blockSignals(True)
        self.output_format.clear()
        for output_format in formats:
            self.output_format.addItem(output_format.upper(), output_format)
        index = self.output_format.findData(previous)
        self.output_format.setCurrentIndex(index if index >= 0 else 0)
        self.output_format.blockSignals(False)

    def validate(self) -> bool:
        sources = self.source_paths()
        kinds = {media_kind(path) for path in sources if path.is_file()}
        kind = next(iter(kinds)) if len(kinds) == 1 and None not in kinds and len(sources) == sum(path.is_file() for path in sources) else None
        self.converter_output_group.setEnabled(kind is not None and self.worker is None)
        mixed = len(kinds) > 1 or None in kinds
        current_kind = self.output_format.property("media_kind")
        if current_kind != kind:
            self.update_formats(kind)
            self.output_format.setProperty("media_kind", kind)
        if not sources:
            input_message = ""
        elif mixed:
            input_message = "Audio and video files cannot be mixed in one batch."
        elif kind is None:
            input_message = "One or more selected files cannot be used."
        else:
            input_message = f"✓ {len(sources)} {kind} file{'s' if len(sources) != 1 else ''} ready."
        self.input_status.setText(input_message)
        self.input_status.setVisible(bool(input_message))
        self.media_type.setText(kind.title() if kind else "Not detected")
        mp3_selected = kind == "audio" and self.output_format.currentData() == "mp3"
        self.mp3_bitrate_label.setVisible(mp3_selected)
        self.mp3_bitrate.setVisible(mp3_selected)
        output_path = Path(self.output.path).expanduser() if self.output.path else None
        output_ok = bool(output_path and output_path.is_dir() and os.access(output_path, os.W_OK))
        output_status = "✓ Export folder is writable." if output_ok else "Export folder is not writable." if self.output.path else ""
        self.output_status.setText(output_status)
        self.output_status.setVisible(bool(output_status))
        missing = []
        if kind is None:
            missing.append("choose a valid audio-only or video-only batch")
        if not output_ok:
            missing.append("choose a writable export folder")
        if self.worker:
            message = "Converting files…"
        elif missing:
            message = "To enable Convert: " + "; ".join(missing) + "."
        else:
            bitrate = f" at {self.mp3_bitrate.currentText()}" if mp3_selected else ""
            message = f"✓ Ready to convert {len(sources)} file{'s' if len(sources) != 1 else ''} to {self.output_format.currentText()}{bitrate}."
        self.requirements.setText(message)
        ready = kind is not None and output_ok and self.output_format.count() > 0 and self.worker is None
        self.convert_button.setEnabled(ready)
        self.preview_button.setEnabled(bool(sources) and self.worker is None)
        self.remove_button.setEnabled(bool(sources) and self.worker is None)
        return ready

    def set_inputs_enabled(self, enabled: bool) -> None:
        self.choose_button.setEnabled(enabled)
        self.files.setEnabled(enabled)
        self.converter_output_group.setEnabled(enabled and self.output_format.count() > 0)
        self.output_format.setEnabled(enabled)
        self.mp3_bitrate.setEnabled(enabled)
        self.output.set_enabled(enabled)
        self.clear_button.setEnabled(enabled)
        if not enabled:
            self.preview_button.setEnabled(False)
            self.remove_button.setEnabled(False)

    def clear(self) -> None:
        self.files.clear()
        self.output.set_path(self.settings.value("general/default_output", ""))
        self.progress.hide()
        self.progress_status.hide()
        self.validate()

    def cancel(self) -> None:
        if self.worker:
            self.cancel_button.setEnabled(False)
            self.progress_status.setText("Cancelling safely…")
            self.worker.requestInterruption()

    def start_conversion(self) -> None:
        if not self.validate():
            return
        sources = self.source_paths()
        self.worker = ConverterWorker(
            sources,
            Path(self.output.path),
            self.output_format.currentData(),
            self.settings.value("general/conflict_policy", "rename"),
            self.mp3_bitrate.currentData(),
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.succeeded.connect(self.on_success)
        self.worker.failed.connect(self.on_failure)
        self.worker.cancelled.connect(self.on_cancelled)
        self.worker.finished.connect(self.worker_finished)
        self.progress.setValue(0)
        self.progress.show()
        self.progress_status.setText("Preparing conversion…")
        self.progress_status.show()
        self.set_inputs_enabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.convert_button.setEnabled(False)
        self.worker.start()

    def on_progress(self, percent: int, status: str) -> None:
        self.progress.setValue(percent)
        self.progress_status.setText(status)

    def on_success(self, outputs: list[str]) -> None:
        self.job_completed.emit({
            "tool": "converter",
            "created": datetime.now().isoformat(timespec="seconds"),
            "source": os.fspath(self.source_paths()[0]) if self.source_paths() else "",
            "sources": [os.fspath(path) for path in self.source_paths()],
            "output": self.output.path,
            "format": self.output_format.currentData(),
            "bitrate": self.mp3_bitrate.currentData(),
            "outputs": outputs,
        })
        if self.settings.value("general/notify_finished", True, type=bool):
            show_completion(self, "Conversion finished", outputs)

    def on_failure(self, message: str, details: str) -> None:
        show_error(self, "Conversion failed", message, details)

    def on_cancelled(self) -> None:
        self.progress_status.setText("Conversion cancelled. Partial files were removed.")

    def worker_finished(self) -> None:
        worker = self.worker
        self.worker = None
        self.set_inputs_enabled(True)
        self.cancel_button.hide()
        self.validate()
        if worker:
            worker.deleteLater()
