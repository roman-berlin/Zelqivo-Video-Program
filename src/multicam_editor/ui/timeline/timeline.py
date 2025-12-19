# file: ui/timeline/timeline.py
from __future__ import annotations
from typing import List, Optional

from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt6.QtGui import QBrush, QPen, QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsRectItem, QGraphicsItem, QGraphicsLineItem, QToolTip


# ------------------------------- CutMarkerItem -----------------------------
class CutMarkerItem(QGraphicsLineItem):
    """Visual marker for cut plan boundaries with camera label."""

    def __init__(self, x_pos: float, start_ms: int, end_ms: int, camera_id: int, parent=None):
        super().__init__(x_pos, 0, x_pos, ClipItem.HEIGHT, parent)
        self.setAcceptHoverEvents(True)
        self.x_pos = x_pos
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.camera_id = camera_id
        self._hovered = False

        # Visual style
        pen = QPen(QColor(255, 180, 50), 2)
        self.setPen(pen)
        self.setZValue(10)  # Above clips

    def hoverEnterEvent(self, event):  # type: ignore[override]
        self._hovered = True
        # Make line thicker on hover
        pen = QPen(QColor(255, 200, 80), 3)
        self.setPen(pen)
        # Show tooltip
        timecode = self._format_timecode(self.start_ms)
        tooltip = f"Cut at {timecode}\nCamera: {self.camera_id}"
        QToolTip.showText(event.screenPos(), tooltip)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):  # type: ignore[override]
        self._hovered = False
        pen = QPen(QColor(255, 180, 50), 2)
        self.setPen(pen)
        QToolTip.hideText()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):  # type: ignore[override]
        # Emit signal to scene for seek
        scene = self.scene()
        if isinstance(scene, TimelineScene):
            scene.cutMarkerClicked.emit(self.start_ms)
        event.accept()

    @staticmethod
    def _format_timecode(ms: int) -> str:
        """Format milliseconds as MM:SS.mmm"""
        if ms <= 0:
            return "00:00.000"
        total_sec = ms / 1000
        m, s = divmod(int(total_sec), 60)
        millis = int((total_sec - int(total_sec)) * 1000)
        return f"{m:02d}:{int(s):02d}.{millis:03d}"

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[override]
        # Draw marker line
        super().paint(painter, option, widget)

        # Draw camera label
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)

        # Label background
        label_text = f"Cam {self.camera_id}"
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(label_text)
        text_height = fm.height()

        label_rect = QRectF(
            self.x_pos + 4,
            5,
            text_width + 8,
            text_height + 4
        )

        painter.setBrush(QBrush(QColor(255, 180, 50, 200)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(label_rect, 3, 3)

        # Label text
        painter.setPen(QColor(20, 20, 20))
        painter.drawText(
            int(label_rect.x() + 4),
            int(label_rect.y() + text_height),
            label_text
        )


# ------------------------------- ClipItem ----------------------------------
class ClipItem(QGraphicsRectItem):
    """Timeline clip item (single selection enforced by scene)."""

    HEIGHT = 100  # larger for readability

    def __init__(self, path: str, title: str, width: float, grid_px: int):
        super().__init__(0, 0, max(120.0, float(width)), float(self.HEIGHT))
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setAcceptHoverEvents(True)
        self.path = path  # unique key from adapter
        self._title = title
        self._grid_px = int(grid_px)

        # palette
        self._bg = QColor(52, 69, 99)
        self._bg_hover = QColor(60, 78, 112)
        self._bg_selected = QColor(70, 130, 180)
        self._border = QColor(190, 190, 190)
        self._text = QColor(245, 245, 245)
        self._font = QFont("Segoe UI", 11)

    def mousePressEvent(self, event):  # type: ignore[override]
        scn = self.scene()
        if isinstance(scn, TimelineScene):
            scn._record_last_clicked(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # type: ignore[override]
        """
        Treat double click like a single click so that selection and playback are triggered.

        In Qt, a double-click on a graphics item skips the normal mousePress/mouseRelease
        handlers and invokes mouseDoubleClickEvent directly. As a result, our
        mousePressEvent logic (which records the item and relies on the scene's
        selectionChanged signal) is bypassed.  To ensure that double-clicking a clip
        behaves the same as a single click (highlight the item and cause the file
        list/preview to change), we explicitly call mousePressEvent first.  After
        synthesising the single-click behaviour, we delegate to the base
        implementation so that any default double-click handling (if added in
        future) still applies.
        """
        # First, perform the same operations as a single click.
        # This will call our overridden mousePressEvent, which records the
        # last clicked item and forwards to the base implementation.
        self.mousePressEvent(event)
        # Then, call the base double-click handler to respect Qt's event flow.
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change, value):  # type: ignore[override]
        # Lock Y to 0 when position changes
        try:
            if int(change) == int(QGraphicsItem.GraphicsItemChange.ItemPositionChange) and isinstance(value, QPointF):
                return QPointF(max(0.0, float(value.x())), 0.0)
        except (TypeError, ValueError):
            pass
        return value

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        snapped_x = round(self.x() / self._grid_px) * self._grid_px
        self.setPos(max(0.0, float(snapped_x)), 0.0)
        super().mouseReleaseEvent(event)
        scn = self.scene()
        if isinstance(scn, TimelineScene):
            scn.on_item_released(self)

    def paint(self, painter: QPainter, option, widget=None):  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self._border))
        painter.setBrush(QBrush(self._bg_selected if self.isSelected() else (self._bg_hover if self.isUnderMouse() else self._bg)))
        painter.drawRoundedRect(self.rect(), 8, 8)

        painter.setPen(self._text)
        painter.setFont(self._font)
        pad = 10
        r = self.rect().adjusted(pad, 0, -pad, 0)
        fm = QFontMetrics(self._font)
        text = fm.elidedText(self._title, Qt.TextElideMode.ElideMiddle, int(max(30, r.width())))
        painter.drawText(r, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)


