"""Shared dialog and layout helpers for MM Toolkit's UI tabs."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QGroupBox, QLabel, QMessageBox, QToolButton, QVBoxLayout, QWidget


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


def collapsible_section(title: str, content_layout, expanded: bool = True) -> QGroupBox:
    """A section_group look-alike whose body folds away under a click-to-toggle header.

    Returned as a QGroupBox so callers can keep using `.setEnabled(...)` on it
    exactly like `section_group` — Qt propagates enabled state to hidden
    children too, so collapsing is purely a display concern.
    """
    group = QGroupBox()
    group.setStyleSheet(
        "QGroupBox {"
        "  border: 1px solid rgba(127, 127, 127, 0.28);"
        "  border-radius: 10px;"
        "  background-color: rgba(127, 127, 127, 0.06);"
        "}"
    )

    def label(expanded_now: bool) -> str:
        return f"{'▼' if expanded_now else '▶'}  {title}"

    toggle = QToolButton()
    toggle.setText(label(expanded))
    toggle.setCheckable(True)
    toggle.setChecked(expanded)
    toggle.setAutoRaise(True)
    toggle.setCursor(Qt.CursorShape.PointingHandCursor)
    toggle.setStyleSheet(
        "QToolButton { border: none; background: transparent; font-weight: 600; padding: 2px 0; }"
    )

    content = QWidget()
    content.setLayout(content_layout)
    content.setVisible(expanded)

    def on_toggled(checked: bool) -> None:
        content.setVisible(checked)
        toggle.setText(label(checked))

    toggle.toggled.connect(on_toggled)

    layout = QVBoxLayout(group)
    layout.setContentsMargins(12, 8, 12, 10)
    layout.setSpacing(6)
    layout.addWidget(toggle)
    layout.addWidget(content)
    return group


def page_title(text: str) -> QLabel:
    title = QLabel(text)
    title.setFont(QFont("", 24, QFont.Weight.DemiBold))
    return title
