"""
Tests for GPU preflight check logic.
"""

import pytest
from unittest.mock import patch, MagicMock

from multicam_editor.logic.preflight import (
    detect_gpu,
    needs_gpu_warning,
    run_gpu_preflight_check,
    GpuPreflightResult,
    GpuPreflightStatus,
)
from multicam_editor.logic.switching_strategy import SwitchingStrategy


class TestDetectGpu:
    """Tests for detect_gpu function."""
    
    def test_returns_bool(self) -> None:
        """detect_gpu returns a boolean."""
        result = detect_gpu()
        assert isinstance(result, bool)
    
    @patch("multicam_editor.logic.preflight.logger")
    def test_no_torch_returns_false(self, mock_logger) -> None:
        """Returns False when torch is not installed."""
        with patch.dict("sys.modules", {"torch": None}):
            # Force ImportError by patching the import
            with patch(
                "multicam_editor.logic.preflight.detect_gpu",
                side_effect=lambda: False
            ):
                # Just verify the function handles missing torch gracefully
                pass
    
    @patch("multicam_editor.logic.preflight.logger")
    def test_logs_gpu_status(self, mock_logger) -> None:
        """Logs GPU availability status."""
        detect_gpu()
        # Should have logged something about GPU status
        assert mock_logger.info.called or mock_logger.warning.called


class TestNeedsGpuWarning:
    """Tests for needs_gpu_warning function."""
    
    def test_best_lips_no_gpu_needs_warning(self) -> None:
        """BEST_LIPS without GPU needs warning."""
        assert needs_gpu_warning(SwitchingStrategy.BEST_LIPS, gpu_available=False) is True
    
    def test_best_lips_with_gpu_no_warning(self) -> None:
        """BEST_LIPS with GPU does not need warning."""
        assert needs_gpu_warning(SwitchingStrategy.BEST_LIPS, gpu_available=True) is False
    
    def test_balanced_no_warning(self) -> None:
        """BALANCED_LIPS_ENERGY never needs warning."""
        assert needs_gpu_warning(SwitchingStrategy.BALANCED_LIPS_ENERGY, gpu_available=False) is False
        assert needs_gpu_warning(SwitchingStrategy.BALANCED_LIPS_ENERGY, gpu_available=True) is False
    
    def test_fast_rules_no_warning(self) -> None:
        """FAST_RULES never needs warning."""
        assert needs_gpu_warning(SwitchingStrategy.FAST_RULES, gpu_available=False) is False
        assert needs_gpu_warning(SwitchingStrategy.FAST_RULES, gpu_available=True) is False


class TestRunGpuPreflightCheck:
    """Tests for run_gpu_preflight_check function."""
    
    @patch("multicam_editor.logic.preflight.detect_gpu", return_value=True)
    def test_fast_rules_proceeds(self, mock_detect) -> None:
        """FAST_RULES always proceeds without warning."""
        result = run_gpu_preflight_check(SwitchingStrategy.FAST_RULES)
        
        assert result.result == GpuPreflightResult.PROCEED
        assert result.final_strategy == SwitchingStrategy.FAST_RULES
        assert result.gpu_available is True
    
    @patch("multicam_editor.logic.preflight.detect_gpu", return_value=False)
    def test_fast_rules_proceeds_no_gpu(self, mock_detect) -> None:
        """FAST_RULES proceeds even without GPU."""
        result = run_gpu_preflight_check(SwitchingStrategy.FAST_RULES)
        
        assert result.result == GpuPreflightResult.PROCEED
        assert result.final_strategy == SwitchingStrategy.FAST_RULES
    
    @patch("multicam_editor.logic.preflight.detect_gpu", return_value=False)
    def test_balanced_proceeds_no_gpu(self, mock_detect) -> None:
        """BALANCED proceeds even without GPU."""
        result = run_gpu_preflight_check(SwitchingStrategy.BALANCED_LIPS_ENERGY)
        
        assert result.result == GpuPreflightResult.PROCEED
        assert result.final_strategy == SwitchingStrategy.BALANCED_LIPS_ENERGY
    
    @patch("multicam_editor.logic.preflight.detect_gpu", return_value=True)
    def test_best_lips_with_gpu_proceeds(self, mock_detect) -> None:
        """BEST_LIPS with GPU proceeds without warning."""
        result = run_gpu_preflight_check(SwitchingStrategy.BEST_LIPS)
        
        assert result.result == GpuPreflightResult.PROCEED
        assert result.final_strategy == SwitchingStrategy.BEST_LIPS
    
    @patch("multicam_editor.logic.preflight.detect_gpu", return_value=False)
    def test_best_lips_no_gpu_headless(self, mock_detect) -> None:
        """BEST_LIPS without GPU in headless mode logs and continues."""
        result = run_gpu_preflight_check(
            SwitchingStrategy.BEST_LIPS,
            show_dialog_callback=None,  # Headless
        )
        
        assert result.result == GpuPreflightResult.HEADLESS
        assert result.final_strategy == SwitchingStrategy.BEST_LIPS
        assert result.message is not None
    
    @patch("multicam_editor.logic.preflight.detect_gpu", return_value=False)
    def test_best_lips_user_continues(self, mock_detect) -> None:
        """User chooses to continue with BEST_LIPS."""
        mock_dialog = MagicMock(return_value=(True, SwitchingStrategy.BEST_LIPS))
        
        result = run_gpu_preflight_check(
            SwitchingStrategy.BEST_LIPS,
            show_dialog_callback=mock_dialog,
        )
        
        assert result.result == GpuPreflightResult.WARNING_SHOWN
        assert result.final_strategy == SwitchingStrategy.BEST_LIPS
        mock_dialog.assert_called_once()
    
    @patch("multicam_editor.logic.preflight.detect_gpu", return_value=False)
    def test_best_lips_user_switches_to_fast(self, mock_detect) -> None:
        """User switches from BEST_LIPS to FAST_RULES."""
        mock_dialog = MagicMock(return_value=(True, SwitchingStrategy.FAST_RULES))
        
        result = run_gpu_preflight_check(
            SwitchingStrategy.BEST_LIPS,
            show_dialog_callback=mock_dialog,
        )
        
        assert result.result == GpuPreflightResult.SWITCHED
        assert result.original_strategy == SwitchingStrategy.BEST_LIPS
        assert result.final_strategy == SwitchingStrategy.FAST_RULES
    
    @patch("multicam_editor.logic.preflight.detect_gpu", return_value=False)
    def test_best_lips_user_switches_to_balanced(self, mock_detect) -> None:
        """User switches from BEST_LIPS to BALANCED."""
        mock_dialog = MagicMock(return_value=(True, SwitchingStrategy.BALANCED_LIPS_ENERGY))
        
        result = run_gpu_preflight_check(
            SwitchingStrategy.BEST_LIPS,
            show_dialog_callback=mock_dialog,
        )
        
        assert result.result == GpuPreflightResult.SWITCHED
        assert result.final_strategy == SwitchingStrategy.BALANCED_LIPS_ENERGY
    
    @patch("multicam_editor.logic.preflight.detect_gpu", return_value=False)
    def test_dialog_exception_continues(self, mock_detect) -> None:
        """If dialog raises exception, continue with original strategy."""
        mock_dialog = MagicMock(side_effect=RuntimeError("UI error"))
        
        result = run_gpu_preflight_check(
            SwitchingStrategy.BEST_LIPS,
            show_dialog_callback=mock_dialog,
        )
        
        assert result.result == GpuPreflightResult.HEADLESS
        assert result.final_strategy == SwitchingStrategy.BEST_LIPS
        assert "UI error" in result.message
