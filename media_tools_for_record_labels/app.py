"""Desktop interface for Media Tools for Record Labels."""

from __future__ import annotations

import os
import json
import shutil
import sys
import traceback
from pathlib import Path
from datetime import datetime

import cv2
from PySide6.QtCore import QByteArray, QSettings, QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import (
    AUDIO_OUTPUT_FORMATS,
    CancelledError,
    ClipRequest,
    RenderSettings,
    VIDEO_OUTPUT_FORMATS,
    convert_media,
    cut_video_clips,
    detect_drop_starts,
    find_audio_files,
    format_timestamp,
    generate_videos,
    media_kind,
    parse_timestamp,
    validate_visual,
    validate_video,
)
from . import __version__


def open_preview(parent: QWidget, path: str | Path) -> None:
    target = Path(path).expanduser()
    if not target.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(target))):
        QMessageBox.warning(parent, "Preview unavailable", f"Could not open:\n{target}")


def show_error(parent: QWidget, title: str, message: str, details: str) -> None:
    box = QMessageBox(QMessageBox.Icon.Critical, title, message, parent=parent)
    box.setDetailedText(details)
    box.exec()


def show_completion(parent: QWidget, title: str, outputs: list[str]) -> None:
    if not outputs:
        QMessageBox.information(parent, title, "No new files were created.")
        return
    box = QMessageBox(QMessageBox.Icon.Information, title, f"Created {len(outputs)} file{'s' if len(outputs) != 1 else ''}.", parent=parent)
    open_file = box.addButton("Open First File", QMessageBox.ButtonRole.ActionRole)
    show_folder = box.addButton("Show in Folder", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Ok)
    box.exec()
    if box.clickedButton() is open_file:
        open_preview(parent, outputs[0])
    elif box.clickedButton() is show_folder:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(Path(outputs[0]).parent)))


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


def page_title(text: str) -> QLabel:
    title = QLabel(text)
    title.setFont(QFont("", 24, QFont.Weight.DemiBold))
    return title


def material_icon(name: str, color: str) -> QIcon:
    svg = bundled_asset(f"material-icons/{name}.svg").read_text(encoding="utf-8")
    svg = svg.replace("<svg ", f'<svg fill="{color}" ', 1)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class RenderWorker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(list)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(self, tracks: list[Path], cover: Path, output: Path, settings: RenderSettings, naming: str, conflict: str, track_options: dict[Path, tuple[float, float]]):
        super().__init__()
        self.tracks = tracks
        self.cover = cover
        self.output = output
        self.settings = settings
        self.naming = naming
        self.conflict = conflict
        self.track_options = track_options

    def run(self) -> None:
        try:
            results = generate_videos(
                self.tracks,
                self.cover,
                self.output,
                self.settings,
                lambda percent, status: self.progress.emit(percent, status),
                self.naming,
                self.conflict,
                self.isInterruptionRequested,
                self.track_options,
            )
            self.succeeded.emit([os.fspath(path) for path in results])
        except CancelledError:
            self.cancelled.emit()
        except Exception as exc:
            details = traceback.format_exc()
            print(details, file=sys.stderr)
            self.failed.emit(str(exc), details)


class DropDetectionWorker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, sources: list[Path], seconds_before: float):
        super().__init__()
        self.sources = sources
        self.seconds_before = seconds_before

    def run(self) -> None:
        try:
            starts = detect_drop_starts(
                self.sources,
                self.seconds_before,
                lambda percent, status: self.progress.emit(percent, status),
                self.isInterruptionRequested,
            )
            self.succeeded.emit({os.fspath(path): start for path, start in starts.items()})
        except CancelledError:
            pass
        except Exception as exc:
            self.failed.emit(str(exc))


class ClipWorker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(list)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(self, source: Path, clips: list[ClipRequest], output: Path, naming: str, conflict: str):
        super().__init__()
        self.source = source
        self.clips = clips
        self.output = output
        self.naming = naming
        self.conflict = conflict

    def run(self) -> None:
        try:
            results = cut_video_clips(
                self.source,
                self.clips,
                self.output,
                lambda percent, status: self.progress.emit(percent, status),
                self.naming,
                self.conflict,
                self.isInterruptionRequested,
            )
            self.succeeded.emit([os.fspath(path) for path in results])
        except CancelledError:
            self.cancelled.emit()
        except Exception as exc:
            details = traceback.format_exc()
            print(details, file=sys.stderr)
            self.failed.emit(str(exc), details)


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
        self.directory_button: QPushButton | None = None
        if self.mode == "file_or_directory":
            self.button.setText("Choose File…")
            self.directory_button = QPushButton("Choose Folder…")
            self.directory_button.clicked.connect(self.choose_directory)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)
        if self.directory_button:
            layout.addWidget(self.directory_button)

    @property
    def path(self) -> str:
        return self.edit.text()

    def set_path(self, path: str) -> None:
        self.edit.setText(path)
        self.changed.emit(path)

    def choose(self) -> None:
        start = self.path or str(Path.home())
        if self.mode in {"file", "file_or_directory"}:
            selected, _ = QFileDialog.getOpenFileName(self, self.dialog_title, start, self.file_filter)
        else:
            selected = QFileDialog.getExistingDirectory(self, self.dialog_title, start)
        if selected:
            self.set_path(selected)

    def choose_directory(self) -> None:
        current = Path(self.path).expanduser() if self.path else Path.home()
        start = current.parent if current.is_file() else current
        selected = QFileDialog.getExistingDirectory(self, "Choose folder containing audio", os.fspath(start))
        if selected:
            self.set_path(selected)

    def set_enabled(self, enabled: bool) -> None:
        self.button.setEnabled(enabled)
        if self.directory_button:
            self.directory_button.setEnabled(enabled)


class ClipField(QLineEdit):
    focused = Signal()

    def focusInEvent(self, event) -> None:  # noqa: N802, ANN001
        super().focusInEvent(event)
        self.focused.emit()


