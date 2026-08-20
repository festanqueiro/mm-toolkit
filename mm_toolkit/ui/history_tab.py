"""History tab: recent job list, reload-into-tab support, and an inline preview player."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from mm_toolkit.core import media_kind, validate_media_source
from mm_toolkit.ui.helpers import page_title
from mm_toolkit.ui.widgets import MediaTransport, VideoPreviewWidget


class HistoryTab(QWidget):
    load_requested = Signal(object)

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        title = page_title("History")
        subtitle = QLabel("Recent jobs are stored only in your local application settings.")
        self.jobs = QListWidget()
        self.jobs.currentRowChanged.connect(self.on_job_selected)
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
        left = QVBoxLayout()
        left.addWidget(self.jobs, 1)
        left.addLayout(actions)

        self.outputs = QListWidget()
        self.outputs.setMaximumHeight(110)
        self.outputs.currentRowChanged.connect(self.on_output_selected)
        self.transport = MediaTransport()
        self.player = self.transport.player
        self.play_button = self.transport.play_button
        self.video_preview = VideoPreviewWidget()
        self.video_preview.setMinimumSize(320, 180)
        self.video_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.video_preview.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.video_preview.hide()
        self.player.setVideoOutput(self.video_preview)
        self.player_status = QLabel("Select a job to preview its rendered files.")
        self.player_status.setWordWrap(True)
        transport_row = QHBoxLayout()
        transport_row.addWidget(self.transport.play_button)
        transport_row.addWidget(self.transport.timeline, 1)
        transport_row.addWidget(self.transport.time_label)

        right = QVBoxLayout()
        right.addWidget(QLabel("Rendered files"))
        right.addWidget(self.outputs)
        right.addWidget(self.video_preview, 1)
        right.addLayout(transport_row)
        right.addWidget(self.player_status)

        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addLayout(right, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(body, 1)
        self.records: list[dict] = []
        self.current_outputs: list[str] = []
        self.refresh()

    def refresh(self) -> None:
        previous_key = self._record_key(self.selected_record())
        try:
            self.records = json.loads(self.settings.value("history/jobs", "[]"))
        except (TypeError, json.JSONDecodeError):
            self.records = []
        self.jobs.blockSignals(True)
        self.jobs.clear()
        for record in self.records:
            tool = {
                "promo": "Video Creator",
                "clips": "Media Cutter",
                "converter": "Media Converter",
            }.get(record.get("tool"), "Media Tool")
            source = Path(record.get("source", "")).name or "Unknown input"
            self.jobs.addItem(f"{record.get('created', '')}  •  {tool}  •  {source}")
        enabled = bool(self.records)
        self.load_button.setEnabled(enabled)
        self.open_button.setEnabled(enabled)
        matched_row = next(
            (i for i, record in enumerate(self.records) if self._record_key(record) == previous_key),
            None,
        ) if previous_key is not None else None
        target_row = matched_row if matched_row is not None else (0 if enabled else -1)
        self.jobs.setCurrentRow(target_row)
        self.jobs.blockSignals(False)
        if matched_row is None:
            # No previously-selected job to preserve (first load, cleared history, or
            # the viewed job was removed) — (re)load whatever is now selected.
            self.on_job_selected(target_row)

    @staticmethod
    def _record_key(record: dict | None) -> tuple | None:
        if record is None:
            return None
        return (record.get("created"), record.get("tool"), record.get("source"))

    def select_latest(self) -> None:
        if self.records:
            self.jobs.setCurrentRow(0)

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

    def on_job_selected(self, row: int) -> None:
        record = self.records[row] if 0 <= row < len(self.records) else None
        self.outputs.clear()
        self.current_outputs = [path for path in (record.get("outputs") or []) if Path(path).is_file()] if record else []
        for path in self.current_outputs:
            self.outputs.addItem(Path(path).name)
        if self.current_outputs:
            self.outputs.setCurrentRow(0)
        else:
            self.load_output(None)
            self.player_status.setText(
                "No rendered files found for this job." if record else "Select a job to preview its rendered files."
            )

    def on_output_selected(self, row: int) -> None:
        path = self.current_outputs[row] if 0 <= row < len(self.current_outputs) else None
        self.load_output(path)

    def load_output(self, path: str | None) -> None:
        self.player.stop()
        valid, message = validate_media_source(path) if path else (False, "")
        kind = media_kind(path) if valid else None
        self.player.setSource(QUrl.fromLocalFile(path) if valid else QUrl())
        self.video_preview.setVisible(kind == "video")
        self.play_button.setEnabled(valid)
        self.player_status.setText(message if path and not valid else "")
