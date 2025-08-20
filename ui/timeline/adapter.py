# file: ui/timeline/adapter.py
# NOTE: Removed `from __future__ import annotations` to avoid syntax error when code
# was pasted with extra lines above. Python 3.11+ handles postponed annotations by default.

from typing import List

from PyQt6.QtCore import QObject, pyqtSignal

from logic.project_state import Project
from ui.timeline.timeline import TimelineScene


class TimelineAdapter(QObject):
    """Bridge Project ↔ TimelineScene; keeps view in sync with model.

    Emits:
        pathsReordered(list[str]): new order when user reorders clips in the scene.
    """

    pathsReordered = pyqtSignal(list)

    def __init__(self, project: Project, scene: TimelineScene) -> None:
        super().__init__(scene)
        self.project = project
        self.scene = scene
        self.scene.orderChanged.connect(self.on_scene_order_changed)

    # --- API used by MainWindow ---
    def add_paths(self, paths: List[str]) -> List[str]:
        clips = self.project.add_clips(paths)
        if clips:
            self.sync_scene_from_model()
        return [c.path for c in clips]

    def on_scene_order_changed(self, ordered_paths: List[str]) -> None:
        self.project.reorder_by_paths(ordered_paths)
        self.pathsReordered.emit(ordered_paths)

    def sync_scene_from_model(self) -> None:
        self.scene.clear_clips()
        titles = [c.title for c in self.project.video.clips]
        paths = [c.path for c in self.project.video.clips]
        self.scene.add_clips(paths, titles, cap=self.project.max_videos)