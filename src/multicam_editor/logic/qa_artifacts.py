"""QA artifacts export for validating speaker switching decisions.

Writes diarization.json, cut_plan.json, and processing_summary.json to a run folder.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from PyQt6.QtCore import QStandardPaths

from .active_speaker import SpeakerSegment

logger = logging.getLogger(__name__)


@dataclass
class CutPlanEntry:
    """Extended cut entry with QA metadata."""
    start_ms: int
    end_ms: int
    chosen_camera_index: int
    speaker_id: int
    reason: str  # "threshold", "forced", "default"


def get_runs_base_dir() -> Path:
    """Return the base directory for QA run folders.

    Uses AppData/Local on Windows, ~/.local/share on Linux.
    Works in EXE builds.
    """
    app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if not app_data:
        app_data = os.path.expanduser("~")
    base = Path(app_data) / "MultiCamEditor" / "qa_runs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def create_run_folder() -> Path:
    """Create a timestamped run folder and return its path."""
    base = get_runs_base_dir()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_folder = base / f"run_{timestamp}"
    run_folder.mkdir(parents=True, exist_ok=True)
    logger.info("QA run folder: %s", run_folder.name)
    return run_folder


def get_last_run_folder() -> Optional[Path]:
    """Return the most recent run folder, or None if none exist."""
    base = get_runs_base_dir()
    if not base.exists():
        return None
    folders = sorted(base.glob("run_*"), reverse=True)
    return folders[0] if folders else None


def _sanitize_path(path: str) -> str:
    """Return only the filename to avoid PII in logs/exports."""
    return os.path.basename(path)


def export_diarization(
    run_folder: Path,
    segments: List[SpeakerSegment],
) -> None:
    """Export diarization.json with speakers and segments."""
    speaker_ids = sorted(set(s.speaker_id for s in segments))
    data = {
        "speakers": [{"id": sid, "label": f"speaker_{sid}"} for sid in speaker_ids],
        "segments": [
            {"start_ms": s.start_ms, "end_ms": s.end_ms, "speaker_id": s.speaker_id}
            for s in segments
        ],
    }
    out_path = run_folder / "diarization.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.debug("Wrote diarization.json (%d segments)", len(segments))


def export_cut_plan(
    run_folder: Path,
    cuts: List[CutPlanEntry],
) -> None:
    """Export cut_plan.json with ordered cuts and reasons."""
    data = {
        "cuts": [
            {
                "start_ms": c.start_ms,
                "end_ms": c.end_ms,
                "chosen_camera_index": c.chosen_camera_index,
                "speaker_id": c.speaker_id,
                "reason": c.reason,
            }
            for c in cuts
        ]
    }
    out_path = run_folder / "cut_plan.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.debug("Wrote cut_plan.json (%d cuts)", len(cuts))

    # Log each cut for easy debugging
    for i, c in enumerate(cuts):
        logger.info(
            "CUT %d: %d-%d speaker_%d->cam%d reason=%s",
            i, c.start_ms, c.end_ms, c.speaker_id, c.chosen_camera_index, c.reason
        )


def export_processing_summary(
    run_folder: Path,
    num_speakers: int,
    num_segments: int,
    num_cuts: int,
    total_duration_ms: int,
    thresholds: dict[str, int],
    sync_info: Optional[dict[str, Any]] = None,
) -> None:
    """Export processing_summary.json with counts and settings."""
    data = {
        "counts": {
            "num_speakers": num_speakers,
            "num_segments": num_segments,
            "num_cuts": num_cuts,
            "total_duration_ms": total_duration_ms,
        },
        "thresholds": thresholds,
        "external_audio_sync": sync_info or {"used": False},
    }
    out_path = run_folder / "processing_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.debug("Wrote processing_summary.json")


class QAArtifactExporter:
    """Collects and exports all QA artifacts for a single processing run."""

    def __init__(self) -> None:
        self.run_folder: Optional[Path] = None
        self._segments: List[SpeakerSegment] = []
        self._cuts: List[CutPlanEntry] = []
        self._thresholds: dict[str, int] = {}
        self._total_duration_ms: int = 0
        self._sync_info: Optional[dict[str, Any]] = None

    def start_run(self) -> Path:
        """Create a new run folder and return its path."""
        self.run_folder = create_run_folder()
        return self.run_folder

    def set_diarization(self, segments: List[SpeakerSegment]) -> None:
        """Store diarization segments for export."""
        self._segments = list(segments)

    def set_thresholds(
        self,
        min_switch_interval_ms: int,
        min_speech_ms: int,
        bg_short_remark_ms: int,
    ) -> None:
        """Store decision engine thresholds."""
        self._thresholds = {
            "min_switch_interval_ms": min_switch_interval_ms,
            "min_speech_ms": min_speech_ms,
            "bg_short_remark_ms": bg_short_remark_ms,
        }

    def set_total_duration(self, duration_ms: int) -> None:
        """Store total video duration."""
        self._total_duration_ms = duration_ms

    def add_cut(
        self,
        start_ms: int,
        end_ms: int,
        camera_index: int,
        speaker_id: int,
        reason: str,
    ) -> None:
        """Add a cut entry with reason."""
        self._cuts.append(CutPlanEntry(
            start_ms=start_ms,
            end_ms=end_ms,
            chosen_camera_index=camera_index,
            speaker_id=speaker_id,
            reason=reason,
        ))

    def set_sync_info(
        self,
        offset_ms: float,
        success: bool,
        message: str = "",
    ) -> None:
        """Store external audio sync info."""
        self._sync_info = {
            "used": True,
            "offset_ms": offset_ms,
            "success": success,
            "message": message,
        }

    def finalize(self) -> None:
        """Write all artifacts to the run folder."""
        if not self.run_folder:
            logger.warning("QA export skipped: no run folder")
            return

        try:
            export_diarization(self.run_folder, self._segments)
            export_cut_plan(self.run_folder, self._cuts)

            num_speakers = len(set(s.speaker_id for s in self._segments))
            export_processing_summary(
                self.run_folder,
                num_speakers=num_speakers,
                num_segments=len(self._segments),
                num_cuts=len(self._cuts),
                total_duration_ms=self._total_duration_ms,
                thresholds=self._thresholds,
                sync_info=self._sync_info,
            )
            logger.info("QA artifacts written to: %s", self.run_folder.name)
        except Exception as e:
            logger.error("Failed to write QA artifacts: %s", e, exc_info=True)
