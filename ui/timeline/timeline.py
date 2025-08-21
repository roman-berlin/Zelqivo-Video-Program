# file: ui/timeline/timeline.py  (adds clear_clips())
from __future__ import annotations
from typing import List, Optional

from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt6.QtGui import QBrush, QPen, QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsRectItem


class ClipItem(QGraphicsRectItem):
    HEIGHT = 80
    def __init__(self, path: str, title: str, width: float, grid_px: int):
        super().__init__(0, 0, max(60.0, width), float(self.HEIGHT))
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setAcceptHoverEvents(True)
        self.path = path
        self._title = title
        self._grid_px = grid_px
        self._bg = QColor(64, 64, 64)
        self._bg_selected = QColor(90, 90, 120)
        self._border = QColor(32, 32, 32)
        self._text = QColor(240, 240, 240)
        self._font = QFont(); self._font.setPointSizeF(9.5)

    def itemChange(self, change, value):  # type: ignore[override]
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionChange:
            p = value
            return type(p)(max(0.0, p.x()), 0.0)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        x = self.x(); snapped = round(x / self._grid_px) * self._grid_px
        self.setPos(max(0.0, float(snapped)), 0.0)
        super().mouseReleaseEvent(event)

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self._border))
        painter.setBrush(QBrush(self._bg_selected if self.isSelected() else self._bg))
        painter.drawRoundedRect(self.rect(), 6, 6)
        painter.setPen(self._text); painter.setFont(self._font)
        pad = 8; r = self.rect().adjusted(pad, 0, -pad, 0)
        fm = QFontMetrics(self._font)
        text = fm.elidedText(self._title, Qt.TextElideMode.ElideMiddle, int(max(20, r.width())))
        painter.drawText(r, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)


class TimelineScene(QGraphicsScene):
    orderChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(0, 0, 6000, ClipItem.HEIGHT)
        self._grid_px = 50
        self._clips: list[ClipItem] = []

    def drawBackground(self, painter: QPainter, rect: QRectF):  # type: ignore[override]
        painter.fillRect(rect, QColor(20, 20, 20))
        pen = QPen(QColor(60, 60, 60)); pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        left = int(rect.left()) - (int(rect.left()) % self._grid_px)
        for x in range(left, int(rect.right()) + self._grid_px, self._grid_px):
            painter.drawLine(x, 0, x, ClipItem.HEIGHT)

    def clear_clips(self) -> None:
        """
        Remove all clip items from the scene and reset internal state.

        This method iterates over the existing `_clips` list and removes
        each `ClipItem` from the scene before clearing the list. It does
        not emit an `orderChanged` signal directly – callers that care
        about order updates should emit or rebuild as needed.
        """
        for c in list(self._clips):
            self.removeItem(c)
        self._clips.clear()

    # Backwards‑compatibility alias expected by TimelineAdapter
    def clear_all(self) -> None:
        """Alias for `clear_clips` to match the adapter API."""
        self.clear_clips()

    def add_clips(
        self,
        paths: List[str],
        titles: Optional[List[str]] = None,
        cap: int = 10,
    ) -> List[str]:
        """
        Add multiple clips to the timeline at once.

        This convenience method iterates over the provided paths (up to
        the remaining capacity) and delegates to `add_clip` for each
        individual addition. It collects and returns the list of paths
        that were successfully added. After adding, the internal clip
        order is emitted via `orderChanged`.

        :param paths: A list of file paths to add.
        :param titles: Optional custom titles corresponding to each path.
        :param cap: Maximum number of clips allowed in the timeline.
        :return: The subset of `paths` that were added.
        """
        added: List[str] = []
        # Early exit if no capacity remains
        if len(self._clips) >= cap:
            return added
        titles = titles or [None] * len(paths)  # type: ignore[list-item]
        remain = max(0, cap - len(self._clips))
        for i, p in enumerate(paths[:remain]):
            title = titles[i] if i < len(titles) and titles[i] else None
            item = self.add_clip(p, title=title, cap=cap)
            if item is not None:
                added.append(p)
        # Emit order change once for the batch
        if added:
            self._emit_order()
        return added

    def add_clip(
        self,
        path: str,
        *,
        title: Optional[str] = None,
        cap: int = 10,
    ) -> Optional[ClipItem]:
        """
        Add a single clip to the timeline and return the created item.

        The clip is appended to the end of the internal `_clips` list,
        positioned based on the widths of existing clips plus a small
        margin. If the cap has already been reached, no item is added
        and `None` is returned. The caller is responsible for emitting
        any order change signals if needed.
        """
        # respect capacity
        if len(self._clips) >= cap:
            return None
        # Derive a display title from the filename if not provided
        if not title:
            title = path.split("/")[-1] if path else ""
        # Fixed width for now; could be scaled based on duration
        width = 320.0
        item = ClipItem(path, title, width, self._grid_px)
        # Compute x position: sum of widths + margin (8px per existing clip)
        x = sum(c.rect().width() for c in self._clips) + (len(self._clips) * 8)
        item.setPos(x, 0)
        self.addItem(item)
        self._clips.append(item)
        return item

    def find_item_by_path(self, path: str) -> Optional[ClipItem]:
        """
        Find and return the clip item corresponding to a given path.
        If no matching item exists, returns `None`.
        """
        for c in self._clips:
            if c.path == path:
                return c
        return None

    def select_by_path(self, path: str) -> None:
        for c in self._clips:
            c.setSelected(c.path == path)

    def paths_order(self) -> List[str]:
        return [c.path for c in self._sorted()]

    def relayout_compact(self) -> None:
        x = 0.0
        for c in self._sorted():
            c.setPos(x, 0); x += c.rect().width() + 8
        self._emit_order()

    def _sorted(self) -> List[ClipItem]:
        return sorted(self._clips, key=lambda c: c.x())

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        super().mouseReleaseEvent(event)
        self.relayout_compact()

    def _emit_order(self) -> None:
        self.orderChanged.emit([c.path for c in self._sorted()])