class ClipsTab(QWidget):
    job_completed = Signal(object)
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.worker: ClipWorker | None = None
        title = page_title("Livestream Clips")
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
        self.source_status = QLabel("")
        self.output_status = QLabel("")
        self.preview_source = QPushButton("▶ Play Source Video")
        self.preview_source.setEnabled(False)
        self.preview_source.clicked.connect(lambda: open_preview(self, self.source.path))
        self.player = QMediaPlayer(self)
        self.player_audio = QAudioOutput(self)
        self.player.setAudioOutput(self.player_audio)
        self.video_preview = QVideoWidget()
        self.video_preview.setMinimumHeight(170)
        self.player.setVideoOutput(self.video_preview)
        self.play_button = QPushButton("▶ Play")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle_playback)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.sliderMoved.connect(self.player.setPosition)
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.set_start_button = QPushButton("Set Start")
        self.set_end_button = QPushButton("Set End")
        self.active_clip_label = QLabel("Editing Clip 1")
        self.active_clip_label.setStyleSheet("font-weight: 600; color: palette(highlight);")
        self.set_start_button.clicked.connect(lambda: self.set_timestamp(1))
        self.set_end_button.clicked.connect(lambda: self.set_timestamp(2))
        self.player.positionChanged.connect(self.on_player_position)
        self.player.durationChanged.connect(self.on_player_duration)
        self.player.playbackStateChanged.connect(self.on_playback_state)

        input_form = QFormLayout()
        input_form.setSpacing(10)
        input_form.addRow("Source video", self.source)
        input_form.addRow("", self.source_status)
        input_form.addRow("Preview", self.preview_source)

        output_form = QFormLayout()
        output_form.setSpacing(10)
        output_form.addRow("Export folder", self.output)
        output_form.addRow("", self.output_status)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Title", "Start", "End (optional)", "Duration", ""])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.currentCellChanged.connect(self.update_active_clip)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(150)
        self.add_button = QPushButton("+ Add clip")
        self.add_button.clicked.connect(lambda: self.add_row())
        self.clip_status = QLabel("")
        self.generate = QPushButton("Create Clips")
        self.generate.setMinimumHeight(44)
        self.generate.clicked.connect(self.start_generation)
        self.generate_requirements = QLabel("")
        self.generate_requirements.setWordWrap(True)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancel)
        self.progress_status = QLabel("")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        self.progress_status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        clip_input_layout = QVBoxLayout()
        clip_input_layout.addLayout(input_form)
        clip_input_layout.addWidget(self.video_preview)
        timeline_row = QHBoxLayout()
        timeline_row.addWidget(self.timeline, 1)
        timeline_row.addWidget(self.time_label)
        clip_input_layout.addLayout(timeline_row)
        clip_input_layout.addWidget(self.active_clip_label)
        playback_actions = QHBoxLayout()
        playback_actions.addWidget(self.play_button)
        playback_actions.addStretch()
        playback_actions.addWidget(self.set_start_button)
        playback_actions.addWidget(self.set_end_button)
        clip_input_layout.addLayout(playback_actions)
        timestamps_layout = QVBoxLayout()
        timestamps_layout.addWidget(self.table)
        timestamps_layout.addWidget(self.add_button)
        timestamps_layout.addWidget(self.clip_status)
        right_column = QVBoxLayout()
        right_column.addWidget(section_group("Clip timestamps", timestamps_layout), 1)
        right_column.addWidget(section_group("Output", output_form))
        feature_columns = QHBoxLayout()
        feature_columns.setSpacing(14)
        feature_columns.addWidget(section_group("Input", clip_input_layout), 1)
        feature_columns.addLayout(right_column, 1)
        layout.addLayout(feature_columns, 1)
        layout.addWidget(self.progress_status)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        actions.addWidget(self.clear_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.generate_requirements, 1)
        actions.addWidget(self.generate)
        layout.addLayout(actions)

        self.source.changed.connect(self.validate)
        self.source.changed.connect(self.load_video_preview)
        self.output.changed.connect(self.validate)
        for row, key in ((self.source, "clips/source"), (self.output, "clips/output")):
            value = self.settings.value(key, "")
            if value and Path(value).exists():
                row.edit.setText(value)
        self.add_row()
        self.validate()

    def add_row(self, title: str = "", start: str = "00:00:00", end: str = "", duration: str = "60") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value, placeholder in (
            (0, title, f"Clip {row + 1:02d}"),
            (1, start, "Required, e.g. 00:03:15"),
            (2, end, "Optional"),
            (3, duration, "60"),
        ):
            edit = ClipField(value)
            edit.setPlaceholderText(placeholder)
            edit.textChanged.connect(self.validate)
            edit.focused.connect(lambda row=row, column=column: self.table.setCurrentCell(row, column))
            self.table.setCellWidget(row, column, edit)
        remove = QPushButton("Remove")
        remove.clicked.connect(lambda _checked=False, button=remove: self.remove_row(button))
        self.table.setCellWidget(row, 4, remove)
        self.table.setCurrentCell(row, 0)
        self.validate()

    def update_active_clip(self, current_row: int, _current_column: int, _previous_row: int, _previous_column: int) -> None:
        if current_row < 0:
            self.active_clip_label.setText("Select a clip to edit")
            return
        title = self.table.cellWidget(current_row, 0).text().strip() or f"Clip {current_row + 1:02d}"
        self.active_clip_label.setText(f"Editing Clip {current_row + 1}: {title} — Set Start/End updates this row")
        for row in range(self.table.rowCount()):
            style = "border: 2px solid palette(highlight); border-radius: 4px;" if row == current_row else ""
            for column in range(self.table.columnCount()):
                widget = self.table.cellWidget(row, column)
                if widget:
                    widget.setStyleSheet(style)

    def remove_row(self, button: QPushButton) -> None:
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 4) is button:
                self.table.removeRow(row)
                break
        if self.table.rowCount() == 0:
            self.add_row()
        self.validate()

    def parsed_clips(self) -> tuple[list[ClipRequest], str]:
        clips: list[ClipRequest] = []
        for row in range(self.table.rowCount()):
            title_text = self.table.cellWidget(row, 0).text().strip()
            start_text = self.table.cellWidget(row, 1).text().strip()
            end_text = self.table.cellWidget(row, 2).text().strip()
            duration_text = self.table.cellWidget(row, 3).text().strip()
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
            clips.append(ClipRequest(start, duration, title_text))
        return clips, f"✓ {len(clips)} clip{'s' if len(clips) != 1 else ''} ready."

    def load_video_preview(self, path: str) -> None:
        valid, _ = validate_video(path)
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path) if valid else QUrl())
        self.play_button.setEnabled(valid and self.worker is None)

    def toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def on_playback_state(self, state) -> None:  # noqa: ANN001
        self.play_button.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "▶ Play")

    def on_player_position(self, position: int) -> None:
        if not self.timeline.isSliderDown():
            self.timeline.setValue(position)
        self.time_label.setText(
            f"{format_timestamp(position / 1000)} / {format_timestamp(self.player.duration() / 1000)}"
        )

    def on_player_duration(self, duration: int) -> None:
        self.timeline.setRange(0, max(0, duration))
        self.on_player_position(self.player.position())

    def set_timestamp(self, column: int) -> None:
        row = self.table.currentRow()
        if row < 0:
            row = 0
            self.table.selectRow(row)
        self.table.cellWidget(row, column).setText(format_timestamp(self.player.position() / 1000))

    def validate(self) -> bool:
        source_ok, source_message = validate_video(self.source.path)
        source_status = (("✓ " if source_ok else "") + source_message) if self.source.path else ""
        self.source_status.setText(source_status)
        self.source_status.setVisible(bool(source_status))
        output_path = Path(self.output.path).expanduser() if self.output.path else None
        output_ok = bool(output_path and output_path.is_dir() and os.access(output_path, os.W_OK))
        output_status = "✓ Export folder is writable." if output_ok else "Export folder is not writable." if self.output.path else ""
        self.output_status.setText(output_status)
        self.output_status.setVisible(bool(output_status))
        clips, clip_message = self.parsed_clips()
        self.clip_status.setText(clip_message)
        ready = source_ok and output_ok and bool(clips) and self.worker is None
        missing = []
        if not source_ok:
            missing.append("choose a valid source video")
        if not clips:
            missing.append(clip_message.rstrip("."))
        if not output_ok:
            missing.append("choose a writable export folder")
        if self.worker is not None:
            action_message = "Creating clips…"
        elif missing:
            action_message = "To enable Create Clips: " + "; ".join(missing) + "."
        else:
            action_message = "✓ Ready to create clips."
        self.generate_requirements.setText(action_message)
        self.generate.setToolTip(action_message)
        self.preview_source.setEnabled(source_ok and self.worker is None)
        self.generate.setEnabled(ready)
        return ready

    def set_inputs_enabled(self, enabled: bool) -> None:
        self.source.set_enabled(enabled)
        self.output.set_enabled(enabled)
        self.add_button.setEnabled(enabled)
        self.table.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.play_button.setEnabled(enabled and bool(self.source.path))
        self.timeline.setEnabled(enabled)
        self.set_start_button.setEnabled(enabled)
        self.set_end_button.setEnabled(enabled)
        if not enabled:
            self.preview_source.setEnabled(False)

    def cancel(self) -> None:
        if self.worker:
            self.cancel_button.setEnabled(False)
            self.progress_status.setText("Cancelling safely…")
            self.worker.requestInterruption()

    def clear(self) -> None:
        self.source.set_path("")
        self.player.stop()
        self.output.set_path(self.settings.value("general/default_output", ""))
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
        self.worker = ClipWorker(
            Path(self.source.path), clips, Path(self.output.path),
            self.settings.value("general/clip_naming", "{source} - {title}"),
            self.settings.value("general/conflict_policy", "rename"),
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.succeeded.connect(self.on_success)
        self.worker.failed.connect(self.on_failure)
        self.worker.cancelled.connect(self.on_cancelled)
        self.worker.finished.connect(self.worker_finished)
        self.progress.setValue(0)
        self.progress.show()
        self.progress_status.setText("Preparing clips…")
        self.progress_status.show()
        self.set_inputs_enabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.generate.setEnabled(False)
        self.worker.start()

    def on_progress(self, percent: int, status: str) -> None:
        self.progress.setValue(percent)
        self.progress_status.setText(status)

    def on_success(self, outputs: list[str]) -> None:
        self.job_completed.emit({
            "tool": "clips",
            "created": datetime.now().isoformat(timespec="seconds"),
            "source": self.source.path,
            "output": self.output.path,
            "clips": [
                {"title": clip.title, "start": clip.start, "duration": clip.duration}
                for clip in self.parsed_clips()[0]
            ],
            "outputs": outputs,
        })
        if self.settings.value("general/notify_finished", True, type=bool):
            show_completion(self, "Clips created", outputs)

    def on_failure(self, message: str, details: str) -> None:
        show_error(self, "Clip creation failed", message, details)

    def on_cancelled(self) -> None:
        self.progress_status.setText("Cancelled. Partial files were removed.")

    def worker_finished(self) -> None:
        worker = self.worker
        self.worker = None
        self.set_inputs_enabled(True)
        self.cancel_button.hide()
        self.validate()
        if worker:
            worker.deleteLater()


class ConverterTab(QWidget):
    job_completed = Signal(object)

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.worker: ConverterWorker | None = None
        title = page_title("Converter")
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
        self.output = PathRow("Choose converter export folder", "directory")
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
        output_column.addWidget(section_group("Output", output_form))
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


class SettingsTab(QWidget):
    changed = Signal()

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        title = page_title("Settings")
        subtitle = QLabel("Defaults shared by all Media Tools features.")
        self.default_output = PathRow("Choose default export folder", "directory")
        self.output_status = QLabel("")
        self.notify_finished = QCheckBox("Show a popup when processing finishes")
        self.notify_finished.setChecked(
            self.settings.value("general/notify_finished", True, type=bool)
        )
        self.promo_naming = QLineEdit(
            self.settings.value("general/promo_naming", "{track} - Promo Snippet")
        )
        self.clip_naming = QLineEdit(
            self.settings.value("general/clip_naming", "{source} - {title}")
        )
        self.conflict_policy = QComboBox()
        for label, value in (("Create a numbered copy", "rename"), ("Overwrite", "overwrite"), ("Skip", "skip")):
            self.conflict_policy.addItem(label, value)
        saved_conflict = self.settings.value("general/conflict_policy", "rename")
        self.conflict_policy.setCurrentIndex(max(0, self.conflict_policy.findData(saved_conflict)))
        saved_output = self.settings.value("general/default_output", "")
        if saved_output and Path(saved_output).is_dir():
            self.default_output.edit.setText(saved_output)

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Default Folder for Export", self.default_output)
        form.addRow("", self.output_status)
        form.addRow("Notifications", self.notify_finished)
        form.addRow("Generated video filename", self.promo_naming)
        form.addRow("Clip filename", self.clip_naming)
        form.addRow("Existing files", self.conflict_policy)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(section_group("General", form))
        layout.addStretch()

        self.default_output.changed.connect(self.save)
        self.notify_finished.toggled.connect(self.save)
        self.promo_naming.editingFinished.connect(self.save)
        self.clip_naming.editingFinished.connect(self.save)
        self.conflict_policy.currentIndexChanged.connect(self.save)
        self.validate()

    def validate(self) -> None:
        path = Path(self.default_output.path).expanduser() if self.default_output.path else None
        valid = bool(path and path.is_dir() and os.access(path, os.W_OK))
        self.output_status.setText(
            "✓ Default export folder is writable."
            if valid
            else "Optional: choose a writable folder to prefill exports."
        )

    def save(self, *_args) -> None:  # noqa: ANN002
        path = self.default_output.path
        if path and Path(path).is_dir() and os.access(path, os.W_OK):
            self.settings.setValue("general/default_output", path)
        elif not path:
            self.settings.remove("general/default_output")
        self.settings.setValue("general/notify_finished", self.notify_finished.isChecked())
        self.settings.setValue("general/promo_naming", self.promo_naming.text().strip() or "{track} - Promo Snippet")
        self.settings.setValue("general/clip_naming", self.clip_naming.text().strip() or "{source} - {title}")
        self.settings.setValue("general/conflict_policy", self.conflict_policy.currentData())
        self.validate()
        self.changed.emit()


class AboutTab(QWidget):
    def __init__(self):
        super().__init__()
        page_heading = page_title("About")
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
            "Open-source desktop utilities for generating music videos "
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
        icon_credit = QLabel(
            '<a href="https://fonts.google.com/icons">Google Material Icons</a> '
            "used under the Apache License 2.0."
        )
        icon_credit.setOpenExternalLinks(True)
        icon_credit.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(page_heading)
        layout.addStretch()
        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addWidget(repository)
        layout.addWidget(icon_credit)
        layout.addStretch()


class HistoryTab(QWidget):
    load_requested = Signal(object)

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        title = page_title("History")
        subtitle = QLabel("Recent jobs are stored only in your local application settings.")
        self.jobs = QListWidget()
        self.load_button = QPushButton("Load Job")
        self.open_button = QPushButton("Show Output Folder")
        self.clear_button = QPushButton("Clear History")
        self.load_button.clicked.connect(self.load_selected)
        self.open_button.clicked.connect(self.open_selected)
        self.clear_button.clicked.connect(self.clear)
        actions = QHBoxLayout()
        actions.addWidget(self.clear_button)
        actions.addStretch()
        actions.addWidget(self.open_button)
        actions.addWidget(self.load_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.jobs, 1)
        layout.addLayout(actions)
        self.records: list[dict] = []
        self.refresh()

    def refresh(self) -> None:
        try:
            self.records = json.loads(self.settings.value("history/jobs", "[]"))
        except (TypeError, json.JSONDecodeError):
            self.records = []
        self.jobs.clear()
        for record in self.records:
            tool = {
                "promo": "Video Generator",
                "clips": "Livestream Clips",
                "converter": "Converter",
            }.get(record.get("tool"), "Media Tool")
            source = Path(record.get("source", "")).name or "Unknown input"
            self.jobs.addItem(f"{record.get('created', '')}  •  {tool}  •  {source}")
        enabled = bool(self.records)
        self.load_button.setEnabled(enabled)
        self.open_button.setEnabled(enabled)

    def selected_record(self) -> dict | None:
        row = self.jobs.currentRow()
        if row < 0 and self.records:
            row = 0
        return self.records[row] if 0 <= row < len(self.records) else None

    def load_selected(self) -> None:
        record = self.selected_record()
        if record:
            self.load_requested.emit(record)

    def open_selected(self) -> None:
        record = self.selected_record()
        if record and Path(record.get("output", "")).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(record["output"]))

    def clear(self) -> None:
        self.settings.remove("history/jobs")
        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: RenderWorker | None = None
        self.analysis_worker: DropDetectionWorker | None = None
        self.pending_drop_detection = False
        self.settings = QSettings("Media Tools for Record Labels", "Media Tools for Record Labels")
        self.setWindowTitle("Media Tools for Record Labels")
        self.setMinimumSize(820, 620)
        self.resize(1100, 820)

        title = page_title("Video Generator")
        subtitle = QLabel("Turn audio plus an image or video into a new music video at the visual's native resolution.")
        subtitle.setWordWrap(True)

        self.music = PathRow(
            "Choose audio file or folder",
            "file_or_directory",
            "Audio (*.wav *.wave *.aif *.aiff *.flac *.mp3 *.m4a *.aac *.ogg)",
        )
        self.cover = PathRow(
            "Choose image or video",
            "file",
            "Visuals (*.png *.jpg *.jpeg *.webp *.tif *.tiff *.mp4 *.mov *.m4v *.mkv *.avi *.webm)",
        )
        self.output = PathRow("Choose export folder", "directory")
        self.music_status = QLabel("")
        self.cover_status = QLabel("")
        self.output_status = QLabel("")
        self.music_status.setWordWrap(True)
        self.cover_status.setWordWrap(True)
        self.output_status.setWordWrap(True)
        self.artwork_preview = QLabel("Visual preview")
        self.artwork_preview.setFixedSize(104, 104)
        self.artwork_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork_preview.setWordWrap(True)
        self.artwork_preview.setStyleSheet(
            "QLabel { border: 1px solid palette(mid); border-radius: 8px; padding: 4px; }"
        )
        self.bass_effect = QCheckBox("Bass-reactive zoom blur")
        self.bass_effect.setChecked(True)
        self.video_fade = QCheckBox("Fade video in/out")
        self.video_fade.setChecked(True)
        self.audio_fade = QCheckBox("Fade audio in/out")
        self.audio_fade.setChecked(True)
        self.mute_original_video_audio = QCheckBox("Mute original video sound")
        self.mute_original_video_audio.setChecked(True)
        self.mute_original_video_audio.setVisible(False)
        self.mute_original_video_audio_label = QLabel("Video sound")
        self.mute_original_video_audio_label.setVisible(False)
        self.detect_drop = QCheckBox("Detect drop automatically")
        self.detect_drop.setChecked(True)
        self.pre_drop = QDoubleSpinBox()
        self.pre_drop.setRange(0.0, 60.0)
        self.pre_drop.setDecimals(1)
        self.pre_drop.setSingleStep(0.5)
        self.pre_drop.setSuffix(" seconds")
        self.pre_drop.setValue(2.0)
        self.detect_drop.toggled.connect(self.on_detect_drop_changed)
        self.pre_drop.editingFinished.connect(self.start_drop_detection)
        self.promo_tracks = QTableWidget(0, 3)
        self.promo_tracks.setHorizontalHeaderLabels(["Audio", "Start", "Duration"])
        self.promo_tracks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.promo_tracks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.promo_tracks.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.promo_tracks.setMinimumHeight(50)
        self.analysis_status = QLabel("")
        self.analysis_status.setWordWrap(True)
        self.profile = QComboBox()
        for label, value in (
            ("Visual native", None),
            ("Vertical 1080 × 1920", (1080, 1920)),
            ("Square 1080 × 1080", (1080, 1080)),
            ("Landscape 1920 × 1080", (1920, 1080)),
        ):
            self.profile.addItem(label, value)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(1, 600)
        self.duration.setValue(60)
        self.duration.setSuffix(" seconds")
        self.fps = QSpinBox()
        self.fps.setRange(12, 60)
        self.fps.setValue(24)
        self.crf = QSpinBox()
        self.crf.setRange(14, 30)
        self.crf.setValue(18)
        self.crf.setToolTip("Lower values produce higher quality and larger files.")
        self.encoding_speed = QComboBox()
        for preset in ("ultrafast", "fast", "medium", "slow"):
            self.encoding_speed.addItem(preset.title(), preset)
        self.encoding_speed.setCurrentIndex(self.encoding_speed.findData("medium"))
        self.audio_bitrate = QComboBox()
        for bitrate in ("128k", "192k", "256k", "320k"):
            self.audio_bitrate.addItem(bitrate, bitrate)
        self.audio_bitrate.setCurrentIndex(self.audio_bitrate.findData("256k"))
        self.video_duration_summary = QLabel("Select audio to estimate duration.")
        self.job_summary = QLabel("")

        input_form = QFormLayout()
        input_form.setSpacing(12)
        input_form.addRow("Audio", self.music)
        input_form.addRow("", self.music_status)
        artwork_row = QWidget()
        artwork_layout = QHBoxLayout(artwork_row)
        artwork_layout.setContentsMargins(0, 0, 0, 0)
        artwork_layout.addWidget(self.cover, 1)
        artwork_layout.addWidget(self.artwork_preview)
        input_form.addRow("Image or video", artwork_row)
        input_form.addRow("", self.cover_status)

        effects_form = QFormLayout()
        effects_form.setSpacing(12)
        effects_form.addRow("Visual effect", self.bass_effect)
        effects_form.addRow(self.mute_original_video_audio_label, self.mute_original_video_audio)
        effects_form.addRow("Video", self.video_fade)
        effects_form.addRow("Audio", self.audio_fade)

        promo_clips_layout = QVBoxLayout()
        promo_clips_layout.addWidget(self.analysis_status)
        promo_clips_layout.addWidget(self.promo_tracks, 1)
        self.timing_options = QWidget()
        timing_options_form = QFormLayout(self.timing_options)
        timing_options_form.setContentsMargins(0, 4, 0, 0)
        timing_options_form.setSpacing(8)
        timing_options_form.addRow("Automatic start", self.detect_drop)
        timing_options_form.addRow("Seconds before drop", self.pre_drop)
        self.timing_options.setVisible(False)
        promo_clips_layout.addWidget(self.timing_options)

        output_form = QFormLayout()
        output_form.setSpacing(12)
        output_form.addRow("Export folder", self.output)
        output_form.addRow("", self.output_status)
        output_form.addRow("Video profile", self.profile)
        output_form.addRow("Frame rate", self.fps)
        output_form.addRow("Quality (CRF)", self.crf)
        output_form.addRow("Encoding speed", self.encoding_speed)
        output_form.addRow("Audio bitrate", self.audio_bitrate)
        output_form.addRow("Estimated duration", self.video_duration_summary)
        output_form.addRow("Job estimate", self.job_summary)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        self.generate = QPushButton("Generate Videos")
        self.generate.setMinimumHeight(44)
        self.generate.setEnabled(False)
        self.generate.clicked.connect(self.start_generation)
        self.generate_requirements = QLabel("")
        self.generate_requirements.setWordWrap(True)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancel)
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
        layout.addStretch()
        self.clips = ClipsTab(self.settings)
        self.converter = ConverterTab(self.settings)
        self.app_settings = SettingsTab(self.settings)
        self.history = HistoryTab(self.settings)
        self.about = AboutTab()
        self.tabs = QTabWidget()
        icon_color = self.palette().color(QPalette.ColorRole.WindowText).name()
        self.tabs.addTab(container, material_icon("music_video", icon_color), "Video Generator")
        self.tabs.addTab(self.clips, material_icon("content_cut", icon_color), "Livestream Clips")
        self.tabs.addTab(self.converter, material_icon("swap_horiz", icon_color), "Converter")
        self.tabs.addTab(self.history, material_icon("history", icon_color), "History")
        self.tabs.addTab(self.app_settings, material_icon("settings", icon_color), "Settings")
        self.tabs.addTab(self.about, material_icon("info", icon_color), "About")
        self.setCentralWidget(self.tabs)

        self.music.changed.connect(self.on_music_changed)
        self.cover.changed.connect(self.validate)
        self.output.changed.connect(self.validate)
        self.app_settings.changed.connect(self.apply_app_settings)
        self.clips.job_completed.connect(self.add_history)
        self.converter.job_completed.connect(self.add_history)
        self.history.load_requested.connect(self.load_history_job)
        self.restore_paths()
        self.apply_app_settings()
        self.refresh_promo_tracks()
        self.validate()

    def restore_paths(self) -> None:
        for row, key in ((self.music, "music"), (self.cover, "cover"), (self.output, "output")):
            value = self.settings.value(key, "")
            if value and Path(value).exists():
                row.edit.setText(value)
        self.bass_effect.setChecked(self.settings.value("promo/bass_effect", True, type=bool))
        self.video_fade.setChecked(self.settings.value("promo/video_fade", True, type=bool))
        self.audio_fade.setChecked(self.settings.value("promo/audio_fade", True, type=bool))
        self.mute_original_video_audio.setChecked(
            self.settings.value("promo/mute_original_video_audio", True, type=bool)
        )
        self.detect_drop.setChecked(self.settings.value("promo/detect_drop", True, type=bool))
        self.pre_drop.setValue(self.settings.value("promo/pre_drop", 2.0, type=float))

    def apply_app_settings(self) -> None:
        default_output = self.settings.value("general/default_output", "")
        if default_output and Path(default_output).is_dir():
            if not self.output.path:
                self.output.set_path(default_output)
            if not self.clips.output.path:
                self.clips.output.set_path(default_output)
            if not self.converter.output.path:
                self.converter.output.set_path(default_output)

    def add_history(self, record: dict) -> None:
        try:
            records = json.loads(self.settings.value("history/jobs", "[]"))
        except (TypeError, json.JSONDecodeError):
            records = []
        records.insert(0, record)
        self.settings.setValue("history/jobs", json.dumps(records[:20]))
        self.history.refresh()

    def load_history_job(self, record: dict) -> None:
        if record.get("tool") == "promo":
            self.detect_drop.blockSignals(True)
            self.detect_drop.setChecked(False)
            self.detect_drop.blockSignals(False)
            self.music.set_path(record.get("source", ""))
            self.cover.set_path(record.get("cover", ""))
            self.output.set_path(record.get("output", ""))
            self.bass_effect.setChecked(record.get("bass_effect", True))
            self.video_fade.setChecked(record.get("video_fade", True))
            self.audio_fade.setChecked(record.get("audio_fade", True))
            self.mute_original_video_audio.setChecked(record.get("mute_original_video_audio", True))
            self.detect_drop.blockSignals(True)
            self.detect_drop.setChecked(record.get("detect_drop", True))
            self.detect_drop.blockSignals(False)
            self.pre_drop.setValue(record.get("pre_drop", 2.0))
            stored_tracks = {item.get("path"): item for item in record.get("tracks", [])}
            for row in range(self.promo_tracks.rowCount()):
                path = self.promo_tracks.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if path in stored_tracks:
                    self.promo_tracks.cellWidget(row, 1).setText(format_timestamp(stored_tracks[path].get("start", 0)))
                    self.promo_tracks.cellWidget(row, 2).setValue(stored_tracks[path].get("duration", 60))
            self.pre_drop.setEnabled(self.detect_drop.isChecked())
            self.analysis_status.setText("✓ Loaded saved per-track timings.")
            self.fps.setValue(record.get("fps", 24))
            profile = record.get("profile")
            self.profile.setCurrentIndex(max(0, self.profile.findData(tuple(profile) if profile else None)))
            self.tabs.setCurrentIndex(0)
        elif record.get("tool") == "clips":
            self.clips.source.set_path(record.get("source", ""))
            self.clips.output.set_path(record.get("output", ""))
            self.clips.table.setRowCount(0)
            for clip in record.get("clips", []):
                self.clips.add_row(
                    clip.get("title", ""),
                    format_timestamp(clip.get("start", 0)),
                    "",
                    str(clip.get("duration", 60)),
                )
            if self.clips.table.rowCount() == 0:
                self.clips.add_row()
            self.tabs.setCurrentIndex(1)
        elif record.get("tool") == "converter":
            self.converter.set_files(record.get("sources", []))
            self.converter.output.set_path(record.get("output", ""))
            format_index = self.converter.output_format.findData(record.get("format", ""))
            if format_index >= 0:
                self.converter.output_format.setCurrentIndex(format_index)
            bitrate_index = self.converter.mp3_bitrate.findData(record.get("bitrate", "320k"))
            if bitrate_index >= 0:
                self.converter.mp3_bitrate.setCurrentIndex(bitrate_index)
            self.tabs.setCurrentIndex(2)

    def on_music_changed(self, _path: str = "") -> None:
        self.refresh_promo_tracks()
        self.validate()

    def refresh_promo_tracks(self) -> None:
        previous: dict[str, tuple[str, float]] = {}
        for row in range(self.promo_tracks.rowCount()):
            item = self.promo_tracks.item(row, 0)
            if item:
                previous[item.data(Qt.ItemDataRole.UserRole)] = (
                    self.promo_tracks.cellWidget(row, 1).text(),
                    self.promo_tracks.cellWidget(row, 2).value(),
                )
        tracks = find_audio_files(self.music.path)
        self.timing_options.setVisible(bool(tracks))
        self.promo_tracks.setRowCount(0)
        for row, track in enumerate(tracks):
            self.promo_tracks.insertRow(row)
            item = QTableWidgetItem(track.name)
            item.setToolTip(os.fspath(track))
            item.setData(Qt.ItemDataRole.UserRole, os.fspath(track))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.promo_tracks.setItem(row, 0, item)
            old_start, old_duration = previous.get(os.fspath(track), ("00:00:00", self.duration.value()))
            start = QLineEdit(old_start)
            start.setPlaceholderText("HH:MM:SS")
            start.textChanged.connect(self.validate)
            duration = QDoubleSpinBox()
            duration.setRange(1, 3600)
            duration.setDecimals(1)
            duration.setSuffix(" s")
            duration.setValue(old_duration)
            duration.valueChanged.connect(self.validate)
            self.promo_tracks.setCellWidget(row, 1, start)
            self.promo_tracks.setCellWidget(row, 2, duration)
        if tracks and self.detect_drop.isChecked():
            self.start_drop_detection()
        elif tracks:
            self.analysis_status.setText("Manual start times — edit each row as needed.")
        else:
            self.analysis_status.clear()

    def promo_track_options(self) -> tuple[dict[Path, tuple[float, float]], str]:
        options: dict[Path, tuple[float, float]] = {}
        for row in range(self.promo_tracks.rowCount()):
            item = self.promo_tracks.item(row, 0)
            try:
                start = parse_timestamp(self.promo_tracks.cellWidget(row, 1).text())
            except ValueError as exc:
                return {}, f"Track {row + 1}: {exc}"
            duration = self.promo_tracks.cellWidget(row, 2).value()
            options[Path(item.data(Qt.ItemDataRole.UserRole))] = (start, duration)
        return options, f"✓ {len(options)} promo clip{'s' if len(options) != 1 else ''} ready."

    def on_detect_drop_changed(self, checked: bool) -> None:
        self.pre_drop.setEnabled(checked and self.worker is None)
        if checked:
            self.start_drop_detection()
        else:
            self.pending_drop_detection = False
            if self.analysis_worker and self.analysis_worker.isRunning():
                self.analysis_worker.requestInterruption()
            for row in range(self.promo_tracks.rowCount()):
                self.promo_tracks.cellWidget(row, 1).setText("00:00:00")
            self.analysis_status.setText("Manual start times — edit each row as needed.")
            self.validate()

    def start_drop_detection(self) -> None:
        tracks = find_audio_files(self.music.path)
        if not self.detect_drop.isChecked() or not tracks:
            return
        if self.analysis_worker and self.analysis_worker.isRunning():
            self.pending_drop_detection = True
            self.analysis_worker.requestInterruption()
            return
        self.pending_drop_detection = False
        self.analysis_worker = DropDetectionWorker(tracks, self.pre_drop.value())
        self.analysis_worker.progress.connect(lambda _percent, status: self.analysis_status.setText(status + "…"))
        self.analysis_worker.succeeded.connect(self.on_drop_detection_success)
        self.analysis_worker.failed.connect(lambda message: self.analysis_status.setText(f"Automatic detection failed: {message}. Edit starts manually."))
        self.analysis_worker.finished.connect(self.on_drop_detection_finished)
        self.analysis_status.setText("Preparing drop detection…")
        self.validate()
        self.analysis_worker.start()

    def on_drop_detection_success(self, starts: dict[str, float]) -> None:
        if not self.detect_drop.isChecked():
            return
        for row in range(self.promo_tracks.rowCount()):
            path = self.promo_tracks.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if path in starts:
                self.promo_tracks.cellWidget(row, 1).setText(format_timestamp(starts[path]))
        self.analysis_status.setText(f"✓ Automatically set {len(starts)} start time{'s' if len(starts) != 1 else ''}.")

    def on_drop_detection_finished(self) -> None:
        worker = self.analysis_worker
        self.analysis_worker = None
        if worker:
            worker.deleteLater()
        if self.pending_drop_detection:
            self.start_drop_detection()
        else:
            self.validate()

    def validate(self) -> bool:
        tracks = find_audio_files(self.music.path)
        music_ok = bool(tracks)
        music_status = (
            f"✓ Found {len(tracks)} audio file{'s' if len(tracks) != 1 else ''}."
            if music_ok
            else "No audio files were found." if self.music.path else ""
        )
        self.music_status.setText(music_status)
        self.music_status.setVisible(bool(music_status))
        cover_ok, cover_message = validate_visual(self.cover.path)
        video_visual = Path(self.cover.path).suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
        self.mute_original_video_audio.setVisible(video_visual)
        self.mute_original_video_audio_label.setVisible(video_visual)
        self.mute_original_video_audio.setEnabled(video_visual and cover_ok and self.worker is None)
        cover_status = (("✓ " if cover_ok else "") + cover_message) if self.cover.path else ""
        self.cover_status.setText(cover_status)
        self.cover_status.setVisible(bool(cover_status))
        self.update_artwork_preview(cover_ok)
        editable = self.worker is None
        self.promo_clips_group.setEnabled(music_ok and editable)
        downstream_ready = music_ok and cover_ok and editable
        self.post_effects_group.setEnabled(downstream_ready)
        self.output_group.setEnabled(downstream_ready)
        output_path = Path(self.output.path).expanduser() if self.output.path else None
        output_ok = bool(output_path and output_path.is_dir() and os.access(output_path, os.W_OK))
        output_status = "✓ Export folder is writable." if output_ok else "Export folder is not writable." if self.output.path else ""
        self.output_status.setText(output_status)
        self.output_status.setVisible(bool(output_status))
        track_options, track_message = self.promo_track_options()
        analysing = bool(self.analysis_worker and self.analysis_worker.isRunning())
        ready = music_ok and cover_ok and output_ok and bool(track_options) and not analysing and self.worker is None
        missing = []
        if not music_ok:
            missing.append("choose audio")
        if not cover_ok:
            missing.append("choose a valid image or video")
        if not output_ok:
            missing.append("choose a writable export folder")
        if music_ok and not track_options:
            missing.append(track_message.rstrip("."))
        if analysing:
            missing.append("wait for automatic drop detection")
        if self.worker is not None:
            action_message = "Generating videos…"
        elif missing:
            action_message = "To enable Generate: " + "; ".join(missing) + "."
        else:
            action_message = "✓ Ready to generate videos."
        self.generate_requirements.setText(action_message)
        self.generate.setToolTip(action_message)
        if track_options:
            durations = [duration for _start, duration in track_options.values()]
            total_seconds = sum(durations)
            shortest = min(durations)
            longest = max(durations)
            if abs(shortest - longest) < 0.01:
                per_video = f"{format_timestamp(shortest)} per video"
            else:
                per_video = f"{format_timestamp(shortest)}–{format_timestamp(longest)} per video"
            self.video_duration_summary.setText(
                f"{per_video} • {format_timestamp(total_seconds)} combined"
            )
            free_gb = shutil.disk_usage(output_path).free / 1024**3 if output_ok else 0
            self.job_summary.setText(f"{len(track_options)} output(s) • {free_gb:.1f} GB free")
        else:
            self.video_duration_summary.setText("Select audio to estimate duration.")
            self.job_summary.setText("Select audio to estimate this job.")
        self.generate.setEnabled(ready)
        return ready

    def update_artwork_preview(self, cover_ok: bool) -> None:
        if not cover_ok:
            self.artwork_preview.setPixmap(QPixmap())
            self.artwork_preview.setText("Visual preview")
            return
        if Path(self.cover.path).suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}:
            capture = cv2.VideoCapture(self.cover.path)
            readable, frame = capture.read()
            capture.release()
            if not readable:
                self.artwork_preview.setText("Video preview unavailable")
                return
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channels = rgb.shape
            pixmap = QPixmap.fromImage(QImage(rgb.data, width, height, channels * width, QImage.Format.Format_RGB888).copy())
        else:
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
        self.video_fade.setEnabled(enabled)
        self.audio_fade.setEnabled(enabled)
        self.mute_original_video_audio.setEnabled(
            enabled and Path(self.cover.path).suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
        )
        self.detect_drop.setEnabled(enabled)
        self.pre_drop.setEnabled(enabled and self.detect_drop.isChecked())
        self.promo_tracks.setEnabled(enabled)
        for control in (
            self.profile,
            self.fps,
            self.crf,
            self.encoding_speed,
            self.audio_bitrate,
        ):
            control.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)

    def cancel(self) -> None:
        if self.worker:
            self.cancel_button.setEnabled(False)
            self.progress_status.setText("Cancelling safely…")
            self.worker.requestInterruption()

    def clear(self) -> None:
        self.music.set_path("")
        self.cover.set_path("")
        self.output.set_path(self.settings.value("general/default_output", ""))
        self.bass_effect.setChecked(True)
        self.video_fade.setChecked(True)
        self.audio_fade.setChecked(True)
        self.mute_original_video_audio.setChecked(True)
        self.detect_drop.setChecked(True)
        self.pre_drop.setValue(2.0)
        self.profile.setCurrentIndex(0)
        self.duration.setValue(60)
        self.fps.setValue(24)
        self.crf.setValue(18)
        self.encoding_speed.setCurrentIndex(self.encoding_speed.findData("medium"))
        self.audio_bitrate.setCurrentIndex(self.audio_bitrate.findData("256k"))
        self.progress.setValue(0)
        self.progress.hide()
        self.progress_status.clear()
        self.progress_status.hide()
        for key in ("music", "cover", "output", "promo/bass_effect", "promo/video_fade", "promo/audio_fade", "promo/mute_original_video_audio", "promo/detect_drop", "promo/pre_drop"):
            self.settings.remove(key)
        self.validate()

    def start_generation(self) -> None:
        if not self.validate():
            return
        tracks = find_audio_files(self.music.path)
        track_options, _ = self.promo_track_options()
        for key, value in (("music", self.music.path), ("cover", self.cover.path), ("output", self.output.path)):
            self.settings.setValue(key, value)
        render_settings = RenderSettings(
            fps=self.fps.value(),
            duration=self.duration.value(),
            pre_drop=self.pre_drop.value(),
            bass_effect=self.bass_effect.isChecked(),
            mute_original_video_audio=self.mute_original_video_audio.isChecked(),
            video_fade=self.video_fade.isChecked(),
            audio_fade=self.audio_fade.isChecked(),
            output_size=self.profile.currentData(),
            preset=self.encoding_speed.currentData(),
            crf=self.crf.value(),
            audio_bitrate=self.audio_bitrate.currentData(),
        )
        self.settings.setValue("promo/bass_effect", self.bass_effect.isChecked())
        self.settings.setValue("promo/video_fade", self.video_fade.isChecked())
        self.settings.setValue("promo/audio_fade", self.audio_fade.isChecked())
        self.settings.setValue("promo/mute_original_video_audio", self.mute_original_video_audio.isChecked())
        self.settings.setValue("promo/detect_drop", self.detect_drop.isChecked())
        self.settings.setValue("promo/pre_drop", self.pre_drop.value())
        self.worker = RenderWorker(
            tracks,
            Path(self.cover.path),
            Path(self.output.path),
            render_settings,
            self.settings.value("general/promo_naming", "{track} - Promo Snippet"),
            self.settings.value("general/conflict_policy", "rename"),
            track_options,
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.succeeded.connect(self.on_success)
        self.worker.failed.connect(self.on_failure)
        self.worker.cancelled.connect(self.on_cancelled)
        self.worker.finished.connect(self.worker_finished)
        self.progress.setValue(0)
        self.progress.show()
        self.progress_status.setText("Preparing…")
        self.progress_status.show()
        self.set_inputs_enabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.generate.setEnabled(False)
        self.worker.start()

    def on_progress(self, percent: int, status: str) -> None:
        self.progress.setValue(percent)
        self.progress_status.setText(status)

    def on_success(self, outputs: list[str]) -> None:
        profile = self.profile.currentData()
        track_options, _ = self.promo_track_options()
        self.add_history({
            "tool": "promo",
            "created": datetime.now().isoformat(timespec="seconds"),
            "source": self.music.path,
            "cover": self.cover.path,
            "output": self.output.path,
            "bass_effect": self.bass_effect.isChecked(),
            "video_fade": self.video_fade.isChecked(),
            "audio_fade": self.audio_fade.isChecked(),
            "mute_original_video_audio": self.mute_original_video_audio.isChecked(),
            "detect_drop": self.detect_drop.isChecked(),
            "pre_drop": self.pre_drop.value(),
            "tracks": [
                {"path": os.fspath(path), "start": start, "duration": duration}
                for path, (start, duration) in track_options.items()
            ],
            "fps": self.fps.value(),
            "profile": list(profile) if profile else None,
            "outputs": outputs,
        })
        if self.settings.value("general/notify_finished", True, type=bool):
            show_completion(self, "Videos generated", outputs)

    def on_failure(self, message: str, details: str) -> None:
        show_error(self, "Generation failed", message, details)

    def on_cancelled(self) -> None:
        self.progress_status.setText("Cancelled. Partial files were removed.")

    def worker_finished(self) -> None:
        worker = self.worker
        self.worker = None
        self.set_inputs_enabled(True)
        self.cancel_button.hide()
        self.validate()
        if worker:
            worker.deleteLater()

    def closeEvent(self, event):  # noqa: N802, ANN001
        promo_running = self.worker and self.worker.isRunning()
        analysis_running = self.analysis_worker and self.analysis_worker.isRunning()
        clips_running = self.clips.worker and self.clips.worker.isRunning()
        converter_running = self.converter.worker and self.converter.worker.isRunning()
        if promo_running or analysis_running or clips_running or converter_running:
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
