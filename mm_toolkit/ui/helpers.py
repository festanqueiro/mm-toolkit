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


def _build_collapsible_section(title: str, content_layout, expanded: bool) -> tuple[QGroupBox, QToolButton]:
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
    return group, toggle


def collapsible_section(title: str, content_layout, expanded: bool = True) -> QGroupBox:
    """A section_group look-alike whose body folds away under a click-to-toggle header.

    Returned as a QGroupBox so callers can keep using `.setEnabled(...)` on it
    exactly like `section_group` — Qt propagates enabled state to hidden
    children too, so collapsing is purely a display concern. For a set of
    sections where only one should be open at a time, use `Accordion`
    instead — it calls this internally and adds that exclusivity.
    """
    group, _toggle = _build_collapsible_section(title, content_layout, expanded)
    return group


class Accordion:
    """A group of collapsible_section()s where opening one closes the others.

    Prevents the "every section expanded at once" pile-up on tabs with many
    optional groups — build each section via `.section(...)` instead of
    calling `collapsible_section` directly, and they'll stay mutually
    exclusive.
    """

    def __init__(self):
        self._toggles: list[QToolButton] = []
        self._toggle_for_group: dict[QGroupBox, QToolButton] = {}

    def section(self, title: str, content_layout, expanded: bool = False) -> QGroupBox:
        group, toggle = _build_collapsible_section(title, content_layout, expanded)
        toggle.toggled.connect(lambda checked, toggle=toggle: self._on_toggled(toggle, checked))
        self._toggles.append(toggle)
        self._toggle_for_group[group] = toggle
        return group

    def _on_toggled(self, toggle: QToolButton, checked: bool) -> None:
        if not checked:
            return
        for other in self._toggles:
            if other is not toggle and other.isChecked():
                other.setChecked(False)

    def bind_stretch(self, group: QGroupBox, layout, expanded_stretch: int = 1) -> None:
        """Give `group` a stretch factor in `layout` only while it's expanded.

        Without this, a section holding a widget with a natural Expanding
        size policy (e.g. a table) keeps claiming leftover space even while
        collapsed, instead of shrinking to just its header height.
        """
        toggle = self._toggle_for_group[group]

        def sync(checked: bool) -> None:
            layout.setStretchFactor(group, expanded_stretch if checked else 0)

        toggle.toggled.connect(sync)
        sync(toggle.isChecked())


def page_title(text: str) -> QLabel:
    title = QLabel(text)
    title.setFont(QFont("", 24, QFont.Weight.DemiBold))
    return title
