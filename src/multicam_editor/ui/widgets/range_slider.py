# file: ui/widgets/range_slider.py
from __future__ import annotations
from typing import Tuple, Optional

from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class RangeSlider(QWidget):
    """
    Dual-handle horizontal range slider with overlap-safe rendering.

    Hardening for startup:
    - Never draws when track width/height <= 0 or range invalid.
    - No divisions by zero (guarded mapping).
    - Paint wrapped defensively; never calls QPainter.end() if not active.
    - Mouse handlers bail out if geometry is tiny.
    """

    valuesChanged = pyqtSignal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min = 0
        self._max = 100
        self._left = 0
        self._right = 100
        self._handle_radius = 8
        self._active: Optional[str] = None
        self._last_active: str = "right"
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

    # --- Geometry helpers ---
    def _track_rect(self) -> Optional[QRectF]:
        r = QRectF(self.rect()).adjusted(10, 11, -10, -11)
        if r.width() <= 0.0 or r.height() <= 0.0:
            return None
        return r

    def _value_to_x(self, v: int, rect: QRectF) -> float:
        rng = float(max(1, (self._max - self._min)))
        return float(rect.left()) + float(rect.width()) * (float(v - self._min) / rng)

    def _x_to_value(self, x: float, rect: QRectF) -> int:
        w = float(max(1.0, rect.width()))
        t = (float(x) - float(rect.left())) / w
        rng = float(max(1, (self._max - self._min)))
        return int(round(self._min + t * rng))

    def _hit_handle(self, pos_x: float, pos_y: float, rect: QRectF) -> Optional[str]:
        cy = float(rect.center().y())
        lx = self._value_to_x(self._left, rect)
        rx = self._value_to_x(self._right, rect)
        r = float(self._handle_radius)
        y_ok = abs(pos_y - cy) <= (r + 3.0)
        left_hit = y_ok and (lx - r <= pos_x <= lx + r)
        right_hit = y_ok and (rx - r <= pos_x <= rx + r)
        if left_hit and right_hit:
            dl = abs(pos_x - lx); dr = abs(pos_x - rx)
            if dl < dr:
                return "left"
            if dr < dl:
                return "right"
            return self._last_active
        if right_hit:
            return "right"
        if left_hit:
            return "left"
        return None

    # --- Painting ---
    def paintEvent(self, _e) -> None:  # type: ignore[override]
        if self._max <= self._min:
            return
        rect = self._track_rect()
        if rect is None:
            return
        p = QPainter()
        try:
            if not p.begin(self):
                return
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Track
            p.setPen(QPen(Qt.PenStyle.NoPen))
            p.setBrush(QBrush(self.palette().mid().color()))
            p.drawRoundedRect(rect, 3, 3)

            # Value → x
            lx = self._value_to_x(self._left, rect)
            rx = self._value_to_x(self._right, rect)

            # Selected range
            sel = QRectF(lx, rect.top(), max(2.0, rx - lx), rect.height())
            p.setBrush(QBrush(self.palette().highlight().color()))
            p.drawRoundedRect(sel, 3, 3)

            # Ticks
            tick_pen = QPen(self.palette().dark().color()); tick_pen.setWidth(2)
            p.setPen(tick_pen)
            p.drawLine(int(lx), int(rect.top()), int(lx), int(rect.top() + 6))
            p.drawLine(int(rx), int(rect.top()), int(rx), int(rect.top() + 6))

            # Keep handles visible when overlapping (visual only)
            cy = float(rect.center().y())
            r = float(self._handle_radius)
            min_sep_px = 2.0 * r + 2.0
            lx_draw, rx_draw = lx, rx
            if abs(rx - lx) < min_sep_px:
                if self._active == "right":
                    rx_draw = min(float(rect.right()), lx + min_sep_px)
                elif self._active == "left":
                    lx_draw = max(float(rect.left()), rx - min_sep_px)
                else:
                    mid = (lx + rx) / 2.0
                    lx_draw = max(float(rect.left()), mid - min_sep_px / 2.0)
                    rx_draw = min(float(rect.right()), mid + min_sep_px / 2.0)

            # Handles
            base_brush = QBrush(self.palette().base().color())
            dark_pen = QPen(self.palette().dark().color()); dark_pen.setWidth(1)
            strong_pen = QPen(self.palette().dark().color()); strong_pen.setWidth(2)

            def draw_handle(x: float, active: bool) -> None:
                p.setBrush(base_brush)
                p.setPen(strong_pen if active else dark_pen)
                p.drawEllipse(int(x - r), int(cy - r), int(2 * r), int(2 * r))

            if self._active == "right":
                draw_handle(lx_draw, False); draw_handle(rx_draw, True)
            elif self._active == "left":
                draw_handle(rx_draw, False); draw_handle(lx_draw, True)
            else:
                draw_handle(lx_draw, False); draw_handle(rx_draw, False)
        except Exception:
            # Silent guard against paint-time exceptions causing native aborts
            pass
        finally:
            if p.isActive():
                p.end()

    # --- Mouse handling ---
    def mousePressEvent(self, e) -> None:  # type: ignore[override]
        if not self.isEnabled() or self._max <= self._min:
            return
        rect = self._track_rect()
        if rect is None:
            return
        pos_x = float(e.position().x() if hasattr(e, "position") else e.x())
        pos_y = float(e.position().y() if hasattr(e, "position") else e.y())

        active = self._hit_handle(pos_x, pos_y, rect)
        if active is None:
            lx = self._value_to_x(self._left, rect)
            rx = self._value_to_x(self._right, rect)
            dl = abs(pos_x - lx); dr = abs(pos_x - rx)
            active = "left" if dl < dr else ("right" if dr < dl else self._last_active)

        self._active = active
        self._last_active = active
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self._drag_to(pos_x)

    def mouseMoveEvent(self, e) -> None:  # type: ignore[override]
        if not self.isEnabled() or self._active is None:
            return
        rect = self._track_rect()
        if rect is None:
            return
        pos_x = float(e.position().x() if hasattr(e, "position") else e.x())
        self._drag_to(pos_x)

    def mouseReleaseEvent(self, _e) -> None:  # type: ignore[override]
        self._active = None
        self.unsetCursor()

    # --- internals ---
    def _drag_to(self, pos_x: float) -> None:
        rect = self._track_rect()
        if rect is None:
            return
        x = max(float(rect.left()), min(float(pos_x), float(rect.right())))
        v = self._x_to_value(x, rect)

        if self._active == "left":
            self.setValues(min(max(self._min, v), self._right), self._right)
        elif self._active == "right":
            self.setValues(self._left, max(self._left, min(v, self._max)))
