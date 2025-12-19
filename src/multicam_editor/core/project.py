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

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
import os
import uuid
import json


class AudioMixMode(Enum):
    """Audio mixing mode for external audio."""
    REPLACE = "replace"  # Only external audio audible
    MIX = "mix"  # Both video and external audio mixed


@dataclass
class AudioMixSettings:
    """Settings for audio mixing with external audio track.

    Attributes:
        mode: REPLACE (only external) or MIX (both)
        video_gain_db: Gain for video's original audio (-60 to +12 dB)
        external_gain_db: Gain for external audio (-60 to +12 dB)
        ducking_enabled: Whether to duck video audio when external is loud
        ducking_amount_db: How much to reduce video audio during ducking
    """
    mode: AudioMixMode = AudioMixMode.REPLACE
    video_gain_db: float = 0.0
    external_gain_db: float = 0.0
    ducking_enabled: bool = False
    ducking_amount_db: float = -12.0

    def clamp_gains(self) -> "AudioMixSettings":
        """Return a copy with gains clamped to valid range [-60, +12]."""
        return AudioMixSettings(
            mode=self.mode,
            video_gain_db=max(-60.0, min(12.0, self.video_gain_db)),
            external_gain_db=max(-60.0, min(12.0, self.external_gain_db)),
            ducking_enabled=self.ducking_enabled,
            ducking_amount_db=max(-60.0, min(0.0, self.ducking_amount_db)),
        )


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

    Effects (Prompt 8.1):
        fade_in_ms: Duration of fade-in effect (0 = disabled)
        fade_out_ms: Duration of fade-out effect (0 = disabled)
        grayscale: If True, apply grayscale filter
        speed: Playback speed multiplier (1.0 = normal, 0.5 = half speed, 2.0 = double)
    """

    id: str
    path: str
    in_ms: int = 0
    out_ms: Optional[int] = None  # None → until end
    duration_ms: int = 0
    # Effects (Prompt 8.1)
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    grayscale: bool = False
    speed: float = 1.0

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
    SCHEMA_VERSION: int = 1

    def __init__(self) -> None:
        self._clips: List[Clip] = []

    # accessors
    def clips(self) -> List[Clip]:
        return list(self._clips)

    def set_clips(self, clips: List[Clip]) -> None:
        self._clips = list(clips)

    def add_path(self, path: str) -> Clip | None:
        """Add a new clip for *path* if it does not already exist.

        The UI layer (``FileListWidget``) already guards against adding
        duplicate video files, but callers may bypass that check (for example,
        via unit tests or future API calls). Adding the same path twice would
        lead to multiple ``Clip`` objects representing the same source,
        causing ambiguous behaviour when splitting or reordering. To keep the
        project state predictable we refuse to add a second clip with an
        identical ``path`` and instead return ``None``.

        Returns the newly created ``Clip`` on success, or ``None`` if the clip
        already exists.
        """
        normalized = str(path)
        for existing in self._clips:
            if existing.path == normalized:
                return None
        clip = Clip(id=str(uuid.uuid4()), path=normalized)
        self._clips.append(clip)
        return clip

    # ------------------------------------------------------------------
    # duration / trim helpers
    def _find_first_by_path(self, path: str) -> Optional[Clip]:
        """Return the first clip with the given source path or ``None``.

        TODO: WARNING - path is not a stable identity after split operations.
        Multiple clips can share the same source path after splitting. This
        method returns the FIRST match, which may not be the intended clip.
        Consider using clip ID for lookups in future refactoring.
        """
        for c in self._clips:
            if c.path == path:
                return c
        return None

    def get_trim_by_path(self, path: str) -> Tuple[int, int]:
        """Return a (in_ms, out_ms) tuple for the first clip with ``path``.

        If ``out_ms`` is ``None`` or zero the clip's ``duration_ms`` is used.
        If no clip exists the tuple (0, 0) is returned.

        TODO: Path-based lookup - returns FIRST clip match. After splits,
        multiple clips share the same path. Consider clip ID-based API.
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

        TODO: Path-based lookup - affects FIRST clip match only. After splits,
        multiple clips share the same path. Consider clip ID-based API.
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

        TODO: Path-based lookup - modifies FIRST clip match only. After splits,
        multiple clips share the same path. Consider clip ID-based API.
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

        left = Clip(id=str(uuid.uuid4()), path=src.path, in_ms=start, out_ms=t, duration_ms=src.duration_ms)
        right = Clip(id=str(uuid.uuid4()), path=src.path, in_ms=t, out_ms=raw_end, duration_ms=src.duration_ms)
        self._clips[idx:idx + 1] = [left, right]
        return left, right

    # save/load (Prompt 9.1)
    def save_to_json(self, filepath: str) -> None:
        """Save project to JSON with relative paths (schema v1)."""
        project_dir = os.path.dirname(os.path.abspath(filepath))

        clips_data = []
        for clip in self._clips:
            # Convert absolute path to relative
            abs_clip_path = os.path.abspath(clip.path)
            try:
                rel_path = os.path.relpath(abs_clip_path, project_dir)
            except ValueError:
                # Different drives on Windows - keep absolute
                rel_path = abs_clip_path

            clips_data.append({
                "id": clip.id,
                "path": rel_path,
                "in_ms": clip.in_ms,
                "out_ms": clip.out_ms,
                "duration_ms": clip.duration_ms,
                "fade_in_ms": clip.fade_in_ms,
                "fade_out_ms": clip.fade_out_ms,
                "grayscale": clip.grayscale,
                "speed": clip.speed,
            })

        data = {
            "schema_version": self.SCHEMA_VERSION,
            "clips": clips_data,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load_from_json(filepath: str) -> "Project":
        """Load project from JSON, restoring state 1:1."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("schema_version") != Project.SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version: {data.get('schema_version')}")

        project = Project()
        project_dir = os.path.dirname(os.path.abspath(filepath))

        clips = []
        for clip_data in data.get("clips", []):
            # Convert relative path back to absolute
            rel_path = clip_data["path"]
            if os.path.isabs(rel_path):
                abs_path = rel_path
            else:
                abs_path = os.path.normpath(os.path.join(project_dir, rel_path))

            clip = Clip(
                id=clip_data["id"],
                path=abs_path,
                in_ms=clip_data.get("in_ms", 0),
                out_ms=clip_data.get("out_ms"),
                duration_ms=clip_data.get("duration_ms", 0),
                fade_in_ms=clip_data.get("fade_in_ms", 0),
                fade_out_ms=clip_data.get("fade_out_ms", 0),
                grayscale=clip_data.get("grayscale", False),
                speed=clip_data.get("speed", 1.0),
            )
            clips.append(clip)

        project._clips = clips
        return project
