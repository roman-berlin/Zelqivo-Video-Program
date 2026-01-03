"""Tests for PipelineConfig and UI settings wiring."""

import pytest

from multicam_editor.logic.pipeline_config import PipelineConfig
from multicam_editor.logic.active_speaker import SpeakerSegment
from multicam_editor.logic.decision_engine import DecisionEngine, CutSegment


class TestPipelineConfigFromUIMapping:
    """Test conversion of UI camera-to-speaker mapping to pipeline format."""

    def test_empty_mapping(self) -> None:
        """Empty mapping returns empty dict."""
        config = PipelineConfig.from_ui_mapping({})
        assert config.speaker_to_cameras_map == {}
        assert config.speaker_switching_enabled is True

    def test_all_auto_mapping(self) -> None:
        """All 'Auto' entries are skipped."""
        ui_mapping = {
            0: "Auto (best effort)",
            1: "Auto (best effort)",
        }
        config = PipelineConfig.from_ui_mapping(ui_mapping)
        assert config.speaker_to_cameras_map == {}

    def test_speaker_to_camera_conversion(self) -> None:
        """UI format {camera: speaker_X} converts to {X: [camera]}."""
        ui_mapping = {
            0: "speaker_0",
            1: "speaker_1",
        }
        config = PipelineConfig.from_ui_mapping(ui_mapping)
        # speaker_0 -> [camera 0], speaker_1 -> [camera 1]
        assert config.speaker_to_cameras_map == {0: [0], 1: [1]}

    def test_swapped_mapping(self) -> None:
        """Swapped mapping: camera 0 has speaker_1, camera 1 has speaker_0."""
        ui_mapping = {
            0: "speaker_1",  # Camera 0 shows speaker_1
            1: "speaker_0",  # Camera 1 shows speaker_0
        }
        config = PipelineConfig.from_ui_mapping(ui_mapping)
        # speaker_0 -> [camera 1], speaker_1 -> [camera 0]
        assert config.speaker_to_cameras_map == {1: [0], 0: [1]}

    def test_partial_auto_mapping(self) -> None:
        """Mix of auto and explicit mapping."""
        ui_mapping = {
            0: "speaker_0",
            1: "Auto (best effort)",
            2: "speaker_2",
        }
        config = PipelineConfig.from_ui_mapping(ui_mapping)
        # Only explicit mappings
        assert config.speaker_to_cameras_map == {0: [0], 2: [2]}

    def test_invalid_speaker_format_ignored(self) -> None:
        """Invalid formats are silently ignored."""
        ui_mapping = {
            0: "invalid_format",
            1: "speaker_1",
            2: "",
            3: "speaker_abc",  # Non-numeric
        }
        config = PipelineConfig.from_ui_mapping(ui_mapping)
        # Only valid speaker_1 mapped
        assert config.speaker_to_cameras_map == {1: [1]}

    def test_speaker_switching_disabled(self) -> None:
        """Speaker switching flag is preserved."""
        config = PipelineConfig.from_ui_mapping(
            {0: "speaker_0"},
            speaker_switching_enabled=False,
        )
        assert config.speaker_switching_enabled is False
        assert config.speaker_to_cameras_map == {0: [0]}

    def test_multiple_cameras_same_speaker(self) -> None:
        """Multiple cameras can be assigned to the same speaker."""
        ui_mapping = {
            0: "Speaker 1",
            1: "Speaker 2",
            2: "Speaker 1",  # Camera 2 also assigned to Speaker 1
            3: "Speaker 2",
        }
        config = PipelineConfig.from_ui_mapping(ui_mapping)
        # Speaker 1 (id=0) -> [Camera 0, Camera 2]
        # Speaker 2 (id=1) -> [Camera 1, Camera 3]
        assert config.speaker_to_cameras_map == {0: [0, 2], 1: [1, 3]}


