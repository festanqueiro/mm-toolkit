"""Reusable, drag-reorderable visual-effects cascade panel.

Wraps `mm_toolkit.effects.EffectSettings` in Qt controls (a draggable stack
of Bass Blur / Rotate / VHS / Glitch rows, plus a Background layer) with
QSettings persistence, so any tab can drop in `EffectsPanel(settings,
"some_prefix")` to gain the same effect cascade the Video Generator uses,
without duplicating widget wiring. New effects are added by extending
`_EFFECT_DEFS` and `mm_toolkit.effects.apply_effect_chain` together.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from mm_toolkit.effects import (
    BackgroundSettings,
    BassBlurSettings,
    EffectSettings,
    GlitchSettings,
    RotateSettings,
    VhsSettings,
)
from mm_toolkit.ui.widgets import PathRow

_DEFAULT_BACKGROUND_COLOR = (25, 25, 29)

# (key, display label, has a dry/wet amount slider)
_EFFECT_DEFS: tuple[tuple[str, str, bool], ...] = (
    ("bass_blur", "Bass-reactive Blur", False),
    ("rotate", "Rotate", False),
    ("vhs", "VHS", True),
    ("glitch", "Glitch", True),
)


class _EffectRow(QWidget):
    """One draggable row: enable checkbox plus that effect's own controls."""

    changed = Signal()

    def __init__(self, key: str, label: str, has_amount: bool):
        super().__init__()
        self.key = key
        self.checkbox = QCheckBox(label)
        self.amount: QSlider | None = None
        self.amount_label: QLabel | None = None
        self.speed: QDoubleSpinBox | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        handle = QLabel("☰")
        handle.setToolTip("Drag to reorder")
        handle.setFixedWidth(20)
        layout.addWidget(handle)
        layout.addWidget(self.checkbox)
        layout.addStretch(1)

        if key == "rotate":
            self.speed = QDoubleSpinBox()
            self.speed.setRange(0.1, 200.0)
            self.speed.setDecimals(1)
            self.speed.setValue(33.3)
            self.speed.setSuffix(" RPM")
            self.speed.setFixedWidth(110)
            self.speed.setEnabled(False)
            self.speed.valueChanged.connect(self.changed)
            layout.addWidget(self.speed)
        elif has_amount:
            self.amount = QSlider(Qt.Orientation.Horizontal)
            self.amount.setRange(0, 100)
            self.amount.setValue(50)
            self.amount.setFixedWidth(120)
            self.amount.setEnabled(False)
            self.amount_label = QLabel("50%")
            self.amount_label.setFixedWidth(36)
            self.amount_label.setEnabled(False)
            self.amount.valueChanged.connect(lambda value: self.amount_label.setText(f"{value}%"))
            self.amount.valueChanged.connect(self.changed)
            layout.addWidget(self.amount)
            layout.addWidget(self.amount_label)

        self.checkbox.toggled.connect(self._sync_enabled_state)
        self.checkbox.toggled.connect(self.changed)

    def _sync_enabled_state(self, checked: bool) -> None:
        if self.speed is not None:
            self.speed.setEnabled(checked)
        if self.amount is not None:
            self.amount.setEnabled(checked)
            self.amount_label.setEnabled(checked)

    def set_row_enabled(self, enabled: bool) -> None:
        self.checkbox.setEnabled(enabled)
        checked = enabled and self.checkbox.isChecked()
        if self.speed is not None:
            self.speed.setEnabled(checked)
        if self.amount is not None:
            self.amount.setEnabled(checked)
            self.amount_label.setEnabled(checked)


