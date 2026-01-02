"""Pipeline configuration dataclass."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the processing pipeline.

    Attributes:
        speaker_switching_enabled: If False, output single-camera (no cuts).
        speaker_to_camera_map: Maps speaker_id -> camera_id. Used in pyannote mode.
            In ENERGY mode (V1 default), speaker_id == camera_id so mapping is implicit.
    """

    speaker_switching_enabled: bool = True
    speaker_to_camera_map: Dict[int, int] = field(default_factory=dict)

    @staticmethod
    def from_ui_mapping(
        camera_speaker_mapping: Dict[int, str],
        speaker_switching_enabled: bool = True,
    ) -> "PipelineConfig":
        """Create config from UI's camera-to-speaker mapping.

        UI format: {camera_idx: speaker_name} e.g. {0: "Speaker 1", 1: "Auto (best effort)"}
        Pipeline format: {speaker_id: camera_id} e.g. {0: 0, 1: 1}

        For "Auto (best effort)", we skip that mapping entry (default behavior).
        For "Speaker N", we extract N-1 (0-based) and map speaker N-1 -> camera.
        """
        speaker_to_camera: Dict[int, int] = {}

        if not camera_speaker_mapping:
            return PipelineConfig(
                speaker_switching_enabled=speaker_switching_enabled,
                speaker_to_camera_map=speaker_to_camera,
            )

        for camera_idx, speaker_name in camera_speaker_mapping.items():
            if not speaker_name or speaker_name.startswith("Auto"):
                # Skip auto-mapped entries - let the pipeline use defaults
                continue

            # Parse "Speaker N" format (UI uses 1-based numbering)
            try:
                if speaker_name.startswith("Speaker "):
                    # UI labels are 1-based: "Speaker 1" = speaker_id 0
                    speaker_num = int(speaker_name.replace("Speaker ", ""))
                    speaker_id = speaker_num - 1  # Convert to 0-based
                    speaker_to_camera[speaker_id] = camera_idx
                    logger.debug("Manual mapping: Speaker %d (id=%d) -> Camera %d", 
                               speaker_num, speaker_id, camera_idx)
                # Legacy format support
                elif speaker_name.startswith("speaker_"):
                    speaker_id = int(speaker_name.replace("speaker_", ""))
                    speaker_to_camera[speaker_id] = camera_idx
                    logger.debug("Mapping speaker_%d -> camera %d", speaker_id, camera_idx)
            except (ValueError, AttributeError):
                logger.warning("Invalid speaker name format: %s", speaker_name)
                continue

        if speaker_to_camera:
            logger.info("Manual speaker mapping configured: %s", speaker_to_camera)

        return PipelineConfig(
            speaker_switching_enabled=speaker_switching_enabled,
            speaker_to_camera_map=speaker_to_camera,
        )

    def has_manual_mapping(self) -> bool:
        """Return True if user has configured any manual speaker-to-camera mappings."""
        return bool(self.speaker_to_camera_map)


    def get_camera_for_speaker(self, speaker_id: int, num_cameras: int) -> int:
        """Get camera ID for a speaker.

        Falls back to speaker_id as camera_id (ENERGY mode default) if no mapping.
        Clamps to valid camera range.
        """
        camera_id = self.speaker_to_camera_map.get(speaker_id, speaker_id)
        # Clamp to valid range
        return max(0, min(camera_id, num_cameras - 1))
