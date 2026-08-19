"""Video Generator tab: render a promo video from audio + artwork/video."""

from __future__ import annotations

import os
import shutil
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
from mm_toolkit.ui.effects_panel import EffectsPanel
from mm_toolkit.ui.helpers import collapsible_section, page_title, show_completion, show_error
from mm_toolkit.ui.style import (
    ICON_BUTTON_STYLE,
    TIMESTAMP_BUTTON_STYLE,
    TIMESTAMP_FIELD_STYLE,
    material_icon,
)
from mm_toolkit.ui.widgets import PathRow


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


class DropStartField(QWidget):
    """Start-time editor with a per-track drop detection action."""

    textChanged = Signal(str)
    detect_requested = Signal()

    def __init__(self, value: str):
        super().__init__()
        self.edit = QLineEdit(value)
        self.edit.setMinimumWidth(80)
        self.edit.setFixedHeight(36)
        self.edit.setStyleSheet(TIMESTAMP_FIELD_STYLE)
        self.edit.setPlaceholderText("HH:MM:SS")
        self.edit.textChanged.connect(self.textChanged)
        self.detect_button = QToolButton()
        self.detect_button.setText("✨")
        self.detect_button.setFixedSize(36, 36)
        self.detect_button.setStyleSheet(TIMESTAMP_BUTTON_STYLE)
        self.detect_button.setToolTip("Analyze this track and propose a drop start time")
        self.detect_button.setAccessibleName("Detect drop for this track")
        self.detect_button.clicked.connect(self.detect_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.detect_button)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str) -> None:  # noqa: N802
        self.edit.setText(value)


class DropDetectionDialog(QDialog):
    """Confirmation and lead-in selection for per-track drop analysis."""

    def __init__(self, track_name: str, seconds_before: float, parent: QWidget):
        super().__init__(parent)
        self.setWindowTitle("Detect drop start")
        self.setMinimumWidth(420)
        message = QLabel(
            f"MM Toolkit will analyze {track_name} and propose a start time based on its main drop."
        )
        message.setWordWrap(True)
        self.seconds_before = QDoubleSpinBox()
        self.seconds_before.setRange(0.0, 60.0)
        self.seconds_before.setDecimals(1)
        self.seconds_before.setSingleStep(0.5)
        self.seconds_before.setSuffix(" seconds")
        self.seconds_before.setValue(seconds_before)
        form = QFormLayout()
        form.addRow("Start before the drop", self.seconds_before)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Analyze")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(message)
        layout.addLayout(form)
        layout.addWidget(buttons)