class TestPipelineConfigGetCamera:
    """Test camera lookup with mapping and fallback."""

    def test_direct_mapping(self) -> None:
        """Direct mapping lookup works - returns first camera in group."""
        config = PipelineConfig(speaker_to_cameras_map={0: [1], 1: [0]})
        assert config.get_camera_for_speaker(0, num_cameras=2) == 1
        assert config.get_camera_for_speaker(1, num_cameras=2) == 0

    def test_fallback_to_speaker_id(self) -> None:
        """Missing mapping falls back to speaker_id as camera_id."""
        config = PipelineConfig(speaker_to_cameras_map={})
        # No mapping -> speaker_id == camera_id (ENERGY mode default)
        assert config.get_camera_for_speaker(0, num_cameras=3) == 0
        assert config.get_camera_for_speaker(1, num_cameras=3) == 1
        assert config.get_camera_for_speaker(2, num_cameras=3) == 2

    def test_clamp_to_valid_range(self) -> None:
        """Camera ID clamped to valid range."""
        config = PipelineConfig(speaker_to_cameras_map={})
        # Speaker 10 has no mapping, fallback to 10, clamped to max
        assert config.get_camera_for_speaker(10, num_cameras=2) == 1

    def test_fallback_clamp(self) -> None:
        """Fallback speaker_id also clamped."""
        config = PipelineConfig(speaker_to_cameras_map={})
        # Speaker 5 has no mapping, fallback to 5, but only 2 cameras
        assert config.get_camera_for_speaker(5, num_cameras=2) == 1

    def test_get_cameras_for_speaker(self) -> None:
        """get_cameras_for_speaker returns list of cameras."""
        config = PipelineConfig(speaker_to_cameras_map={0: [0, 2], 1: [1, 3]})
        assert config.get_cameras_for_speaker(0) == [0, 2]
        assert config.get_cameras_for_speaker(1) == [1, 3]
        assert config.get_cameras_for_speaker(5) == []  # Not mapped


class TestSpeakerSwitchingDisabled:
    """Test that speaker_switching_enabled=False produces single-camera output."""

    def test_single_camera_cut_plan(self) -> None:
        """With switching disabled, decision engine gets empty segments -> single cut."""
        # Simulate: switching disabled means diarization returns []
        engine = DecisionEngine(default_camera=0)

        # Empty segments = single camera for full duration
        cut_plan = engine.generate_cut_plan([], total_duration_ms=10000)

        assert len(cut_plan) == 1
        assert cut_plan[0] == CutSegment(0, 10000, 0)

    def test_config_preserves_disabled_flag(self) -> None:
        """Config correctly stores disabled flag."""
        config = PipelineConfig(speaker_switching_enabled=False)
        assert config.speaker_switching_enabled is False


class TestMappingIntegration:
    """Integration tests: mapping affects cut plan camera selection."""

    def test_swapped_mapping_affects_cuts(self) -> None:
        """With swapped mapping, speakers select opposite cameras."""
        config = PipelineConfig.from_ui_mapping({
            0: "speaker_1",  # Camera 0 captures speaker_1
            1: "speaker_0",  # Camera 1 captures speaker_0
        })

        # When speaker_0 talks, they should be on camera 1
        assert config.get_camera_for_speaker(0, num_cameras=2) == 1
        # When speaker_1 talks, they should be on camera 0
        assert config.get_camera_for_speaker(1, num_cameras=2) == 0

    def test_missing_speaker_safe_fallback(self) -> None:
        """Speaker not in mapping uses safe fallback."""
        config = PipelineConfig.from_ui_mapping({
            0: "speaker_0",
            # speaker_1 not mapped
        })

        # speaker_0 is mapped
        assert config.get_camera_for_speaker(0, num_cameras=2) == 0
        # speaker_1 not mapped -> fallback to speaker_id (1)
        assert config.get_camera_for_speaker(1, num_cameras=2) == 1
        # speaker_5 not mapped and exceeds cameras -> clamp to 1
        assert config.get_camera_for_speaker(5, num_cameras=2) == 1


class TestDecisionEngineWithMapping:
    """Test DecisionEngine behavior with different segment scenarios."""

    def test_no_segments_single_camera(self) -> None:
        """No speaker segments = single camera output."""
        engine = DecisionEngine()
        cuts = engine.generate_cut_plan([], total_duration_ms=5000)
        assert len(cuts) == 1
        assert cuts[0].camera_id == 0

    def test_segments_produce_multiple_cuts(self) -> None:
        """Speaker segments produce camera switches."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
        )
        segments = [
            SpeakerSegment(0, 2000, 0),     # Camera 0
            SpeakerSegment(2000, 4000, 1),  # Camera 1
        ]
        cuts = engine.generate_cut_plan(segments, total_duration_ms=4000)

        assert len(cuts) == 2
        assert cuts[0].camera_id == 0
        assert cuts[1].camera_id == 1

    def test_single_speaker_no_switch(self) -> None:
        """Single speaker = no camera switches."""
        engine = DecisionEngine()
        segments = [
            SpeakerSegment(0, 5000, 0),  # Only speaker 0
        ]
        cuts = engine.generate_cut_plan(segments, total_duration_ms=5000)

        # Should be single continuous cut
        merged = engine.merge_adjacent(cuts)
        assert len(merged) == 1
        assert merged[0].camera_id == 0
