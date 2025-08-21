# file: ui/timeline/adapter.py
from __future__ import annotations
from typing import Optional, Dict, List

from PyQt6.QtCore import QRectF, QCoreApplication, QThread

from core.project import Project, Clip
from ui.timeline.timeline import TimelineScene, TimelineView
from ui.utils.gui import gui_runner


class TimelineAdapter:
    """Thread-safe bridge Project ↔ TimelineScene/View (Prompt 4.4)."""

    def __init__(self, project: Project, scene: TimelineScene, view: TimelineView, file_list=None) -> None:
        self.project = project
        self.scene = scene
        self.view = view
        self.file_list = file_list
        self._key_to_index: Dict[str, int] = {}

    # ---------------- Thread-safe wrappers ----------------
    def refresh_from_project(self) -> None:
        gui_runner().post(self._refresh_from_project_impl)

    def select_and_scroll_by_key(self, key: str) -> None:
        gui_runner().post(lambda: self._select_and_scroll_by_key_impl(key))

    # ---------------------- Clips management ----------------------
    def add_paths(self, paths: list[str]) -> list[str]:
        """Add one or more source paths to the project and refresh the scene.

        Duplicates are ignored by the underlying project.  Returns a list
        of paths that were actually added.  The refresh is posted to
        the GUI thread so it is safe to call from any thread.
        """
        added: list[str] = []
        if not paths:
            return added
        for p in paths:
            try:
                clip = self.project.add_path(p)
            except Exception:
                clip = None
            if clip is not None:
                added.append(p)
        # Always schedule a refresh so the timeline reflects current
        # project state.  Using refresh_from_project posts to GUI thread.
        if added:
            self.refresh_from_project()
        return added

    def update_trim_for_path(self, path: str) -> None:
        """Update the timeline visuals for a trimmed clip.

        When a clip's in/out markers change in the project we refresh
        the scene to ensure the overlay data attached to items (like
        ``in_ms``/``out_ms``) stays in sync.  This method is safe to
        call from any thread.
        """
        # At present the timeline boxes have a fixed width and do not
        # visualise trim directly; we simply refresh the scene so that
        # the metadata stored on each item (source_path, in_ms, out_ms)
        # matches the project state.
        try:
            # Schedule a refresh via the GUI runner
            self.refresh_from_project()
        except Exception:
            pass

    def on_request_reorder(self, new_order: list[str]) -> None:
        """Reorder clips in the project according to the given list of keys.

        The ``TimelineScene`` may emit a requestReorder(new_order) signal
        with a list of item keys.  Each key contains the source path as
        the first component before the first '|'.  We compute the
        corresponding indices and rearrange the underlying project
        accordingly.  Finally a refresh is scheduled.
        """
        if not new_order:
            return
        # Extract source paths from keys; ignore unknown keys
        paths: list[str] = []
        for key in new_order:
            if not isinstance(key, str):
                continue
            parts = key.split("|", 1)
            if parts:
                paths.append(parts[0])
        # Build new clip list in the given order
        clips = self.project.clips()
        # Create mapping from path to list of clips (to handle multiple segments)
        by_path: dict[str, list[Clip]] = {}
        for c in clips:
            by_path.setdefault(c.path, []).append(c)
        new_clips: list[Clip] = []
        seen: set[Clip] = set()
        for p in paths:
            lst = by_path.get(p)
            if not lst:
                continue
            for c in lst:
                if c not in seen:
                    new_clips.append(c)
                    seen.add(c)
        # Append any remaining clips that were not specified
        for c in clips:
            if c not in seen:
                new_clips.append(c)
        # Apply new order
        try:
            self.project.set_clips(new_clips)
        except Exception:
            return
        # Refresh scene
        self.refresh_from_project()

    # ---------------- Impl (GUI thread only) --------------
    def _refresh_from_project_impl(self) -> None:
        clips: List[Clip] = self.project.clips()
        self.scene.clear_all()
        self._key_to_index.clear()

        for i, clip in enumerate(clips):
            key = self._make_key(clip, i)
            title = clip.display_title()
            item = self.scene.add_clip(path=key, title=title)
            try:
                setattr(item, "source_path", clip.path)
                setattr(item, "in_ms", clip.in_ms)
                setattr(item, "out_ms", clip.out_ms)
            except Exception:
                pass
            self._key_to_index[key] = i

        self.scene.relayout_compact()

        if self.file_list is not None:
            try:
                self.file_list.clear()
                for clip in clips:
                    self.file_list.addItem(clip.display_title())
            except Exception:
                pass

    def _select_and_scroll_by_key_impl(self, key: str) -> None:
        try:
            self.scene.select_by_path(key)
        except Exception:
            pass
        finder = getattr(self.scene, "find_item_by_path", None)
        item = finder(key) if callable(finder) else None
        if item is None:
            try:
                for it in self.scene.items():
                    if getattr(it, "path", None) == key:
                        it.setSelected(True)
                        item = it
                        break
            except Exception:
                item = None
        if item is not None and hasattr(item, "mapToScene"):
            rect = item.mapToScene(item.boundingRect()).boundingRect().adjusted(-40, -20, 40, 20)
            self.view.ensureVisible(QRectF(rect))

    # ---------------- Split orchestration -----------------
    def split_selected_at(self, playhead_ms: int) -> Optional[Clip]:
        key = self.selected_key()
        if not key:
            return None
        src_path = key.split("|")[0]
        result = self.project.split_clip_by_path(src_path, playhead_ms)
        if not result:
            return None
        left, _right = result
        # refresh + reselect on GUI thread
        self.refresh_from_project()
        clips = self.project.clips()
        left_index = next((i for i, c in enumerate(clips)
                           if c.path == left.path and c.in_ms == left.in_ms and c.out_ms == left.out_ms), 0)
        left_key = self._make_key(left, left_index)
        self.select_and_scroll_by_key(left_key)
        return left

    # ---------------- Selection query (safe) --------------
    def selected_key(self) -> Optional[str]:
        # reading selection should happen on GUI thread; tolerate call anyway
        app = QCoreApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            # best effort: no cross-thread calls into scene to avoid crash
            return None
        try:
            paths = self.scene.selected_paths()
            if paths:
                return str(paths[0])
        except Exception:
            pass
        try:
            items = self.scene.selectedItems()
        except Exception:
            items = []
        if items:
            key = getattr(items[0], "path", None)
            if key:
                return str(key)
        return None

    # ---------------- Utils -------------------------------
    @staticmethod
    def _make_key(clip: Clip, index: int) -> str:
        right = "" if clip.out_ms is None else str(clip.out_ms)
        return f"{clip.path}|{clip.in_ms}-{right}|{index}"
