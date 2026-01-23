"""Magic Settings dialog for AI processing options.

Provides future AI automation controls in a clean tabbed interface.
All settings persist to QSettings with 'magic/' prefix.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class MagicSettingsDialog(QDialog):
    """Dialog for configuring AI processing options.
    
    Provides placeholder controls for future AI features:
    - AI Director (split screen, reaction shots)
    - Audio Engineer (leveling, noise reduction, ducking)
    - Captions & Branding (styles, logos)
    - Content Repurposing (teasers, silence removal)
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("✨ Magic Settings")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setMinimumHeight(400)
        
        self.settings = QSettings("MultiCamEditor", "MultiCamEditor")
        
        # Detect theme for styling
        self._dark_mode = self.settings.value("appearance/theme", "light", type=str) == "dark"
        
        self._init_ui()
        self._load_settings()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Header
        header = QLabel("Configure your zero-click automation pipeline")
        header.setStyleSheet("color: #888; font-style: italic; margin-bottom: 8px;")
        layout.addWidget(header)
        
        # Tab widget
        tabs = QTabWidget(self)
        tabs.setObjectName("magicSettingsTabs")
        
        # Tab 1: AI Director
        tabs.addTab(self._create_director_tab(), "🎬 AI Director")
        
        # Tab 2: Audio Engineer
        tabs.addTab(self._create_audio_tab(), "🎧 Audio")
        
        # Tab 3: Captions & Branding
        tabs.addTab(self._create_captions_tab(), "📝 Captions")
        
        # Tab 4: Content Repurposing
        tabs.addTab(self._create_repurpose_tab(), "📱 Repurpose")
        
        layout.addWidget(tabs)
        
        # Coming soon notice
        notice = QLabel("⚡ These features are coming soon. Settings are saved for future use.")
        notice.setStyleSheet("color: #f39c12; font-size: 11px; padding: 8px;")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        
        # Button box
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self
        )
        btn_box.accepted.connect(self._save_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        # Apply theme styling
        self._apply_theme()

    def _create_director_tab(self) -> QWidget:
        """Create AI Director settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        
        # Split Screen options
        group = QGroupBox("Camera Composition")
        group_layout = QVBoxLayout(group)
        
        self.chk_split_screen = QCheckBox("Enable Split Screen Mode")
        self.chk_split_screen.setToolTip(
            "Automatically use split screen when multiple speakers talk simultaneously"
        )
        group_layout.addWidget(self.chk_split_screen)
        
        self.chk_reaction_shots = QCheckBox("Include Reaction Shots")
        self.chk_reaction_shots.setToolTip(
            "Cut to listener reactions during key moments"
        )
        group_layout.addWidget(self.chk_reaction_shots)
        
        self.chk_wide_reset = QCheckBox("Wide Shot Reset")
        self.chk_wide_reset.setToolTip(
            "Periodically cut to wide shot for scene orientation"
        )
        group_layout.addWidget(self.chk_wide_reset)
        
        layout.addWidget(group)
        layout.addStretch()
        
        return widget

    def _create_audio_tab(self) -> QWidget:
        """Create Audio Engineer settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        
        group = QGroupBox("Audio Processing")
        group_layout = QVBoxLayout(group)
        
        self.chk_auto_leveling = QCheckBox("Auto-Leveling (Normalize)")
        self.chk_auto_leveling.setToolTip(
            "Automatically normalize audio levels across all speakers"
        )
        group_layout.addWidget(self.chk_auto_leveling)
        
        self.chk_noise_reduction = QCheckBox("AI Noise Reduction")
        self.chk_noise_reduction.setToolTip(
            "Remove background noise, hum, and unwanted sounds"
        )
        group_layout.addWidget(self.chk_noise_reduction)
        
        self.chk_auto_ducking = QCheckBox("Auto-Ducking (Music/SFX)")
        self.chk_auto_ducking.setToolTip(
            "Automatically lower background music when speakers talk"
        )
        group_layout.addWidget(self.chk_auto_ducking)
        
        layout.addWidget(group)
        layout.addStretch()
        
        return widget

    def _create_captions_tab(self) -> QWidget:
        """Create Captions & Branding settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        
        # Caption Style
        group = QGroupBox("Auto-Captions")
        group_layout = QFormLayout(group)
        
        self.cmb_caption_style = QComboBox()
        self.cmb_caption_style.addItems([
            "None (No Captions)",
            "Hormozi Style (Bold, Animated)",
            "Clean (Minimal)",
            "Netflix (Subtitle)",
            "MrBeast (Color Pop)",
        ])
        self.cmb_caption_style.setToolTip(
            "Choose an auto-generated caption style for your video"
        )
        group_layout.addRow("Caption Style:", self.cmb_caption_style)
        
        layout.addWidget(group)
        
        # Branding
        group2 = QGroupBox("Branding")
        group2_layout = QVBoxLayout(group2)
        
        self.btn_add_logo = QPushButton("Add Logo/Watermark...")
        self.btn_add_logo.setEnabled(False)  # Placeholder
        self.btn_add_logo.setToolTip("Add a logo watermark to your video")
        group2_layout.addWidget(self.btn_add_logo)
        
        self.btn_add_intro = QPushButton("Add Intro/Outro...")
        self.btn_add_intro.setEnabled(False)  # Placeholder
        self.btn_add_intro.setToolTip("Add intro and outro sequences")
        group2_layout.addWidget(self.btn_add_intro)
        
        layout.addWidget(group2)
        layout.addStretch()
        
        return widget

    def _create_repurpose_tab(self) -> QWidget:
        """Create Content Repurposing settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        
        group = QGroupBox("Content Derivatives")
        group_layout = QVBoxLayout(group)
        
        self.chk_vertical_teasers = QCheckBox("Generate Vertical Teasers (9:16)")
        self.chk_vertical_teasers.setToolTip(
            "Auto-create short TikTok/Reels/Shorts clips from highlights"
        )
        group_layout.addWidget(self.chk_vertical_teasers)
        
        self.chk_remove_silence = QCheckBox("Remove Silence (Podcast Mode)")
        self.chk_remove_silence.setToolTip(
            "Automatically cut dead air and long pauses"
        )
        group_layout.addWidget(self.chk_remove_silence)
        
        layout.addWidget(group)
        
        # Teaser count hint
        hint = QLabel("📊 Based on your video length, we'll generate 3-5 teasers")
        hint.setStyleSheet("color: #888; font-size: 11px; margin-top: 8px;")
        layout.addWidget(hint)
        
        layout.addStretch()
        
        return widget

    def _load_settings(self) -> None:
        """Load saved settings from QSettings."""
        # AI Director
        self.chk_split_screen.setChecked(
            self.settings.value("magic/director/split_screen", False, type=bool)
        )
        self.chk_reaction_shots.setChecked(
            self.settings.value("magic/director/reaction_shots", False, type=bool)
        )
        self.chk_wide_reset.setChecked(
            self.settings.value("magic/director/wide_reset", False, type=bool)
        )
        
        # Audio Engineer
        self.chk_auto_leveling.setChecked(
            self.settings.value("magic/audio/auto_leveling", True, type=bool)
        )
        self.chk_noise_reduction.setChecked(
            self.settings.value("magic/audio/noise_reduction", False, type=bool)
        )
        self.chk_auto_ducking.setChecked(
            self.settings.value("magic/audio/auto_ducking", False, type=bool)
        )
        
        # Captions
        caption_index = self.settings.value("magic/captions/style_index", 0, type=int)
        self.cmb_caption_style.setCurrentIndex(
            min(caption_index, self.cmb_caption_style.count() - 1)
        )
        
        # Repurposing
        self.chk_vertical_teasers.setChecked(
            self.settings.value("magic/repurpose/vertical_teasers", False, type=bool)
        )
        self.chk_remove_silence.setChecked(
            self.settings.value("magic/repurpose/remove_silence", False, type=bool)
        )

    def _save_and_accept(self) -> None:
        """Save settings to QSettings and close dialog."""
        # AI Director
        self.settings.setValue("magic/director/split_screen", self.chk_split_screen.isChecked())
        self.settings.setValue("magic/director/reaction_shots", self.chk_reaction_shots.isChecked())
        self.settings.setValue("magic/director/wide_reset", self.chk_wide_reset.isChecked())
        
        # Audio Engineer
        self.settings.setValue("magic/audio/auto_leveling", self.chk_auto_leveling.isChecked())
        self.settings.setValue("magic/audio/noise_reduction", self.chk_noise_reduction.isChecked())
        self.settings.setValue("magic/audio/auto_ducking", self.chk_auto_ducking.isChecked())
        
        # Captions
        self.settings.setValue("magic/captions/style_index", self.cmb_caption_style.currentIndex())
        
        # Repurposing
        self.settings.setValue("magic/repurpose/vertical_teasers", self.chk_vertical_teasers.isChecked())
        self.settings.setValue("magic/repurpose/remove_silence", self.chk_remove_silence.isChecked())
        
        logger.info("Magic settings saved")
        self.accept()

    def _apply_theme(self) -> None:
        """Apply theme-aware styling."""
        if self._dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #2d2d2d;
                    color: #e0e0e0;
                }
                QGroupBox {
                    font-weight: bold;
                    border: 1px solid #555;
                    border-radius: 6px;
                    margin-top: 12px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QCheckBox {
                    spacing: 8px;
                }
                QTabWidget::pane {
                    border: 1px solid #555;
                    border-radius: 6px;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #ffffff;
                }
                QGroupBox {
                    font-weight: bold;
                    border: 1px solid #ddd;
                    border-radius: 6px;
                    margin-top: 12px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QCheckBox {
                    spacing: 8px;
                }
                QTabWidget::pane {
                    border: 1px solid #ddd;
                    border-radius: 6px;
                }
            """)


def get_magic_settings() -> dict:
    """Load all magic settings as a dictionary (helper for other modules)."""
    settings = QSettings("MultiCamEditor", "MultiCamEditor")
    
    return {
        "director": {
            "split_screen": settings.value("magic/director/split_screen", False, type=bool),
            "reaction_shots": settings.value("magic/director/reaction_shots", False, type=bool),
            "wide_reset": settings.value("magic/director/wide_reset", False, type=bool),
        },
        "audio": {
            "auto_leveling": settings.value("magic/audio/auto_leveling", True, type=bool),
            "noise_reduction": settings.value("magic/audio/noise_reduction", False, type=bool),
            "auto_ducking": settings.value("magic/audio/auto_ducking", False, type=bool),
        },
        "captions": {
            "style_index": settings.value("magic/captions/style_index", 0, type=int),
        },
        "repurpose": {
            "vertical_teasers": settings.value("magic/repurpose/vertical_teasers", False, type=bool),
            "remove_silence": settings.value("magic/repurpose/remove_silence", False, type=bool),
        },
    }
