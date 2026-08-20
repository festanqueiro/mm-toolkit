"""Settings tab: app-wide defaults (output folder, naming, conflict policy)."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from mm_toolkit.ui.helpers import page_title, section_group
from mm_toolkit.ui.widgets import PathRow


class SettingsTab(QWidget):
    changed = Signal()

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        title = page_title("Settings")
        subtitle = QLabel("Defaults shared by all Media Tools features.")
        self.default_output = PathRow("Choose default export folder", "directory")
        self.output_status = QLabel("")
        self.notify_finished = QCheckBox("Send a notification when processing finishes")
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

        settings_inputs = (
            self.default_output.edit,
            self.default_output.button,
            self.notify_finished,
            self.promo_naming,
            self.clip_naming,
            self.conflict_policy,
        )
        for widget in settings_inputs:
            widget.setMinimumHeight(42)
        self.promo_naming.setMinimumWidth(420)
        self.clip_naming.setMinimumWidth(420)
        self.conflict_policy.setMinimumWidth(260)
        input_font = QFont()
        input_font.setPointSize(14)
        self.promo_naming.setFont(input_font)
        self.clip_naming.setFont(input_font)
        self.conflict_policy.setFont(input_font)

        form = QFormLayout()
        form.setSpacing(18)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
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
