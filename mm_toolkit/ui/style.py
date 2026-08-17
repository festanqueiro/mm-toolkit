"""Shared Qt style-sheet constants and icon helpers for MM Toolkit's UI."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

TIMESTAMP_FIELD_STYLE = (
    "QLineEdit, QDoubleSpinBox { background-color: palette(base); "
    "border: 1px solid palette(mid); border-radius: 6px; padding: 5px 9px; "
    "color: palette(text); }"
    "QLineEdit:focus, QDoubleSpinBox:focus { border-color: palette(highlight); }"
)
TIMESTAMP_BUTTON_STYLE = (
    "QPushButton, QToolButton { background-color: palette(button); border: 1px solid palette(mid); "
    "border-radius: 6px; padding: 0 12px; color: palette(button-text); }"
    "QPushButton:hover, QToolButton:hover { background-color: palette(midlight); }"
    "QPushButton:pressed, QToolButton:pressed { background-color: palette(mid); }"
)
ICON_BUTTON_STYLE = (
    "QToolButton { background: transparent; border: 0; border-radius: 6px; padding: 6px; }"
    "QToolButton:hover { background: palette(midlight); }"
    "QToolButton:pressed { background: palette(mid); }"
)


def bundled_asset(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets" / name


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
