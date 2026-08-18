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
from mm_toolkit.ui.helpers import page_title, section_group, show_completion, show_error
from mm_toolkit.ui.style import ICON_BUTTON_STYLE, TIMESTAMP_BUTTON_STYLE, TIMESTAMP_FIELD_STYLE, material_icon
from mm_toolkit.ui.widgets import PathRow


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
            results = cut_media_clips(
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


class ClipField(QLineEdit):
    focused = Signal()

    def focusInEvent(self, event) -> None:  # noqa: N802, ANN001
        super().focusInEvent(event)
        self.focused.emit()


class VideoPreviewWidget(QVideoWidget):
    """Responsive 16:9 preview surface that preserves the source aspect ratio."""

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return max(220, round(width * 9 / 16))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(640, 360)


class ClipsTab(QWidget):
    job_completed = Signal(object)
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.worker: ClipWorker | None = None
        title = page_title("Media Cutter")
        subtitle = QLabel(
            "Cut audio or video into precisely timed clips. "
            "Use HH:MM:SS, MM:SS, or seconds. End is optional; duration defaults to 60 seconds."
        )
        subtitle.setWordWrap(True)
        self.source = PathRow(
            "Choose source media",
            "file",
            "Media (*.wav *.wave *.aif *.aiff *.flac *.mp3 *.m4a *.aac *.ogg *.mp4 *.mov *.m4v *.mkv *.avi *.webm)",
        )
        self.output = PathRow("Choose clip export folder", "directory")
        self.source_status = QLabel("")
        self.output_status = QLabel("")
        self.player = QMediaPlayer(self)
        self.player_audio = QAudioOutput(self)
        self.player.setAudioOutput(self.player_audio)
        self.video_preview = VideoPreviewWidget()
        self.video_preview.setMinimumSize(360, 220)
        self.video_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.video_preview.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.video_preview.hide()
        self.player.setVideoOutput(self.video_preview)
        self.preview_prime_requested = False
        self.preview_priming = False
        self.preview_prime_was_muted = False
        self.video_preview.videoSink().videoFrameChanged.connect(self.on_preview_frame_changed)
        self.play_button = QPushButton("▶ Play")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle_playback)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.sliderPressed.connect(self.on_timeline_pressed)
        self.timeline.sliderMoved.connect(self.on_timeline_moved)
        self.timeline.sliderReleased.connect(self.on_timeline_released)
        self.timeline_was_playing = False
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.set_start_button = QPushButton("Set Start")
        self.set_end_button = QPushButton("Set End")
        self.active_clip_label = QLabel("Editing: Clip 01")
        self.active_clip_label.setFixedHeight(32)
        self.active_clip_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.active_clip_label.setStyleSheet(
            "QLabel {"
            "  color: palette(text);"
            "  padding: 0 6px;"
            "  font-weight: 600;"
            "}"
        )
        self.set_start_button.clicked.connect(lambda: self.set_timestamp(1))
        self.set_end_button.clicked.connect(lambda: self.set_timestamp(2))
        self.player.positionChanged.connect(self.on_player_position)
        self.player.durationChanged.connect(self.on_player_duration)
        self.player.playbackStateChanged.connect(self.on_playback_state)
        self.player.mediaStatusChanged.connect(self.on_cutter_media_status)
        self.clip_preview_button: QToolButton | None = None
        self.clip_preview_start_ms: int | None = None
        self.clip_preview_end_ms = 0

        input_form = QFormLayout()
        input_form.setSpacing(10)
        input_form.addRow("Source media", self.source)
        input_form.addRow("", self.source_status)

        output_form = QFormLayout()
        output_form.setSpacing(10)
        output_form.addRow("Export folder", self.output)
        output_form.addRow("", self.output_status)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Title", "Start", "End", "Duration", "", ""])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setStyleSheet(
            "QTableWidget {"
            "  border: 1px solid rgba(127, 127, 127, 0.35);"
            "  border-radius: 8px;"
            "  background: palette(base);"
            "  alternate-background-color: palette(alternate-base);"
            "  selection-background-color: palette(midlight);"
            "  selection-color: palette(text);"
            "}"
            "QHeaderView::section {"
            "  background: palette(midlight);"
            "  color: palette(text);"
            "  border: 0;"
            "  border-bottom: 1px solid palette(mid);"
            "  padding: 9px 8px;"
            "  font-weight: 700;"
            "}"
        )
        self.table.currentCellChanged.connect(self.update_active_clip)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setMinimumSectionSize(36)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        for column in (1, 2, 3, 4, 5):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        for column, width in enumerate((110, 82, 82, 70, 42, 42)):
            self.table.setColumnWidth(column, width)
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
        playback_actions = QHBoxLayout()
        playback_actions.addWidget(self.play_button)
        playback_actions.addWidget(self.active_clip_label)
        playback_actions.addStretch()
        playback_actions.addWidget(self.set_start_button)
        playback_actions.addWidget(self.set_end_button)
        clip_input_layout.addLayout(playback_actions)
        timestamps_layout = QVBoxLayout()
        timestamps_layout.addWidget(self.table)
        timestamps_layout.addWidget(self.add_button)
        timestamps_layout.addWidget(self.clip_status)
        right_column = QVBoxLayout()
        self.clip_timestamps_group = section_group("Clip timestamps", timestamps_layout)
        self.clip_output_group = section_group("Output", output_form)
        right_column.addWidget(self.clip_timestamps_group, 1)
        right_column.addWidget(self.clip_output_group)
        feature_columns = QHBoxLayout()
        feature_columns.setSpacing(14)
        self.clip_input_group = section_group("Input", clip_input_layout)
        feature_columns.addWidget(self.clip_input_group, 5)
        feature_columns.addLayout(right_column, 4)
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
        self.source.changed.connect(self.load_media_preview)
        self.output.changed.connect(self.validate)
        for row, key in ((self.source, "clips/source"), (self.output, "clips/output")):
            value = self.settings.value(key, "")
            if value and Path(value).exists():
                row.edit.setText(value)
        self.load_media_preview(self.source.path)
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
            edit.setFixedHeight(38)
            edit.setStyleSheet(TIMESTAMP_FIELD_STYLE)
            edit.setPlaceholderText(placeholder)
            edit.textChanged.connect(self.validate)
            if column in (1, 2, 3):
                edit.textChanged.connect(lambda _text, row=row: self.on_clip_timing_changed(row))
            edit.focused.connect(lambda row=row, column=column: self.table.setCurrentCell(row, column))
            self.table.setCellWidget(row, column, edit)
        preview = QToolButton()
        preview.setIcon(material_icon("play_arrow", self.palette().color(QPalette.ColorRole.Text).name()))
        preview.setToolTip("Play this clip")
        preview.setAccessibleName(f"Play clip {row + 1}")
        preview.setAutoRaise(True)
        preview.setFixedSize(36, 36)
        preview.setStyleSheet(ICON_BUTTON_STYLE)
        preview.clicked.connect(
            lambda _checked=False, button=preview: self.toggle_clip_preview_button(button)
        )
        self.table.setCellWidget(row, 4, preview)
        remove = QToolButton()
        remove.setIcon(material_icon("delete", self.palette().color(QPalette.ColorRole.Text).name()))
        remove.setToolTip("Remove this clip")
        remove.setAccessibleName(f"Remove clip {row + 1}")
        remove.setAutoRaise(True)
        remove.setFixedSize(36, 36)
        remove.setStyleSheet(ICON_BUTTON_STYLE)
        remove.clicked.connect(lambda _checked=False, button=remove: self.remove_row(button))
        self.table.setCellWidget(row, 5, remove)
        self.table.setCurrentCell(row, 0)
        self.validate()

    def update_active_clip(self, current_row: int, _current_column: int, _previous_row: int, _previous_column: int) -> None:
        if current_row < 0:
            self.active_clip_label.setText("Editing: select a clip")
            return
        title = self.table.cellWidget(current_row, 0).text().strip() or f"Clip {current_row + 1:02d}"
        self.active_clip_label.setText(f"Editing: {title}")
        for row in range(self.table.rowCount()):
            for column in range(self.table.columnCount()):
                widget = self.table.cellWidget(row, column)
                if widget:
                    if isinstance(widget, QToolButton):
                        continue
                    base_style = (
                        TIMESTAMP_BUTTON_STYLE
                        if isinstance(widget, QPushButton)
                        else TIMESTAMP_FIELD_STYLE
                    )
                    active_style = (
                        "QPushButton, QLineEdit { background-color: palette(midlight); }"
                        if row == current_row
                        else ""
                    )
                    widget.setStyleSheet(base_style + active_style)

    def remove_row(self, button: QToolButton) -> None:
        self.stop_clip_preview()
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 5) is button:
                self.table.removeRow(row)
                break
        if self.table.rowCount() == 0:
            self.add_row()
        self.validate()

    def parsed_clips(self) -> tuple[list[ClipRequest], str]:
        clips: list[ClipRequest] = []
        for row in range(self.table.rowCount()):
            try:
                clips.append(self.clip_request(row))
            except ValueError as exc:
                return [], f"Clip {row + 1}: {exc}"
        return clips, f"✓ {len(clips)} clip{'s' if len(clips) != 1 else ''} ready."

    def clip_request(self, row: int) -> ClipRequest:
        title = self.table.cellWidget(row, 0).text().strip()
        start_text = self.table.cellWidget(row, 1).text().strip()
        end_text = self.table.cellWidget(row, 2).text().strip()
        duration_text = self.table.cellWidget(row, 3).text().strip()
        if not start_text:
            raise ValueError("enter a start timestamp.")
        start = parse_timestamp(start_text)
        if end_text:
            duration = parse_timestamp(end_text) - start
            if duration <= 0:
                raise ValueError("End must be later than start.")
        else:
            duration = parse_timestamp(duration_text or "60")
            if duration <= 0:
                raise ValueError("Duration must be greater than zero.")
        return ClipRequest(start, duration, title)

    def on_clip_timing_changed(self, row: int) -> None:
        if self.table.cellWidget(row, 4) is self.clip_preview_button:
            self.stop_clip_preview()

    def toggle_clip_preview(self, row: int, button: QToolButton) -> None:
        if self.clip_preview_button is button and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        if not validate_media_source(self.source.path)[0]:
            return
        try:
            clip = self.clip_request(row)
        except ValueError as exc:
            QMessageBox.warning(self, "Preview unavailable", f"Clip {row + 1}: {exc}")
            return
        self.stop_clip_preview()
        self.table.setCurrentCell(row, 4)
        self.clip_preview_button = button
        self.clip_preview_start_ms = round(clip.start * 1000)
        self.clip_preview_end_ms = round((clip.start + clip.duration) * 1000)
        button.setIcon(material_icon("stop", self.palette().color(QPalette.ColorRole.Text).name()))
        button.setToolTip("Stop this clip")
        if self.player.mediaStatus() in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self.start_clip_preview()

    def toggle_clip_preview_button(self, button: QToolButton) -> None:
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 4) is button:
                self.toggle_clip_preview(row, button)
                return

    def on_cutter_media_status(self, status) -> None:  # noqa: ANN001
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.start_clip_preview()
            if self.preview_prime_requested and self.clip_preview_start_ms is None:
                self.prime_video_preview()

    def prime_video_preview(self) -> None:
        if not self.preview_prime_requested or self.preview_priming:
            return
        self.preview_prime_requested = False
        self.preview_priming = True
        self.preview_prime_was_muted = self.player_audio.isMuted()
        self.player_audio.setMuted(True)
        self.player.play()

    def on_preview_frame_changed(self, frame) -> None:  # noqa: ANN001
        if not self.preview_priming or not frame.isValid():
            return
        self.player.pause()
        self.player_audio.setMuted(self.preview_prime_was_muted)
        self.preview_priming = False
        self.play_button.setText("▶ Play")

    def cancel_preview_priming(self) -> None:
        if self.preview_priming:
            self.player_audio.setMuted(self.preview_prime_was_muted)
        self.preview_priming = False
        self.preview_prime_requested = False

    def start_clip_preview(self) -> None:
        if self.clip_preview_start_ms is None or self.clip_preview_button is None:
            return
        start_ms = self.clip_preview_start_ms
        self.clip_preview_start_ms = None
        self.player.setPosition(start_ms)
        self.player.play()

    def stop_clip_preview(self) -> None:
        button = self.clip_preview_button
        self.clip_preview_button = None
        self.clip_preview_start_ms = None
        self.clip_preview_end_ms = 0
        if button:
            button.setIcon(material_icon("play_arrow", self.palette().color(QPalette.ColorRole.Text).name()))
            button.setToolTip("Play this clip")

    def load_media_preview(self, path: str) -> None:
        valid, _ = validate_media_source(path)
        kind = media_kind(path) if valid else None
        self.stop_clip_preview()
        self.cancel_preview_priming()
        self.player.stop()
        self.preview_prime_requested = kind == "video"
        self.player.setSource(QUrl.fromLocalFile(path) if valid else QUrl())
        self.video_preview.setVisible(kind == "video")
        self.play_button.setEnabled(valid and self.worker is None)
        if self.player.mediaStatus() in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self.prime_video_preview()

    def toggle_playback(self) -> None:
        if self.preview_priming:
            self.player_audio.setMuted(self.preview_prime_was_muted)
            self.preview_priming = False
            self.preview_prime_requested = False
            self.play_button.setText("Pause")
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.stop_clip_preview()
            self.player.play()

    def on_playback_state(self, state) -> None:  # noqa: ANN001
        if not self.preview_priming:
            self.play_button.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "▶ Play")
        if state != QMediaPlayer.PlaybackState.PlayingState:
            self.stop_clip_preview()

    def on_player_position(self, position: int) -> None:
        if not self.timeline.isSliderDown():
            self.timeline.setValue(position)
        self.update_cutter_time_label(position)
        if self.clip_preview_end_ms and position >= self.clip_preview_end_ms:
            self.player.pause()

    def update_cutter_time_label(self, position: int) -> None:
        self.time_label.setText(
            f"{format_timestamp(position / 1000)} / {format_timestamp(self.player.duration() / 1000)}"
        )

    def on_timeline_pressed(self) -> None:
        self.timeline_was_playing = (
            self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        if self.timeline_was_playing:
            self.player.pause()
        self.stop_clip_preview()

    def on_timeline_moved(self, position: int) -> None:
        self.player.setPosition(position)
        self.update_cutter_time_label(position)

    def on_timeline_released(self) -> None:
        position = self.timeline.value()
        self.player.setPosition(position)
        self.update_cutter_time_label(position)
        if self.timeline_was_playing:
            self.player.play()
        self.timeline_was_playing = False

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
        source_ok, source_message = validate_media_source(self.source.path)
        kind = media_kind(self.source.path) if source_ok else None
        media_label = kind.title() if kind else "Media"
        output_format = "MP4" if kind == "video" else Path(self.source.path).suffix.lstrip(".").upper()
        if output_format == "WAVE":
            output_format = "WAV"
        elif output_format == "AIF":
            output_format = "AIFF"
        self.clip_output_group.setTitle(f"{media_label} clip output")
        self.generate.setText(f"Create {media_label} Clips")
        downstream_enabled = source_ok and self.worker is None
        self.clip_timestamps_group.setEnabled(downstream_enabled)
        self.clip_output_group.setEnabled(downstream_enabled)
        source_status = (("✓ " if source_ok else "") + source_message) if self.source.path else ""
        self.source_status.setText(source_status)
        self.source_status.setVisible(bool(source_status))
        output_path = Path(self.output.path).expanduser() if self.output.path else None
        output_ok = bool(output_path and output_path.is_dir() and os.access(output_path, os.W_OK))
        if output_ok and kind:
            output_status = f"✓ {media_label} clips will be exported as {output_format} files."
        else:
            output_status = "Export folder is not writable." if self.output.path else ""
        self.output_status.setText(output_status)
        self.output_status.setVisible(bool(output_status))
        clips, clip_message = self.parsed_clips()
        self.clip_status.setText(clip_message)
        ready = source_ok and output_ok and bool(clips) and self.worker is None
        missing = []
        if not source_ok:
            missing.append("choose valid source media")
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
        self.generate.setEnabled(ready)
        return ready

    def set_inputs_enabled(self, enabled: bool) -> None:
        self.source.set_enabled(enabled)
        downstream_enabled = enabled and validate_media_source(self.source.path)[0]
        self.clip_timestamps_group.setEnabled(downstream_enabled)
        self.clip_output_group.setEnabled(downstream_enabled)
        self.output.set_enabled(enabled)
        self.add_button.setEnabled(enabled)
        self.table.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.play_button.setEnabled(enabled and validate_media_source(self.source.path)[0])
        self.timeline.setEnabled(enabled)
        self.set_start_button.setEnabled(enabled)
        self.set_end_button.setEnabled(enabled)

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
