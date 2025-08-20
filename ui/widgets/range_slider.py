# file: ui/widgets/range_slider.py
from __future__ import annotations
from typing import Tuple, Optional

from PyQt6.QtCore import Qt, QRectF, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class RangeSlider(QWidget):
    """Dual‑handle horizontal range slider.

    - Supports dragging either handle; keeps left <= right within [min,max].
    - Emits `valuesChanged(int, int)` when values change (user or programmatic).
    - Keyboard is intentionally disabled for now (NoFocus) to keep UX simple.
    """

    valuesChanged = pyqtSignal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min = 0
        self._max = 100
        self._left = 0
        self._right = 100
        self._handle_radius = 8  # px
        self._active: Optional[str] = None  # 'left' | 'right' | None
        self.setMinimumHeight(28)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)

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

        rect = self.rect().adjusted(10, 11, -10, -11)  # track bounds
        # Track
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.setBrush(QBrush(self.palette().mid().color()))
        p.drawRoundedRect(rect, 3, 3)

        # Map values → x
        rng = max(1, (self._max - self._min))
        lx = rect.left() + (rect.width()) * (self._left - self._min) / rng
        rx = rect.left() + (rect.width()) * (self._right - self._min) / rng

        # Selected range
        sel = QRectF(lx, rect.top(), max(2.0, rx - lx), rect.height())
        p.setBrush(QBrush(self.palette().highlight().color()))
        p.drawRoundedRect(sel, 3, 3)

        # Handles
        cy = rect.center().y()
        r = self._handle_radius
        p.setBrush(QBrush(self.palette().base().color()))
        p.setPen(QPen(self.palette().dark().color()))
        p.drawEllipse(int(lx) - r, cy - r, 2 * r, 2 * r)
        p.drawEllipse(int(rx) - r, cy - r, 2 * r, 2 * r)
        p.end()

    # --- Mouse handling ---
    def mousePressEvent(self, e) -> None:  # type: ignore[override]
        if not self.isEnabled() or self._max <= self._min:
            return
        rect = self.rect().adjusted(10, 11, -10, -11)
        rng = max(1, (self._max - self._min))
        lx = rect.left() + (rect.width()) * (self._left - self._min) / rng
        rx = rect.left() + (rect.width()) * (self._right - self._min) / rng
        pos_x = e.position().x() if hasattr(e, 'position') else e.x()
        # pick the nearest handle
        self._active = 'left' if abs(pos_x - lx) <= abs(pos_x - rx) else 'right'
        self._drag_to(pos_x)

    def mouseMoveEvent(self, e) -> None:  # type: ignore[override]
        if not self.isEnabled() or self._active is None:
            return
        pos_x = e.position().x() if hasattr(e, 'position') else e.x()
        self._drag_to(pos_x)

    def mouseReleaseEvent(self, _e) -> None:  # type: ignore[override]
        self._active = None

    # --- internals ---
    def _drag_to(self, pos_x: float) -> None:
        rect = self.rect().adjusted(10, 11, -10, -11)
        if rect.width() <= 0:
            return
        # clamp x to track
        x = max(rect.left(), min(pos_x, rect.right()))
        # map x → value
        rng = max(1, (self._max - self._min))
        v = self._min + int(round((x - rect.left()) * rng / rect.width()))
        if self._active == 'left':
            self.setValues(v, max(v, self._right))
        elif self._active == 'right':
            self.setValues(min(v, self._max), max(self._left, v))
