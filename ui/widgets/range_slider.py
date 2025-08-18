# file: ui/widgets/range_slider.py
from __future__ import annotations
from typing import Tuple

from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class RangeSlider(QWidget):
    """Minimal dual-handle range slider (horizontal).

    Read-only by default; editing will be enabled in a later step.
    Only exposes what's needed for displaying the range.

    Signals:
        valuesChanged(int, int): emitted when values programmatically change (future: on drag)
    """
    valuesChanged = pyqtSignal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min = 0
        self._max = 100
        self._left = 0
        self._right = 100
        self._handle_radius = 6  # px
        self.setMinimumHeight(24)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # no keyboard for now

    # --- Public API ---
    def setRange(self, min_value: int, max_value: int) -> None:
        if max_value < min_value:
            min_value, max_value = max_value, min_value
        self._min = int(min_value)
        self._max = int(max_value)
        self._left = max(self._min, min(self._left, self._max))
        self._right = max(self._left, min(self._right, self._max))
        self.update()

    def setValues(self, left: int, right: int) -> None:
        left = int(max(self._min, min(left, self._max)))
        right = int(max(left, min(right, self._max)))
        changed = (left != self._left) or (right != self._right)
        self._left, self._right = left, right
        if changed:
            self.valuesChanged.emit(self._left, self._right)
            self.update()

    def values(self) -> Tuple[int, int]:
        return self._left, self._right

    # --- Painting ---
    def paintEvent(self, _e) -> None:  # type: ignore[override]
        if self._max <= self._min:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(8, 9, -8, -9)  # track bounds
        # Track
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.setBrush(QBrush(self.palette().mid().color()))
        p.drawRoundedRect(rect, 3, 3)

        # Selected range
        lx = rect.left() + (rect.width()) * (self._left - self._min) / (self._max - self._min)
        rx = rect.left() + (rect.width()) * (self._right - self._min) / (self._max - self._min)
        sel = QRectF(lx, rect.top(), max(2.0, rx - lx), rect.height())
        p.setBrush(QBrush(self.palette().highlight().color()))
        p.drawRoundedRect(sel, 3, 3)

        # Handles (dots, since read-only)
        p.setBrush(QBrush(self.palette().base().color()))
        p.setPen(QPen(self.palette().dark().color()))
        p.drawEllipse(int(lx), rect.center().y(), 2, 2)
        p.drawEllipse(int(rx), rect.center().y(), 2, 2)
        p.end()