# ------------------------------ TimelineScene -------------------------------
class TimelineScene(QGraphicsScene):
    """Hosts ClipItems, enforces single selection, manages order/layout."""

    orderChanged = pyqtSignal(list)  # emits List[str] of keys in left→right order

    # Emitted when a clip is double-clicked.  Provides the unique key (path|in-out|index)
    # of the item so that callers can mirror selection and start playback.
    clipActivated = pyqtSignal(str)

    # Emitted when a cut marker is clicked. Provides timestamp in ms for seek.
    cutMarkerClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(0, 0, 12000, ClipItem.HEIGHT)
        self._grid_px = 80
        self._clips: List[ClipItem] = []
        self._cut_markers: List[CutMarkerItem] = []
        self._last_clicked: Optional[ClipItem] = None
        self._enforcing_selection: bool = False  # reentrancy guard
        self.selectionChanged.connect(self._enforce_single_selection)
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)  # safer for frequent insert/remove

    # background grid
    def drawBackground(self, painter: QPainter, rect: QRectF):  # type: ignore[override]
        painter.fillRect(rect, QColor(20, 20, 20))
        pen = QPen(QColor(55, 55, 55))
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        left = int(rect.left()) - (int(rect.left()) % self._grid_px)
        for x in range(left, int(rect.right()) + self._grid_px, self._grid_px):
            painter.drawLine(x, 0, x, ClipItem.HEIGHT)

    # single selection enforcement
    def _record_last_clicked(self, item: ClipItem) -> None:
        self._last_clicked = item

    def _enforce_single_selection(self) -> None:
        if self._enforcing_selection:
            return
        selected = [c for c in self._clips if c.isSelected()]
        if len(selected) <= 1:
            return
        self._enforcing_selection = True
        try:
            keep = self._last_clicked or selected[-1]
            for c in selected:
                c.setSelected(c is keep)
        finally:
            self._enforcing_selection = False

    def mousePressEvent(self, event):  # type: ignore[override]
        # click on empty space clears selection
        pos = event.scenePos()
        hit_items = self.items(pos)
        if not any(isinstance(i, ClipItem) for i in hit_items):
            for c in self._clips:
                c.setSelected(False)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # type: ignore[override]
        """Emit `clipActivated` when a clip item is double-clicked.

        When the user double-clicks on a clip, Qt does not guarantee that the
        selectionChanged signal fires again (it might already be selected). To
        ensure that double-clicking opens/plays the clip in the preview, we
        detect which item was clicked and emit `clipActivated` with its key.
        The main window can connect to this signal and forward the selection
        to the file list / preview.
        """
        # Determine which items are under the double-click position.
        try:
            pos = event.scenePos()
            for item in self.items(pos):
                if isinstance(item, ClipItem):
                    # Use the stored path (unique key) on the item
                    key = getattr(item, 'path', None)
                    if key:
                        self.clipActivated.emit(str(key))
                        break
        except Exception:
            pass
        # Call base implementation to maintain default behaviour
        super().mouseDoubleClickEvent(event)

    # mutation API
    def clear_all(self) -> None:
        # block selection signal re-entrancy while clearing
        blocked = self.blockSignals(True)
        try:
            while self._clips:
                c = self._clips.pop()
                try:
                    self.removeItem(c)
                except Exception:
                    pass
            self._clear_cut_markers()
        finally:
            self.blockSignals(blocked)

    def _clear_cut_markers(self) -> None:
        """Remove all cut markers from the scene."""
        while self._cut_markers:
            marker = self._cut_markers.pop()
            try:
                self.removeItem(marker)
            except Exception:
                pass

    def set_cut_plan(self, cut_segments: List) -> None:
        """Draw cut markers based on cut plan segments.

        Args:
            cut_segments: List of CutSegment objects with start_ms, end_ms, camera_id
        """
        # Clear existing markers
        self._clear_cut_markers()

        if not cut_segments:
            return

        # Simple visualization: place markers at proportional positions
        # Assume timeline width represents total duration
        # Get max time from cut segments
        max_time_ms = max(seg.end_ms for seg in cut_segments) if cut_segments else 0
        if max_time_ms <= 0:
            return

        # Use scene width for positioning
        scene_width = self.sceneRect().width()

        # Draw marker for each cut boundary (except first at 0)
        for seg in cut_segments:
            if seg.start_ms > 0:  # Skip marker at time 0
                # Calculate x position proportionally
                x_pos = (seg.start_ms / max_time_ms) * scene_width
                marker = CutMarkerItem(x_pos, seg.start_ms, seg.end_ms, seg.camera_id)
                self.addItem(marker)
                self._cut_markers.append(marker)

    def add_clip(self, path: str, title: Optional[str] = None):
        width = 420.0  # wider boxes
        title = title or path
        item = ClipItem(path, title, width, self._grid_px)
        x = sum(c.rect().width() for c in self._clips) + (len(self._clips) * 8)
        item.setPos(x, 0)
        self.addItem(item)
        self._clips.append(item)
        return item

    def find_item_by_path(self, path: str) -> Optional[ClipItem]:
        for c in self._clips:
            if c.path == path:
                return c
        return None

    def select_by_path(self, path: str) -> None:
        for c in self._clips:
            c.setSelected(c.path == path)

    def selected_paths(self) -> List[str]:
        return [c.path for c in self._clips if c.isSelected()]

    # layout & order
    def relayout_compact(self) -> None:
        x = 0.0
        for c in sorted(self._clips, key=lambda it: (it.x(), id(it))):
            c.setPos(x, 0)
            x += c.rect().width() + 8
        self._emit_order()

    def _emit_order(self) -> None:
        try:
            self.orderChanged.emit([c.path for c in sorted(self._clips, key=lambda it: (it.x(), id(it)))])
        except Exception:
            pass

    def on_item_released(self, item: ClipItem) -> None:
        if item not in self._clips:
            return
        self._clips.sort(key=lambda c: (c.x(), id(c)))
        self.relayout_compact()