class EffectsPanel(QWidget):
    """A draggable Bass Blur/Rotate/VHS/Glitch stack, plus a Background layer."""

    changed = Signal()

    def __init__(self, settings: QSettings, prefix: str):
        super().__init__()
        self.settings = settings
        self.prefix = prefix
        self.background_color = _DEFAULT_BACKGROUND_COLOR

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setSpacing(2)
        self.list.setFrameShape(self.list.Shape.NoFrame)
        self.list.model().rowsMoved.connect(self.changed)

        self.rows: dict[str, _EffectRow] = {}
        self.items: dict[str, QListWidgetItem] = {}
        for key, label, has_amount in _EFFECT_DEFS:
            row = _EffectRow(key, label, has_amount)
            row.changed.connect(self.changed)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            item.setSizeHint(row.sizeHint())
            self.rows[key] = row
            self.items[key] = item
        self.list.setFixedHeight(len(_EFFECT_DEFS) * 40 + 8)
        self.rows["bass_blur"].checkbox.setChecked(True)

        self.background_mode = QComboBox()
        self.background_mode.addItem("Solid color", "color")
        self.background_mode.addItem("Image", "image")
        self.background_color_button = QPushButton()
        self.background_color_button.setFixedWidth(64)
        self.background_color_button.clicked.connect(self.choose_background_color)
        self.background_image = PathRow(
            "Choose background image",
            "file",
            "Images (*.png *.jpg *.jpeg *.webp *.tif *.tiff)",
        )
        self._update_background_color_swatch()

        background_form = QFormLayout()
        background_form.setSpacing(10)
        background_form.addRow("Background", self.background_mode)
        background_form.addRow("Color", self.background_color_button)
        background_form.addRow("Image", self.background_image)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        hint = QLabel("Drag rows to change the order effects are applied in.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)
        layout.addWidget(self.list)
        layout.addLayout(background_form)

        self.background_mode.currentIndexChanged.connect(self._sync_background_visibility)
        self.background_mode.currentIndexChanged.connect(self.changed)
        self.background_image.changed.connect(self.changed)
        self._sync_background_visibility()

        self.restore()

    def _sync_background_visibility(self) -> None:
        is_image = self.background_mode.currentData() == "image"
        self.background_color_button.setVisible(not is_image)
        self.background_image.setVisible(is_image)

    def choose_background_color(self) -> None:
        color = QColorDialog.getColor(QColor(*self.background_color), self, "Choose background color")
        if color.isValid():
            self.background_color = (color.red(), color.green(), color.blue())
            self._update_background_color_swatch()
            self.changed.emit()

    def _update_background_color_swatch(self) -> None:
        r, g, b = self.background_color
        self.background_color_button.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); border: 1px solid palette(mid); border-radius: 6px;"
        )
        self.background_color_button.setText(f"#{r:02x}{g:02x}{b:02x}")

    def order(self) -> list[str]:
        return [self.list.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.list.count())]

    def effect_settings(self) -> EffectSettings:
        rotate_row = self.rows["rotate"]
        vhs_row = self.rows["vhs"]
        glitch_row = self.rows["glitch"]
        return EffectSettings(
            background=BackgroundSettings(
                mode=self.background_mode.currentData() or "color",
                color=self.background_color,
                image_path=self.background_image.path or None,
            ),
            order=tuple(self.order()),
            bass_blur=BassBlurSettings(enabled=self.rows["bass_blur"].checkbox.isChecked()),
            rotate=RotateSettings(enabled=rotate_row.checkbox.isChecked(), rpm=rotate_row.speed.value()),
            vhs=VhsSettings(enabled=vhs_row.checkbox.isChecked(), amount=vhs_row.amount.value() / 100),
            glitch=GlitchSettings(enabled=glitch_row.checkbox.isChecked(), amount=glitch_row.amount.value() / 100),
        )

    def set_enabled(self, enabled: bool) -> None:
        self.list.setEnabled(enabled)
        for row in self.rows.values():
            row.set_row_enabled(enabled)
        self.background_mode.setEnabled(enabled)
        self.background_color_button.setEnabled(enabled)
        self.background_image.set_enabled(enabled)

    def _reorder(self, order: list[str]) -> None:
        wanted = [key for key in order if key in self.items]
        wanted += [key for key, _label, _amount in _EFFECT_DEFS if key not in wanted]
        for index, key in enumerate(wanted):
            item = self.items[key]
            current_index = self.list.row(item)
            if current_index != index:
                self.list.takeItem(current_index)
                self.list.insertItem(index, item)
                self.list.setItemWidget(item, self.rows[key])

    def state_dict(self) -> dict:
        settings = self.effect_settings()
        return {
            "order": list(settings.order),
            "bass_blur": {"enabled": settings.bass_blur.enabled},
            "rotate": {"enabled": settings.rotate.enabled, "rpm": settings.rotate.rpm},
            "vhs": {"enabled": settings.vhs.enabled, "amount": settings.vhs.amount},
            "glitch": {"enabled": settings.glitch.enabled, "amount": settings.glitch.amount},
            "background": {
                "mode": settings.background.mode,
                "color": list(settings.background.color),
                "image_path": settings.background.image_path,
            },
        }

    def apply_state(self, state: dict) -> None:
        if not state:
            return
        self._reorder(state.get("order", []))
        bass = state.get("bass_blur", {})
        self.rows["bass_blur"].checkbox.setChecked(bool(bass.get("enabled", True)))
        rotate = state.get("rotate", {})
        rotate_row = self.rows["rotate"]
        rotate_row.checkbox.setChecked(bool(rotate.get("enabled", False)))
        rotate_row.speed.setValue(float(rotate.get("rpm", 33.3)))
        vhs = state.get("vhs", {})
        vhs_row = self.rows["vhs"]
        vhs_row.checkbox.setChecked(bool(vhs.get("enabled", False)))
        vhs_row.amount.setValue(round(float(vhs.get("amount", 0.5)) * 100))
        glitch = state.get("glitch", {})
        glitch_row = self.rows["glitch"]
        glitch_row.checkbox.setChecked(bool(glitch.get("enabled", False)))
        glitch_row.amount.setValue(round(float(glitch.get("amount", 0.5)) * 100))
        background = state.get("background", {})
        mode = background.get("mode", "color")
        self.background_mode.setCurrentIndex(max(0, self.background_mode.findData(mode)))
        color = background.get("color")
        if color and len(color) == 3:
            self.background_color = tuple(int(component) for component in color)
            self._update_background_color_swatch()
        self.background_image.set_path(background.get("image_path") or "")
        self._sync_background_visibility()

    def restore(self) -> None:
        raw = self.settings.value(f"{self.prefix}/effects_state", "")
        if not raw:
            return
        try:
            self.apply_state(json.loads(raw))
        except (TypeError, ValueError):
            pass

    def save(self) -> None:
        self.settings.setValue(f"{self.prefix}/effects_state", json.dumps(self.state_dict()))

    def clear(self) -> None:
        self._reorder([key for key, _label, _amount in _EFFECT_DEFS])
        self.rows["bass_blur"].checkbox.setChecked(True)
        rotate_row = self.rows["rotate"]
        rotate_row.checkbox.setChecked(False)
        rotate_row.speed.setValue(33.3)
        for key in ("vhs", "glitch"):
            row = self.rows[key]
            row.checkbox.setChecked(False)
            row.amount.setValue(50)
        self.background_mode.setCurrentIndex(0)
        self.background_color = _DEFAULT_BACKGROUND_COLOR
        self._update_background_color_swatch()
        self.background_image.set_path("")
        self.settings.remove(f"{self.prefix}/effects_state")
