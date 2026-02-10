"""Tests for the processing pipeline orchestrator."""

import pytest
from unittest.mock import MagicMock, patch

from multicam_editor.logic.processing_pipeline import (
    ProcessingPipeline,
    PipelineStage,
    PipelineProgress,
    PipelineResult,
    STAGE_WEIGHTS,
)
from multicam_editor.utils.signals import ProcessingSignals

# Patch target for PreflightManager - must be where it's defined since
# processing_pipeline.py uses a local import: from .preflight import PreflightManager
_PREFLIGHT_PATCH = 'multicam_editor.logic.preflight.PreflightManager'


def _mock_preflight_pass(mock_cls):
    """Configure a mock PreflightManager to always pass."""
    instance = mock_cls.return_value
    result = MagicMock()
    result.ok = True
    result.critical_errors = []
    result.warnings = []
    instance.run_full_check.return_value = result


class TestPipelineStage:
    """Tests for pipeline stage enum."""

    def test_stage_order(self):
        """Verify stages are in expected order."""
        stages = list(PipelineStage)
        assert stages[0] == PipelineStage.PROBE
        assert stages[-1] == PipelineStage.DONE

    def test_stage_weights_defined(self):
        """All processing stages should have weights."""
        for stage in PipelineStage:
            if stage != PipelineStage.DONE:
                assert stage in STAGE_WEIGHTS


class TestPipelineProgress:
    """Tests for progress dataclass."""

    def test_progress_creation(self):
        """Progress can be created with all fields."""
        progress = PipelineProgress(
            stage=PipelineStage.PROBE,
            stage_name="Probe",
            overall_percent=25,
            stage_percent=50,
            eta_seconds=60.0,
            message="Probing files",
        )
        assert progress.stage == PipelineStage.PROBE
        assert progress.overall_percent == 25
        assert progress.eta_seconds == 60.0


class TestProcessingPipeline:
    """Tests for the main pipeline class."""

    def test_init_requires_min_two_files(self):
        """Pipeline should require at least 2 input files."""
        signals = ProcessingSignals()

        with pytest.raises(ValueError, match="At least 2 input files required"):
            ProcessingPipeline(["file1.mp4"], signals)

    def test_init_with_valid_files(self):
        """Pipeline initializes with 2+ files."""
        signals = ProcessingSignals()
        pipeline = ProcessingPipeline(["file1.mp4", "file2.mp4"], signals)

        assert len(pipeline.input_files) == 2
        assert pipeline._cancelled is False

    def test_init_speaker_switching_default_enabled(self):
        """Pipeline defaults to speaker_switching_enabled=True."""
        signals = ProcessingSignals()
        pipeline = ProcessingPipeline(["file1.mp4", "file2.mp4"], signals)
        assert pipeline.speaker_switching_enabled is True

    def test_init_speaker_switching_can_be_disabled(self):
        """Pipeline can be created with speaker_switching_enabled=False."""
        signals = ProcessingSignals()
        pipeline = ProcessingPipeline(
            ["file1.mp4", "file2.mp4"], signals, speaker_switching_enabled=False
        )
        assert pipeline.speaker_switching_enabled is False

    def test_cancel_sets_flag(self):
        """Cancel should set cancelled flag."""
        signals = ProcessingSignals()
        pipeline = ProcessingPipeline(["file1.mp4", "file2.mp4"], signals)

        pipeline.cancel()
        assert pipeline._cancelled is True

    def test_probe_stage_fails_on_error(self):
        """Pipeline should fail if probe returns error."""
        from multicam_editor.utils.ffprobe import ProbeResult

        with patch(_PREFLIGHT_PATCH) as mock_preflight, \
             patch('multicam_editor.logic.processing_pipeline.probe') as mock_probe:
            _mock_preflight_pass(mock_preflight)
            mock_probe.return_value = ProbeResult(duration_ms=0, error="File not found")

            signals = ProcessingSignals()
            error_captured = []
            signals.error.connect(error_captured.append)

            pipeline = ProcessingPipeline(["file1.mp4", "file2.mp4"], signals)
            result = pipeline.run()

        assert result.success is False
        assert "Probe stage failed" in result.error

    def test_cancel_during_probe(self):
        """Pipeline should stop when cancelled during probe."""
        from multicam_editor.utils.ffprobe import ProbeResult

        with patch(_PREFLIGHT_PATCH) as mock_preflight, \
             patch('multicam_editor.logic.processing_pipeline.probe') as mock_probe:
            _mock_preflight_pass(mock_preflight)

            def cancel_on_first_call(*args):
                pipeline.cancel()
                return ProbeResult(duration_ms=5000)

            mock_probe.side_effect = cancel_on_first_call

            signals = ProcessingSignals()
            pipeline = ProcessingPipeline(["file1.mp4", "file2.mp4"], signals)
            result = pipeline.run()

        assert result.cancelled is True
        assert result.success is False

    def test_progress_callback_called(self):
        """Progress callback should be invoked."""
        from multicam_editor.utils.ffprobe import ProbeResult

        signals = ProcessingSignals()
        progress_updates = []

        def on_progress(p: PipelineProgress):
            progress_updates.append(p)

        with patch(_PREFLIGHT_PATCH) as mock_preflight, \
             patch('multicam_editor.logic.processing_pipeline.probe') as mock_probe:
            _mock_preflight_pass(mock_preflight)
            mock_probe.return_value = ProbeResult(duration_ms=0, error="test error")

            pipeline = ProcessingPipeline(
                ["file1.mp4", "file2.mp4"],
                signals,
                progress_callback=on_progress,
            )
            pipeline.run()

        # Should have at least one progress update
        assert len(progress_updates) > 0
        assert progress_updates[0].stage == PipelineStage.PROBE


class TestPipelineResult:
    """Tests for pipeline result dataclass."""

    def test_success_result(self):
        """Success result has correct fields."""
        result = PipelineResult(success=True, output_path="/path/to/output.mp4")
        assert result.success is True
        assert result.output_path == "/path/to/output.mp4"
        assert result.cancelled is False

    def test_cancelled_result(self):
        """Cancelled result has correct fields."""
        result = PipelineResult(success=False, cancelled=True)
        assert result.success is False
        assert result.cancelled is True

    def test_error_result(self):
        """Error result has correct fields."""
        result = PipelineResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_detection_stats_default_values(self):
        """Detection stats fields default to zero/empty."""
        result = PipelineResult(success=True, output_path="/path/to/output.mp4")
        assert result.detection_time_s == 0.0
        assert result.detection_model == ""

    def test_detection_stats_with_values(self):
        """Detection stats can be set on result."""
        result = PipelineResult(
            success=True,
            output_path="/path/to/output.mp4",
            detection_time_s=135.5,
            detection_model="Balanced (Hybrid)",
        )
        assert result.detection_time_s == 135.5
        assert result.detection_model == "Balanced (Hybrid)"

    def test_detection_stats_with_all_strategies(self):
        """Detection stats work with all strategy names."""
        strategies = ["Best (Lips)", "Balanced (Hybrid)", "Fast (Energy)"]
        for strategy in strategies:
            result = PipelineResult(
                success=True,
                detection_time_s=60.0,
                detection_model=strategy,
            )
            assert result.detection_model == strategy
