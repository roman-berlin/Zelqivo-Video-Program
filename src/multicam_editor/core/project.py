"""
Patched core.project module with guardrails for splitting (Prompt 4.5).

This version mirrors the DEV branch's core/project.py but adds a minimum
segment length constraint when splitting clips. Splits that would result
in a segment shorter than `MIN_SEGMENT_MS` are prevented and return
``None`` instead of performing the split.  Disallowing very small
segments helps ensure that splits adhere to the guardrails described in
stage 4.5.

All other functionality matches the DEV branch.  To use this class in
your project, replace the original `core/project.py` with this file's
contents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
import os
import uuid


@dataclass
class Clip:
    """Non‑destructive segment of a source file.

    A ``Clip`` represents a continuous segment from a media file.  The
    ``in_ms`` and ``out_ms`` fields define the start and end of the
    segment (in milliseconds).  When ``out_ms`` is ``None`` the clip
    continues to the end of the source.  The ``duration_ms`` field is
    used by the UI to display the full length of the source.  It is
    optional and does not affect splitting – the actual clip length is
    governed by ``in_ms``/``out_ms``.
    """

    id: str
    path: str
    in_ms: int = 0
    out_ms: Optional[int] = None  # None → until end
    duration_ms: int = 0

    def display_title(self) -> str:
        """Return a human‑readable title for display in the timeline/list."""
        base = os.path.basename(self.path) or self.path
        # Represent the right edge of the clip; None means open‑ended
        right = "…" if self.out_ms is None else str(self.out_ms)
        return f"{base} [{self.in_ms}–{right} ms]"


class Project:
    """Ordered collection of clips with split-by-path support (Prompt 4.4/4.5)."""

    # Minimum duration for each segment after a split (ms)
    MIN_SEGMENT_MS: int = 100

    def __init__(self) -> None:
        self._clips: List[Clip] = []

    # accessors
    def clips(self) -> List[Clip]:
        return list(self._clips)

    def set_clips(self, clips: List[Clip]) -> None:
        self._clips = list(clips)

    def add_path(self, path: str) -> Clip:
        clip = Clip(id=str(uuid.uuid4()), path=path)
        self._clips.append(clip)
        return clip

    # ------------------------------------------------------------------
    # duration / trim helpers
    def _find_first_by_path(self, path: str) -> Optional[Clip]:
        """Return the first clip with the given source path or ``None``."""
        for c in self._clips:
            if c.path == path:
                return c
        return None

    def get_trim_by_path(self, path: str) -> Tuple[int, int]:
        """Return a (in_ms, out_ms) tuple for the first clip with ``path``.

        If ``out_ms`` is ``None`` or zero the clip's ``duration_ms`` is used.
        If no clip exists the tuple (0, 0) is returned.
        """
        clip = self._find_first_by_path(path)
        if clip is None:
            return 0, 0
        start = int(clip.in_ms)
        # Use recorded end or fall back to duration
        if clip.out_ms is not None and clip.out_ms > 0:
            end = int(clip.out_ms)
        else:
            end = int(clip.duration_ms)
        end = max(start, end)
        return start, end

    def set_duration_by_path(self, path: str, duration_ms: int) -> None:
        """Set the recorded duration of the first clip with ``path``.

        When ``out_ms`` is unset (``None`` or zero) and the duration becomes
        known, ``out_ms`` is initialised to ``duration_ms`` so that
        trimming operations have a sensible default.
        """
        clip = self._find_first_by_path(path)
        if clip is None:
            return
        d = max(0, int(duration_ms))
        clip.duration_ms = d
        if (clip.out_ms is None or clip.out_ms == 0) and d > 0:
            clip.out_ms = d

    def set_trim_by_path(self, path: str, in_ms: int, out_ms: int) -> None:
        """Adjust the in/out markers for the first clip with ``path``.

        The values are clamped into the range [0, duration_ms].  If no
        duration is recorded the values are clamped assuming 0→∞.
        """
        clip = self._find_first_by_path(path)
        if clip is None:
            return
        dur = clip.duration_ms if clip.duration_ms > 0 else None
        left = max(0, int(in_ms))
        if dur is not None:
            left = min(left, dur)
        right = max(left, int(out_ms))
        if dur is not None:
            right = min(right, dur)
        clip.in_ms = left
        clip.out_ms = right

    # split
    def split_clip_by_path(self, path: str, playhead_ms: int) -> Optional[Tuple[Clip, Clip]]:
        """Split the first clip with *path* at *playhead_ms*.

        The playhead is interpreted as an absolute offset from the start
        of the source file.  If the playhead lies outside the clip's
        current trim range (``in_ms`` .. ``out_ms``) the split is aborted.
        When either resulting segment would be shorter than
        ``MIN_SEGMENT_MS`` the split is also aborted and ``None`` is
        returned.  A ``None`` return indicates that no split was
        performed.

        To support open‑ended clips, a recorded ``out_ms`` of ``None`` or
        ``0`` is treated as unbounded (``end=None``).  In that case the
        right‑side minimum length check is skipped because the segment
        extends to the end of the source.  Returns a tuple ``(left,
        right)`` on success.
        """
        idx: Optional[int] = None
        for i, c in enumerate(self._clips):
            if c.path == path:
                idx = i
                break
        if idx is None:
            return None

        src = self._clips[idx]
        t = max(0, int(playhead_ms))
        start = max(0, int(src.in_ms))
        # Interpret an out_ms of 0 or None as open ended (None)
        raw_end = src.out_ms
        end: Optional[int] = None
        if raw_end is not None and raw_end > 0:
            end = int(raw_end)

        # Prevent splits at or outside the boundaries
        if t <= start:
            return None
        if end is not None and t >= end:
            return None

        # Enforce minimum segment length: ensure both sides of the split
        # will be at least MIN_SEGMENT_MS long relative to the trimmed range.
        if t - start < self.MIN_SEGMENT_MS:
            return None
        if end is not None and (end - t) < self.MIN_SEGMENT_MS:
            return None

        left = Clip(id=str(uuid.uuid4()), path=src.path, in_ms=start, out_ms=t)
        right = Clip(id=str(uuid.uuid4()), path=src.path, in_ms=t, out_ms=raw_end)
        self._clips[idx:idx + 1] = [left, right]
        return left, right