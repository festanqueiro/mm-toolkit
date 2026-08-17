"""History tab: recent job list, reload-into-tab support."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

from mm_toolkit.ui.helpers import page_title


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
                "clips": "Media Cutter",
                "converter": "Media Converter",
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