class VideoGeneratorTab(QWidget):
    job_completed = Signal(object)

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.worker: RenderWorker | None = None
        self.analysis_worker: DropDetectionWorker | None = None

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
        self.artwork_preview = QLabel()
        self.artwork_preview.setFixedSize(104, 104)
        self.artwork_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork_preview.hide()
        self.effects_panel = EffectsPanel(self.settings, "promo")
        self.video_fade = QCheckBox("Fade video in/out")
        self.video_fade.setChecked(True)
        self.audio_fade = QCheckBox("Fade audio in/out")
        self.audio_fade.setChecked(True)
        self.mute_original_video_audio = QCheckBox("Mute original video sound")
        self.mute_original_video_audio.setChecked(True)
        self.mute_original_video_audio.setVisible(False)
        self.mute_original_video_audio_label = QLabel("Video sound")
        self.mute_original_video_audio_label.setVisible(False)
        self.promo_tracks = QTableWidget(0, 4)
        self.promo_tracks.setHorizontalHeaderLabels(["Audio", "Start", "Duration", ""])
        self.promo_tracks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.promo_tracks.setColumnWidth(0, 120)
        self.promo_tracks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.promo_tracks.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.promo_tracks.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.promo_tracks.setColumnWidth(3, 42)
        self.promo_tracks.horizontalHeader().setMinimumSectionSize(36)
        self.promo_tracks.verticalHeader().setDefaultSectionSize(44)
        self.promo_tracks.setMinimumHeight(50)
        self.promo_preview_player = QMediaPlayer(self)
        self.promo_preview_audio = QAudioOutput(self)
        self.promo_preview_player.setAudioOutput(self.promo_preview_audio)
        self.promo_preview_player.positionChanged.connect(self.on_promo_preview_position)
        self.promo_preview_player.playbackStateChanged.connect(self.on_promo_preview_state)
        self.promo_preview_player.mediaStatusChanged.connect(self.on_promo_preview_media_status)
        self.promo_preview_end_ms = 0
        self.promo_preview_start_ms: int | None = None
        self.promo_preview_button: QToolButton | None = None
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
        self.audio_bitrate.setCurrentIndex(self.audio_bitrate.findData("320k"))
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
        effects_form.addRow(self.mute_original_video_audio_label, self.mute_original_video_audio)
        effects_form.addRow("Video", self.video_fade)
        effects_form.addRow("Audio", self.audio_fade)

        promo_clips_layout = QVBoxLayout()
        promo_clips_layout.addWidget(self.promo_tracks, 1)
        promo_clips_layout.addWidget(self.analysis_status)

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        feature_columns = QHBoxLayout()
        feature_columns.setSpacing(14)
        input_column = QVBoxLayout()
        self.promo_input_group = collapsible_section("Input", input_form)
        input_column.addWidget(self.promo_input_group)
        self.promo_clips_group = collapsible_section("Audio timestamps", promo_clips_layout)
        input_column.addWidget(self.promo_clips_group, 1)
        input_column.addStretch()
        settings_column = QVBoxLayout()
        effects_panel_layout = QVBoxLayout()
        effects_panel_layout.addWidget(self.effects_panel.stack_widget)
        self.visual_effects_group = collapsible_section("Visual Effects", effects_panel_layout, expanded=False)
        layers_layout = QVBoxLayout()
        layers_layout.addWidget(self.effects_panel.layers_widget)
        self.layers_group = collapsible_section("Layers", layers_layout, expanded=False)
        self.post_effects_group = collapsible_section("Post-Effects", effects_form, expanded=False)
        self.output_group = collapsible_section("Output", output_form)
        settings_column.addWidget(self.visual_effects_group)
        settings_column.addWidget(self.layers_group)
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

        self.music.changed.connect(self.on_music_changed)
        self.cover.changed.connect(self.validate)
        self.output.changed.connect(self.validate)
        self.restore_paths()
        self.refresh_promo_tracks()
        self.validate()

    def restore_paths(self) -> None:
        for row, key in ((self.music, "music"), (self.cover, "cover"), (self.output, "output")):
            value = self.settings.value(key, "")
            if value and Path(value).exists():
                row.edit.setText(value)
        self.video_fade.setChecked(self.settings.value("promo/video_fade", True, type=bool))
        self.audio_fade.setChecked(self.settings.value("promo/audio_fade", True, type=bool))
        self.mute_original_video_audio.setChecked(
            self.settings.value("promo/mute_original_video_audio", True, type=bool)
        )

    def on_music_changed(self, _path: str = "") -> None:
        self.refresh_promo_tracks()
        self.validate()

    def refresh_promo_tracks(self) -> None:
        self.stop_promo_preview()
        previous: dict[str, tuple[str, float]] = {}
        for row in range(self.promo_tracks.rowCount()):
            item = self.promo_tracks.item(row, 0)
            if item:
                previous[item.data(Qt.ItemDataRole.UserRole)] = (
                    self.promo_tracks.cellWidget(row, 1).text(),
                    self.promo_tracks.cellWidget(row, 2).value(),
                )
        tracks = find_audio_files(self.music.path)
        self.promo_tracks.setRowCount(0)
        for row, track in enumerate(tracks):
            self.promo_tracks.insertRow(row)
            item = QTableWidgetItem(track.name)
            item.setToolTip(os.fspath(track))
            item.setData(Qt.ItemDataRole.UserRole, os.fspath(track))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.promo_tracks.setItem(row, 0, item)
            old_start, old_duration = previous.get(os.fspath(track), ("00:00:00", self.duration.value()))
            start = DropStartField(old_start)
            start.textChanged.connect(self.validate)
            start.detect_requested.connect(lambda row=row: self.start_drop_detection(row))
            duration = QDoubleSpinBox()
            duration.setMinimumWidth(88)
            duration.setFixedHeight(36)
            duration.setStyleSheet(TIMESTAMP_FIELD_STYLE)
            duration.setRange(1, 3600)
            duration.setDecimals(1)
            duration.setSuffix(" s")
            duration.setValue(old_duration)
            duration.valueChanged.connect(self.validate)
            preview = QToolButton()
            preview.setIcon(material_icon("play_arrow", self.palette().color(QPalette.ColorRole.Text).name()))
            preview.setAutoRaise(True)
            preview.setFixedSize(36, 36)
            preview.setStyleSheet(ICON_BUTTON_STYLE)
            preview.setAccessibleName(f"Play preview for {track.name}")
            preview.clicked.connect(
                lambda _checked=False, row=row, button=preview: self.toggle_promo_preview(row, button)
            )
            self.promo_tracks.setCellWidget(row, 1, start)
            self.promo_tracks.setCellWidget(row, 2, duration)
            self.promo_tracks.setCellWidget(row, 3, preview)
            start.textChanged.connect(lambda _text, row=row: self.on_promo_timing_changed(row))
            duration.valueChanged.connect(lambda _value, row=row: self.on_promo_timing_changed(row))
            self.update_promo_preview_button(row)
        self.analysis_status.setText(
            "Edit start times manually or use ✨ to detect a drop for one track."
            if tracks
            else ""
        )

    def on_promo_timing_changed(self, row: int) -> None:
        preview = self.promo_tracks.cellWidget(row, 3)
        if preview is self.promo_preview_button:
            self.stop_promo_preview()
        self.update_promo_preview_button(row)

    def update_promo_preview_button(self, row: int) -> None:
        start = self.promo_tracks.cellWidget(row, 1)
        duration = self.promo_tracks.cellWidget(row, 2)
        preview = self.promo_tracks.cellWidget(row, 3)
        if not isinstance(start, DropStartField) or not isinstance(duration, QDoubleSpinBox):
            return
        if not isinstance(preview, QToolButton):
            return
        preview.setIcon(material_icon("play_arrow", self.palette().color(QPalette.ColorRole.Text).name()))
        preview.setToolTip(
            f"Listen from {start.text() or 'the start time'} for {duration.value():g} seconds"
        )

    def toggle_promo_preview(self, row: int, button: QToolButton) -> None:
        if (
            self.promo_preview_button is button
            and self.promo_preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.stop_promo_preview()
            return

        item = self.promo_tracks.item(row, 0)
        if item is None:
            return
        try:
            start_seconds = parse_timestamp(self.promo_tracks.cellWidget(row, 1).text())
        except ValueError as exc:
            QMessageBox.warning(self, "Preview unavailable", str(exc))
            return
        duration_seconds = self.promo_tracks.cellWidget(row, 2).value()
        source = Path(item.data(Qt.ItemDataRole.UserRole))
        if not source.is_file():
            QMessageBox.warning(self, "Preview unavailable", f"Audio file not found:\n{source}")
            return

        self.stop_promo_preview()
        self.promo_preview_button = button
        self.promo_preview_start_ms = round(start_seconds * 1000)
        self.promo_preview_end_ms = round((start_seconds + duration_seconds) * 1000)
        self.promo_preview_player.setSource(QUrl.fromLocalFile(os.fspath(source)))
        if self.promo_preview_player.mediaStatus() in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self.start_promo_preview_playback()
        button.setIcon(material_icon("stop", self.palette().color(QPalette.ColorRole.Text).name()))
        self.analysis_status.setText(
            f"Listening to {source.name} from {format_timestamp(start_seconds)} for {duration_seconds:g} seconds."
        )

    def on_promo_preview_media_status(self, status) -> None:  # noqa: ANN001
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self.start_promo_preview_playback()

    def start_promo_preview_playback(self) -> None:
        if self.promo_preview_start_ms is None or self.promo_preview_button is None:
            return
        start_ms = self.promo_preview_start_ms
        self.promo_preview_start_ms = None
        self.promo_preview_player.setPosition(start_ms)
        self.promo_preview_player.play()

    def on_promo_preview_position(self, position: int) -> None:
        if self.promo_preview_end_ms and position >= self.promo_preview_end_ms:
            self.stop_promo_preview()

    def on_promo_preview_state(self, state) -> None:  # noqa: ANN001
        if state == QMediaPlayer.PlaybackState.StoppedState and self.promo_preview_button:
            self.promo_preview_button.setIcon(
                material_icon("play_arrow", self.palette().color(QPalette.ColorRole.Text).name())
            )
            self.promo_preview_button = None
            self.promo_preview_start_ms = None
            self.promo_preview_end_ms = 0

    def stop_promo_preview(self) -> None:
        button = self.promo_preview_button
        self.promo_preview_button = None
        self.promo_preview_start_ms = None
        self.promo_preview_end_ms = 0
        self.promo_preview_player.stop()
        if button:
            button.setIcon(material_icon("play_arrow", self.palette().color(QPalette.ColorRole.Text).name()))

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

    def start_drop_detection(self, row: int) -> None:
        if self.analysis_worker and self.analysis_worker.isRunning():
            return
        item = self.promo_tracks.item(row, 0)
        if item is None:
            return
        source = Path(item.data(Qt.ItemDataRole.UserRole))
        if not source.is_file():
            QMessageBox.warning(self, "Drop detection unavailable", f"Audio file not found:\n{source}")
            return
        saved_lead_in = self.settings.value("promo/drop_lead_in", 2.0, type=float)
        dialog = DropDetectionDialog(source.name, saved_lead_in, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        seconds_before = dialog.seconds_before.value()
        self.settings.setValue("promo/drop_lead_in", seconds_before)
        self.set_drop_buttons_enabled(False)
        self.analysis_worker = DropDetectionWorker([source], seconds_before)
        self.analysis_worker.progress.connect(lambda _percent, status: self.analysis_status.setText(status + "…"))
        self.analysis_worker.succeeded.connect(self.on_drop_detection_success)
        self.analysis_worker.failed.connect(
            lambda message: self.analysis_status.setText(
                f"Drop detection failed: {message}. You can still enter the start manually."
            )
        )
        self.analysis_worker.finished.connect(self.on_drop_detection_finished)
        self.analysis_status.setText(f"Analyzing {source.name} for its main drop…")
        self.validate()
        self.analysis_worker.start()

    def on_drop_detection_success(self, starts: dict[str, float]) -> None:
        for row in range(self.promo_tracks.rowCount()):
            path = self.promo_tracks.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if path in starts:
                self.promo_tracks.cellWidget(row, 1).setText(format_timestamp(starts[path]))
                self.analysis_status.setText(
                    f"✓ Proposed {format_timestamp(starts[path])} for {Path(path).name}. You can edit or preview it."
                )
                break

    def on_drop_detection_finished(self) -> None:
        worker = self.analysis_worker
        self.analysis_worker = None
        if worker:
            worker.deleteLater()
        self.set_drop_buttons_enabled(self.worker is None)
        self.validate()

    def set_drop_buttons_enabled(self, enabled: bool) -> None:
        for row in range(self.promo_tracks.rowCount()):
            start_field = self.promo_tracks.cellWidget(row, 1)
            if isinstance(start_field, DropStartField):
                start_field.detect_button.setEnabled(enabled)

    def validate(self) -> bool:
        tracks = find_audio_files(self.music.path)
        self.generate.setText("Generate Video" if len(tracks) == 1 else "Generate Videos")
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
        self.visual_effects_group.setEnabled(downstream_ready)
        self.layers_group.setEnabled(downstream_ready)
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
            missing.append("wait for drop analysis")
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
            self.artwork_preview.clear()
            self.artwork_preview.hide()
            return
        if Path(self.cover.path).suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}:
            capture = cv2.VideoCapture(self.cover.path)
            readable, frame = capture.read()
            capture.release()
            if not readable:
                self.artwork_preview.clear()
                self.artwork_preview.hide()
                return
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channels = rgb.shape
            pixmap = QPixmap.fromImage(QImage(rgb.data, width, height, channels * width, QImage.Format.Format_RGB888).copy())
        else:
            pixmap = QPixmap(self.cover.path)
        if pixmap.isNull():
            self.artwork_preview.clear()
            self.artwork_preview.hide()
            return
        self.artwork_preview.setPixmap(
            pixmap.scaled(
                94,
                94,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.artwork_preview.show()

    def set_inputs_enabled(self, enabled: bool) -> None:
        if not enabled:
            self.stop_promo_preview()
        for row in (self.music, self.cover, self.output):
            row.set_enabled(enabled)
        self.effects_panel.set_enabled(enabled)
        self.video_fade.setEnabled(enabled)
        self.audio_fade.setEnabled(enabled)
        self.mute_original_video_audio.setEnabled(
            enabled and Path(self.cover.path).suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
        )
        self.promo_tracks.setEnabled(enabled)
        self.set_drop_buttons_enabled(enabled and self.analysis_worker is None)
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
        self.stop_promo_preview()
        self.music.set_path("")
        self.cover.set_path("")
        self.output.set_path(self.settings.value("general/default_output", ""))
        self.effects_panel.clear()
        self.video_fade.setChecked(True)
        self.audio_fade.setChecked(True)
        self.mute_original_video_audio.setChecked(True)
        self.profile.setCurrentIndex(0)
        self.duration.setValue(60)
        self.fps.setValue(24)
        self.crf.setValue(18)
        self.encoding_speed.setCurrentIndex(self.encoding_speed.findData("medium"))
        self.audio_bitrate.setCurrentIndex(self.audio_bitrate.findData("320k"))
        self.progress.setValue(0)
        self.progress.hide()
        self.progress_status.clear()
        self.progress_status.hide()
        for key in ("music", "cover", "output", "promo/video_fade", "promo/audio_fade", "promo/mute_original_video_audio"):
            self.settings.remove(key)
        self.validate()

    def start_generation(self) -> None:
        if not self.validate():
            return
        tracks = find_audio_files(self.music.path)
        track_options, _ = self.promo_track_options()
        for key, value in (("music", self.music.path), ("cover", self.cover.path), ("output", self.output.path)):
            self.settings.setValue(key, value)
        effect_settings = self.effects_panel.effect_settings()
        render_settings = RenderSettings(
            fps=self.fps.value(),
            duration=self.duration.value(),
            bass_effect=effect_settings.bass_blur.enabled,
            mute_original_video_audio=self.mute_original_video_audio.isChecked(),
            video_fade=self.video_fade.isChecked(),
            audio_fade=self.audio_fade.isChecked(),
            output_size=self.profile.currentData(),
            preset=self.encoding_speed.currentData(),
            crf=self.crf.value(),
            audio_bitrate=self.audio_bitrate.currentData(),
            effects=effect_settings,
        )
        self.effects_panel.save()
        self.settings.setValue("promo/video_fade", self.video_fade.isChecked())
        self.settings.setValue("promo/audio_fade", self.audio_fade.isChecked())
        self.settings.setValue("promo/mute_original_video_audio", self.mute_original_video_audio.isChecked())
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
        effects_state = self.effects_panel.state_dict()
        self.job_completed.emit({
            "tool": "promo",
            "created": datetime.now().isoformat(timespec="seconds"),
            "source": self.music.path,
            "cover": self.cover.path,
            "output": self.output.path,
            "bass_effect": effects_state["bass_blur"]["enabled"],
            "effects": effects_state,
            "video_fade": self.video_fade.isChecked(),
            "audio_fade": self.audio_fade.isChecked(),
            "mute_original_video_audio": self.mute_original_video_audio.isChecked(),
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
