# file: ui/timeline/adapter.py
from __future__ import annotations

from typing import List, Optional, Tuple, Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QPen, QColor
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem


class TimelineAdapter:
    """
    Bridges Project <-> TimelineScene/View.

    Expected TimelineScene API (your implementation already provides these):
      - add_clip(path: str) -> QGraphicsItem
      - clear_all() -> None
      - select_by_path(path: str) -> None
      - (optional) find_item_by_path(path: str) -> QGraphicsItem

    TimelineView (optional):
      - fit_width_if_needed() -> None
    """

    def __init__(self, project: Any, timeline_scene: Any, timeline_view: Any | None = None) -> None:
        self.project = project
        self.scene: Any = timeline_scene
        self.view: Any | None = timeline_view
        # path → (main item, blue active overlay)
        self._item_map: dict[str, Tuple[QGraphicsItem, Optional[QGraphicsRectItem]]] = {}

    # ---------- add paths ----------

    def add_paths(self, paths: List[str]) -> List[str]:
        """Add to model and scene; return actually added (dedup + 10-cap)."""
        actually_added: List[str] = []
        for path in paths:
            if not self.project.add_clip(path):
                continue
            actually_added.append(path)

            # Main visual item for the clip
            item = self.scene.add_clip(path)

            # Create overlay *as a child of item* (never add to scene separately)
            overlay = QGraphicsRectItem(item)
            z = item.zValue() if hasattr(item, "zValue") else 0.0
            overlay.setZValue(float(z) + 0.5)
            overlay.setPen(QPen(Qt.PenStyle.NoPen))
            overlay.setBrush(QBrush(QColor(66, 133, 244, 160)))
            overlay.setVisible(False)

            self._item_map[path] = (item, overlay)

            # Initialize geometry if clip duration already known
            self.update_trim_for_path(path)

        # Optional view fit
        if actually_added and self.view and hasattr(self.view, "fit_width_if_needed"):
            try:
                self.view.fit_width_if_needed()
            except Exception:
                pass

        return actually_added

    # ---------- rebuild ----------

    def rebuild(self) -> None:
        """Rebuild entire scene from model order."""
        self.scene.clear_all()
        self._item_map.clear()
        for clip in self.project.track.clips:
            item = self.scene.add_clip(clip.path)

            overlay = QGraphicsRectItem(item)
            z = item.zValue() if hasattr(item, "zValue") else 0.0
            overlay.setZValue(float(z) + 0.5)
            overlay.setPen(QPen(Qt.PenStyle.NoPen))
            overlay.setBrush(QBrush(QColor(66, 133, 244, 160)))
            overlay.setVisible(False)

            self._item_map[clip.path] = (item, overlay)
            self.update_trim_for_path(clip.path)

        if self.view and hasattr(self.view, "fit_width_if_needed"):
            try:
                self.view.fit_width_if_needed()
            except Exception:
                pass

    # ---------- trims overlay ----------

    def update_trim_for_path(self, path: str) -> None:
        """Refresh the blue active region on a single clip."""
        pair = self._item_map.get(path)
        if not pair:
            # Fallback: try to locate an existing item in scene (optional API)
            item = self.scene.find_item_by_path(path) if hasattr(self.scene, "find_item_by_path") else None
            if not item:
                return
            overlay = QGraphicsRectItem(item)
            z = item.zValue() if hasattr(item, "zValue") else 0.0
            overlay.setZValue(float(z) + 0.5)
            overlay.setPen(QPen(Qt.PenStyle.NoPen))
            overlay.setBrush(QBrush(QColor(66, 133, 244, 160)))
            overlay.setVisible(False)
            self._item_map[path] = (item, overlay)
            pair = (item, overlay)

        item, overlay = pair
        clip = self.project.find_clip_by_path(path)
        if not clip or clip.duration_ms <= 0 or overlay is None:
            if overlay:
                overlay.setVisible(False)
            return

        r = self._item_rect(item)
        if r is None or r.width() <= 0.0 or r.height() <= 0.0:
            overlay.setVisible(False)
            return

        # Map trims to local pixels of the main item
        w = float(max(1.0, r.width()))
        dur = float(max(1, clip.duration_ms))
        left_px = float(r.left()) + w * (max(0, clip.in_ms) / dur)
        width_px = w * (max(0, clip.out_ms - clip.in_ms) / dur)

        if width_px <= 1.0:
            overlay.setVisible(False)
            return

        overlay.setRect(left_px, float(r.top()), width_px, float(r.height()))
        overlay.setVisible(True)

    def _item_rect(self, item: QGraphicsItem) -> Optional[QRectF]:
        """Return a stable local rect for the main item."""
        try:
            if hasattr(item, "rect"):
                r = item.rect()  # type: ignore[attr-defined]
                if isinstance(r, QRectF):
                    return r
            br = item.boundingRect()
            return br if isinstance(br, QRectF) else None
        except Exception:
            return None

    # ---------- order sync hooks ----------

    def on_order_changed(self) -> None:
        """Call after external reorders so overlays re-align."""
        for path in list(self._item_map.keys()):
            self.update_trim_for_path(path)

    # Optional: if your scene emits requestReorder(old_index, new_index)
    def on_request_reorder(self, old_index: int, new_index: int) -> None:
        try:
            self.project.move_clip(int(old_index), int(new_index))
            self.rebuild()
        except Exception:
            pass
