# file: logic/project_state.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import uuid
import os


SCHEMA_VERSION = 1
MAX_VIDEOS = 10


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Clip:
    id: str
    path: str
    in_ms: int = 0
    out_ms: Optional[int] = None  # None = until end
    speed: float = 1.0
    mute: bool = False
    effects: dict = field(default_factory=dict)
    overlays: list = field(default_factory=list)

    @property
    def title(self) -> str:
        return os.path.basename(self.path)


@dataclass
class Track:
    id: str
    name: str
    clips: List[Clip] = field(default_factory=list)

    def index_by_path(self, path: str) -> int:
        for i, c in enumerate(self.clips):
            if c.path == path:
                return i
        return -1


@dataclass
class Project:
    id: str = field(default_factory=_new_id)
    version: int = SCHEMA_VERSION
    video: Track = field(default_factory=lambda: Track(id=_new_id(), name="V1"))
    max_videos: int = MAX_VIDEOS

    # --- Mutations ---
    def add_clips(self, paths: List[str]) -> List[Clip]:
        """Add clips by file path. Enforces max_videos and skips duplicates by path.
        Returns the list of newly created Clip objects (in order added).
        """
        added: List[Clip] = []
        remaining = max(0, self.max_videos - len(self.video.clips))
        if remaining <= 0:
            return added
        # Skip duplicates by path
        existing = {c.path for c in self.video.clips}
        for p in paths:
            if remaining <= 0:
                break
            if p in existing:
                continue
            clip = Clip(id=_new_id(), path=p)
            self.video.clips.append(clip)
            added.append(clip)
            remaining -= 1
        return added

    def reorder_by_paths(self, ordered_paths: List[str]) -> None:
        """Reorder video track clips to match ordered_paths (unknown paths ignored)."""
        by_path = {c.path: c for c in self.video.clips}
        new_order: List[Clip] = []
        for p in ordered_paths:
            c = by_path.get(p)
            if c is not None:
                new_order.append(c)
        # Append any clips not in list (should not happen normally)
        for c in self.video.clips:
            if c not in new_order:
                new_order.append(c)
        self.video.clips = new_order