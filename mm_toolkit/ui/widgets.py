"""Shared widgets used across MM Toolkit's UI tabs."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


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
