"""
GPU Warning Dialog for preflight checks.

Shows a warning when BEST_LIPS mode is selected without GPU.
"""

import logging
from typing import Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PyQt6.QtCore import Qt

from ..logic.switching_strategy import SwitchingStrategy

logger = logging.getLogger(__name__)


class GpuWarningDialog(QDialog):
    """Warning dialog for CPU-intensive processing without GPU."""
    
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Performance Warning")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        self._user_choice: Tuple[bool, SwitchingStrategy] = (
            True, SwitchingStrategy.BEST_LIPS
        )
        
        self._init_ui(message)
    
    def _init_ui(self, message: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Warning icon and message
        warning_label = QLabel(f"⚠️ {message}")
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(warning_label)
        
        # Recommendation
        recommend_label = QLabel(
            "💡 Recommendation: Use 'Fast (CPU)' or 'Balanced' for faster processing."
        )
        recommend_label.setWordWrap(True)
        recommend_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(recommend_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        # Switch to Fast button (recommended)
        self.btn_fast = QPushButton("⚡ Switch to Fast")
        self.btn_fast.setToolTip("Use rule-based switching (fastest)")
        self.btn_fast.clicked.connect(self._on_switch_fast)
        btn_layout.addWidget(self.btn_fast)
        
        # Switch to Balanced button
        self.btn_balanced = QPushButton("⚖️ Switch to Balanced")
        self.btn_balanced.setToolTip("Use hybrid detection (good balance)")
        self.btn_balanced.clicked.connect(self._on_switch_balanced)
        btn_layout.addWidget(self.btn_balanced)
        
        # Continue anyway button
        self.btn_continue = QPushButton("Continue (Best)")
        self.btn_continue.setToolTip("Continue with visual-only detection (slow)")
        self.btn_continue.clicked.connect(self._on_continue)
        btn_layout.addWidget(self.btn_continue)
        
        layout.addLayout(btn_layout)
    
    def _on_switch_fast(self) -> None:
        logger.info("User selected: Switch to Fast")
        self._user_choice = (True, SwitchingStrategy.FAST_RULES)
        self.accept()
    
    def _on_switch_balanced(self) -> None:
        logger.info("User selected: Switch to Balanced")
        self._user_choice = (True, SwitchingStrategy.BALANCED_LIPS_ENERGY)
        self.accept()
    
    def _on_continue(self) -> None:
        logger.info("User selected: Continue with Best (CPU)")
        self._user_choice = (True, SwitchingStrategy.BEST_LIPS)
        self.accept()
    
    def get_user_choice(self) -> Tuple[bool, SwitchingStrategy]:
        """Get the user's choice after dialog closes."""
        return self._user_choice


def show_gpu_warning_dialog(
    strategy: SwitchingStrategy,
    message: str,
    parent=None,
) -> Tuple[bool, SwitchingStrategy]:
    """
    Show GPU warning dialog and return user choice.
    
    Args:
        strategy: Current selected strategy.
        message: Warning message to display.
        parent: Parent widget.
        
    Returns:
        Tuple of (proceed, new_strategy).
    """
    dialog = GpuWarningDialog(message, parent)
    result = dialog.exec()
    
    if result == QDialog.DialogCode.Accepted:
        return dialog.get_user_choice()
    else:
        # Dialog closed without choice - continue with original
        logger.info("Dialog closed without explicit choice, continuing with original")
        return (True, strategy)
