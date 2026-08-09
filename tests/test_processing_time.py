# file: tests/test_processing_time.py
import time
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtWidgets import QApplication, QLabel
from multicam_editor.ui.main_window import MainWindow

@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def main_window(qtbot, qapp):
    """Create MainWindow for testing."""
    # Mock Project to avoid complex init
    with patch("multicam_editor.ui.main_window.Project"), \
         patch("multicam_editor.logic.processing_worker.ProcessingThread"):
        window = MainWindow()
        qtbot.addWidget(window)
        return window

def test_total_processing_time_display(main_window):
    """Verify that total processing time is calculated and displayed."""
    # 1. Simulate start of processing
    # We manually set the start time because we are not running the full thread
    start_time = time.time() - 90  # 90 seconds ago (1m 30s)
    main_window._processing_start_time = start_time
    
    # Simulate some detection stats present
    main_window._detection_time_s = 45.0
    main_window._detection_model = "TestModel"

    # 2. Simulate processing finished
    output_path = "/path/to/output.mp4"
    
    # Ensure label exists and is hidden initially
    assert hasattr(main_window, "lbl_detection_stats")
    
    # Call the finished handler directly
    main_window._on_processing_finished(output_path)
    
    # 3. Verify the label text
    text = main_window.lbl_detection_stats.text()
    
    # Should contain Total Time
    assert "Total Time" in text
    
    # Should contain formatted time (approx 1m 30s)
    # Since time continues to tick, it might be 1m 30s or 1m 31s
    assert "1m 30s" in text or "1m 31s" in text
    
    # Should also still contain detection time
    assert "Detection: 45s" in text
    assert "TestModel" in text

def test_processing_time_start_recording(main_window):
    """Verify that start time is recorded when processing starts."""
    # Mock dependencies to allow on_process_videos to run far enough
    main_window.project = MagicMock()
    # Mock clips to have duration
    clip = MagicMock()
    clip.duration_ms = 10000
    clip.path = "/tmp/video1.mp4"
    main_window.project.clips.return_value = [clip, clip]
    
    # Mock settings
    main_window.settings = MagicMock()
    main_window.settings.value.return_value = 0 # Model index 0 (Fast)
    
    # Mock preflight and checks
    with patch("multicam_editor.ui.main_window.run_gpu_preflight_check") as mock_preflight, \
         patch("multicam_editor.ui.main_window.check_preflight_warnings") as mock_warnings, \
         patch("multicam_editor.logic.preflight.detect_gpu", return_value=True):
         
        mock_preflight.return_value.final_strategy.value = "fast"
        mock_warnings.return_value = []
        
        # Manually ensure ProcessingThread is mocked so we don't actually start threads
        main_window._processing_thread = MagicMock()

        # Call process
        # We need to mock the processing thread creation inside the method or just check if start time set
        # The method creates a new ProcessingThread instance.
        # We can inspect if _processing_start_time is set.
        
        # Reset start time
        if hasattr(main_window, "_processing_start_time"):
            del main_window._processing_start_time
            
        # We need to patch the thread class used in the method
        with patch("multicam_editor.logic.processing_worker.ProcessingThread"):
            # Also mock progress dialog
            main_window._progress_dialog = MagicMock()
            
            main_window.on_process_videos()
            
            # Verify start time was set
            assert hasattr(main_window, "_processing_start_time")
            assert main_window._processing_start_time > 0
            assert abs(main_window._processing_start_time - time.time()) < 5 # Within last 5 seconds