# ------------------------------ TimelineView --------------------------------
class TimelineView(QGraphicsView):
    """View with default horizontal zoom and fit-to-width helper."""

    DEFAULT_ZOOM_X = 1.6  # larger by default

    def __init__(self, scene: TimelineScene, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("timelineView")
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._space_pressed = False

        # apply default horizontal zoom
        self._default_zoom_x = float(self.DEFAULT_ZOOM_X)
        self.resetTransform()
        self.scale(self._default_zoom_x, 1.0)

    def wheelEvent(self, event):  # type: ignore[override]
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.15 if angle > 0 else 1 / 1.15
            self.scale(factor, 1.0)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key.Key_Space and not self._space_pressed:
            self._space_pressed = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key.Key_Space and self._space_pressed:
            self._space_pressed = False
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def fit_width_if_needed(self) -> None:
        scene_rect = self.sceneRect()
        view_width = self.viewport().width()
        content_width = scene_rect.width()
        if content_width <= 0 or view_width <= 0:
            return

        current_scale_x = self.transform().m11()
        if content_width <= view_width:
            target = getattr(self, "_default_zoom_x", float(self.DEFAULT_ZOOM_X))
            if abs(current_scale_x - target) > 1e-3:
                self.resetTransform()
                self.scale(target, 1.0)
            return

        factor = view_width / content_width
        self.resetTransform()
        self.scale(factor, 1.0)
