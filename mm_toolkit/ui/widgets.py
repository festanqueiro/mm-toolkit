"""Shared widgets used across MM Toolkit's UI tabs."""

from __future__ import annotations

import os
from pathlib import Path

from typing import Callable

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QWidget

from mm_toolkit.core import format_timestamp


class VideoPreviewWidget(QVideoWidget):
    """Responsive 16:9 preview surface that preserves the source aspect ratio."""

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return max(220, round(width * 9 / 16))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(640, 360)


class MediaTransport(QObject):
    """Play/pause button, seek slider, and time label wired to a QMediaPlayer.

    A non-visual controller: it owns the QMediaPlayer, QAudioOutput, and the
    three control widgets, and wires the standard play/seek/duration state
    machine between them. It does not lay the widgets out itself, since
    callers differ (a simple row vs. widgets interspersed with other
    controls) — place `.play_button` / `.timeline` / `.time_label` in
    whatever layout fits. Callers needing extra behavior (e.g. clip-preview
    bounds, media-status priming) connect additional slots directly to
    `.player` / `.timeline` alongside this controller's own wiring, rather
    than overriding it.
    """

    def __init__(self, parent: QObject | None = None, on_toggle: Callable[[], None] | None = None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.player_audio = QAudioOutput(self)
        self.player.setAudioOutput(self.player_audio)
        self.play_button = QPushButton("▶ Play")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(on_toggle or self.toggle_playback)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.sliderPressed.connect(self.on_timeline_pressed)
        self.timeline.sliderMoved.connect(self.on_timeline_moved)
        self.timeline.sliderReleased.connect(self.on_timeline_released)
        self.timeline_was_playing = False
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.player.positionChanged.connect(self.on_player_position)
        self.player.durationChanged.connect(self.on_player_duration)
        self.player.playbackStateChanged.connect(self.on_playback_state)

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
        self.update_time_label(position)

    def update_time_label(self, position: int) -> None:
        self.time_label.setText(
            f"{format_timestamp(position / 1000)} / {format_timestamp(self.player.duration() / 1000)}"
        )

    def on_timeline_pressed(self) -> None:
        self.timeline_was_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if self.timeline_was_playing:
            self.player.pause()

    def on_timeline_moved(self, position: int) -> None:
        self.player.setPosition(position)
        self.update_time_label(position)

    def on_timeline_released(self) -> None:
        position = self.timeline.value()
        self.player.setPosition(position)
        self.update_time_label(position)
        if self.timeline_was_playing:
            self.player.play()
        self.timeline_was_playing = False

    def on_player_duration(self, duration: int) -> None:
        self.timeline.setRange(0, max(0, duration))
        self.on_player_position(self.player.position())


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
        self.edit.setMinimumHeight(36)
        self.edit.setStyleSheet(
            "QLineEdit {"
            "  color: palette(text);"
            "  background-color: palette(base);"
            "  border: 1px solid palette(mid);"
            "  border-radius: 6px;"
            "  padding: 5px 9px;"
            "}"
        )
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
