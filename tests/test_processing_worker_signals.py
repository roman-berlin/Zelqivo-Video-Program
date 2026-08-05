"""Tests for ProcessingWorker signals."""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import QObject

from multicam_editor.logic.processing_worker import ProcessingWorker
from multicam_editor.logic.processing_pipeline import PipelineResult

class TestProcessingWorkerSignals:
    """Test signal emissions from ProcessingWorker."""

    def test_detection_stats_signal_emitted(self):
        """Worker should emit detection_stats when result contains them."""
        # Setup
        worker = ProcessingWorker(
            input_files=["file1.mp4", "file2.mp4"],
            speaker_switching_enabled=True
        )
        
        # Mock signals to verify emission
        mock_stats_slot = MagicMock()
        worker.detection_stats.connect(mock_stats_slot)
        
        # Mock the pipeline (which is created inside run())
        with patch('multicam_editor.logic.processing_worker.ProcessingPipeline') as MockPipeline:
            # Configure pipeline mock to return a result with stats
            mock_pipeline_instance = MockPipeline.return_value
            mock_pipeline_instance.run.return_value = PipelineResult(
                success=True,
                output_path="out.mp4",
                detection_time_s=42.5,
                detection_model="Test Model"
            )
            
            # Run worker
            worker.run()
            
            # Verify signal emission
            mock_stats_slot.assert_called_once_with(42.5, "Test Model")

    def test_detection_stats_signal_not_emitted_if_zero(self):
        """Worker should not emit detection_stats if time is 0."""
        # Setup
        worker = ProcessingWorker(
            input_files=["file1.mp4", "file2.mp4"],
            speaker_switching_enabled=True
        )
        
        # Mock signal
        mock_stats_slot = MagicMock()
        worker.detection_stats.connect(mock_stats_slot)
        
        # Mock pipeline result with no stats
        with patch('multicam_editor.logic.processing_worker.ProcessingPipeline') as MockPipeline:
            mock_pipeline_instance = MockPipeline.return_value
            mock_pipeline_instance.run.return_value = PipelineResult(
                success=True,
                output_path="out.mp4",
                detection_time_s=0.0,
                detection_model=""
            )
            
            worker.run()
            
            # Verify signal was NOT emitted
            mock_stats_slot.assert_not_called()