class TimelineView(QGraphicsView):
    def __init__(self, scene: TimelineScene, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("timelineView")
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._space_pressed = False; self.scale(1.0, 1.0)

    def wheelEvent(self, event):  # type: ignore[override]
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y(); factor = 1.15 if angle > 0 else 1/1.15
            self.scale(factor, 1.0); event.accept(); return
        super().wheelEvent(event)

    def keyPressEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key.Key_Space and not self._space_pressed:
            self._space_pressed = True; self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            event.accept(); return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key.Key_Space and self._space_pressed:
            self._space_pressed = False; self.setDragMode(QGraphicsView.DragMode.NoDrag)
            event.accept(); return
        super().keyReleaseEvent(event)

    # Optional API expected by TimelineAdapter
    def fit_width_if_needed(self) -> None:
        """
        Adjust the view's transformation to ensure all clips are visible
        horizontally. This is a no‑op when the scene width fits within
        the current viewport.

        The implementation calculates the bounding rectangle of the scene
        and scales the view along the X axis so that the content fits
        within the viewport width. Y scaling is left unchanged to
        maintain clip height. If the content is already narrower than
        the viewport, the transformation is reset.
        """
        # Determine scene and viewport dimensions
        scene_rect = self.sceneRect() if hasattr(self, "sceneRect") else None
        if not scene_rect:
            return
        view_width = self.viewport().width()
        content_width = scene_rect.width()
        if content_width <= 0 or view_width <= 0:
            return
        current_transform = self.transform()
        current_scale_x = current_transform.m11() if hasattr(current_transform, "m11") else 1.0
        # If content fits, reset any scaling to 1.0
        if content_width <= view_width:
            if abs(current_scale_x - 1.0) > 1e-3:
                self.resetTransform()
            return
        # Otherwise scale to fit width
        factor = view_width / content_width
        self.resetTransform()
        self.scale(factor, 1.0)