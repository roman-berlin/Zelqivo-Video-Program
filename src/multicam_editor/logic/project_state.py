# file: logic/project_state.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


MAX_VIDEOS = 10  # hard rule; UI also enforces 10-cap


@dataclass
class Clip:
    path: str
    duration_ms: int = 0
    in_ms: int = 0        # inclusive
    out_ms: int = 0       # exclusive; 0 → unset until duration known


@dataclass
class Track:
    clips: List[Clip] = field(default_factory=list)


class Project:
    """In-memory project state (single track)."""

    def __init__(self) -> None:
        self.track = Track()

    # ---- add/remove/reorder ----
    def add_clip(self, path: str) -> bool:
        if not path:
            return False
        if any(c.path == path for c in self.track.clips):
            return False
        if len(self.track.clips) >= MAX_VIDEOS:
            return False
        self.track.clips.append(Clip(path=path))
        return True

    def remove_clip_by_path(self, path: str) -> bool:
        for i, c in enumerate(self.track.clips):
            if c.path == path:
                del self.track.clips[i]
                return True
        return False

    def move_clip(self, old_index: int, new_index: int) -> None:
        if not (0 <= old_index < len(self.track.clips)):
            return
        new_index = max(0, min(new_index, len(self.track.clips) - 1))
        if old_index == new_index:
            return
        clip = self.track.clips.pop(old_index)
        self.track.clips.insert(new_index, clip)

    # ---- lookup ----
    def find_clip_by_path(self, path: str) -> Optional[Clip]:
        for c in self.track.clips:
            if c.path == path:
                return c
        return None

    def index_of_path(self, path: str) -> int:
        for i, c in enumerate(self.track.clips):
            if c.path == path:
                return i
        return -1

    # ---- trims / duration ----
    def get_trim_by_path(self, path: str) -> Tuple[int, int]:
        """Return (in_ms, out_ms). If out unset, use duration."""
        c = self.find_clip_by_path(path)
        if not c:
            return 0, 0
        out = c.out_ms if c.out_ms > 0 else c.duration_ms
        return int(c.in_ms), int(out)

    def set_duration_by_path(self, path: str, duration_ms: int) -> None:
        c = self.find_clip_by_path(path)
        if not c:
            return
        c.duration_ms = max(0, int(duration_ms))
        if c.out_ms == 0 and c.duration_ms > 0:
            c.out_ms = c.duration_ms

    def set_trim_by_path(self, path: str, in_ms: int, out_ms: int) -> None:
        c = self.find_clip_by_path(path)
        if not c:
            return
        dur = max(0, int(c.duration_ms))
        left = max(0, min(int(in_ms), dur))
        right = max(left, min(int(out_ms), dur))
        c.in_ms, c.out_ms = left, right
