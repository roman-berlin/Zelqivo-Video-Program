"""Pipeline configuration dataclass."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the processing pipeline.

    Attributes:
        speaker_switching_enabled: If False, output single-camera (no cuts).
        speaker_to_cameras_map: Maps speaker_id -> list of camera_ids.
            Multiple cameras can be assigned to the same speaker.
            When multiple cameras are assigned, energy detection picks the best one.
    """

    speaker_switching_enabled: bool = True
    speaker_to_cameras_map: Dict[int, List[int]] = field(default_factory=dict)

    @staticmethod
    def from_ui_mapping(
        camera_speaker_mapping: Dict[int, str],
        speaker_switching_enabled: bool = True,
    ) -> "PipelineConfig":
        """Create config from UI's camera-to-speaker mapping.

        UI format: {camera_idx: speaker_name} e.g. {0: "Speaker 1", 1: "Speaker 1", 2: "Speaker 2"}
        Pipeline format: {speaker_id: [camera_ids]} e.g. {0: [0, 1], 1: [2]}

        Multiple cameras can map to the same speaker - they form a "camera group".
        For "Auto (best effort)", we skip that mapping entry (default behavior).
        """
        speaker_to_cameras: Dict[int, List[int]] = {}

        if not camera_speaker_mapping:
            return PipelineConfig(
                speaker_switching_enabled=speaker_switching_enabled,
                speaker_to_cameras_map=speaker_to_cameras,
            )

        for camera_idx, speaker_name in camera_speaker_mapping.items():
            if not speaker_name or speaker_name.startswith("Auto"):
                # Skip auto-mapped entries - let the pipeline use defaults
                continue

            # Parse "Speaker N" format (UI uses 1-based numbering)
            try:
                speaker_id = None
                if speaker_name.startswith("Speaker "):
                    # UI labels are 1-based: "Speaker 1" = speaker_id 0
                    speaker_num = int(speaker_name.replace("Speaker ", ""))
                    speaker_id = speaker_num - 1  # Convert to 0-based
                # Legacy format support
                elif speaker_name.startswith("speaker_"):
                    speaker_id = int(speaker_name.replace("speaker_", ""))

                if speaker_id is not None:
                    if speaker_id not in speaker_to_cameras:
                        speaker_to_cameras[speaker_id] = []
                    speaker_to_cameras[speaker_id].append(camera_idx)
                    logger.debug("Manual mapping: Speaker %d -> Camera %d", 
                               speaker_id + 1, camera_idx)
            except (ValueError, AttributeError):
                logger.warning("Invalid speaker name format: %s", speaker_name)
                continue

        if speaker_to_cameras:
            logger.info("Speaker-camera groups: %s", 
                       {f"Speaker {k+1}": [f"Cam {c}" for c in v] 
                        for k, v in speaker_to_cameras.items()})

        return PipelineConfig(
            speaker_switching_enabled=speaker_switching_enabled,
            speaker_to_cameras_map=speaker_to_cameras,
        )

    def has_manual_mapping(self) -> bool:
        """Return True if user has configured any manual speaker-to-camera mappings."""
        return bool(self.speaker_to_cameras_map)

    def get_cameras_for_speaker(self, speaker_id: int) -> List[int]:
        """Get list of camera IDs assigned to a speaker.
        
        Returns empty list if speaker has no mapping (use energy detection for all cameras).
        """
        return self.speaker_to_cameras_map.get(speaker_id, [])

    def get_camera_for_speaker(self, speaker_id: int, num_cameras: int) -> int:
        """Get single camera ID for a speaker (first in group, or fallback).

        Falls back to speaker_id as camera_id (ENERGY mode default) if no mapping.
        Clamps to valid camera range.
        """
        cameras = self.get_cameras_for_speaker(speaker_id)
        if cameras:
            return cameras[0]  # Return first camera if multiple assigned
        # Fallback to speaker_id == camera_id
        return max(0, min(speaker_id, num_cameras - 1))
