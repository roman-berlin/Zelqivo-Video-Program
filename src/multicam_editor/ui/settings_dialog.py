"""Settings dialog for configuring application behavior."""

from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QSpinBox,
    QComboBox,
    QVBoxLayout,
    QGroupBox,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QScrollArea,
    QWidget,
)

from ..core.project import AudioMixMode, AudioMixSettings
from ..logic.active_speaker import DiarizationMode
from ..logic.switching_strategy import SwitchingStrategy, DEFAULT_STRATEGY
from ..logic.debug_export import export_debug_package
import logging
import os

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Dialog for editing application settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(420, 550)  # Taller to show more content
        self.setMinimumHeight(400)
        self.setMaximumHeight(800)
        self.settings = QSettings("MultiCamEditor", "MultiCamEditor")

        self._init_ui()
        self._load_settings()

    def _init_ui(self) -> None:
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # Create scroll area for all settings content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        # Container widget for scroll area content
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(12)
        layout.setContentsMargins(4, 4, 4, 4)

        # 1. Appearance Settings
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout()
        appearance_layout.setSpacing(8)

        # Toggle button for dark/light mode
        self.btn_theme_toggle = QPushButton("🌙 Dark Mode")
        self.btn_theme_toggle.setCheckable(True)
        self.btn_theme_toggle.setToolTip("Toggle between light and dark themes")
        self.btn_theme_toggle.setObjectName("btnThemeToggle")
        self.btn_theme_toggle.toggled.connect(self._on_dark_mode_toggled)
        appearance_layout.addRow("Theme:", self.btn_theme_toggle)

        appearance_group.setLayout(appearance_layout)
        layout.addWidget(appearance_group)

        # 2. Output Settings
        output_group = QGroupBox("Output")
        output_layout = QFormLayout()
        output_layout.setSpacing(8)

        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["1080p", "720p", "480p"])
        output_layout.addRow("Output Quality:", self.combo_quality)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # 3. Diarization Settings
        diarization_group = QGroupBox("Diarization (Who is speaking?)")
        diarization_layout = QFormLayout()

        self.combo_diarization_mode = QComboBox()
        self.combo_diarization_mode.addItem("Hybrid (Audio VAD + Visual) - Recommended", DiarizationMode.HYBRID.value)
        self.combo_diarization_mode.addItem("Lips Only (Strict Visual) - Experimental", DiarizationMode.LIPS.value)
        self.combo_diarization_mode.setToolTip(
            "Hybrid: Uses audio to detect speech timing, Lips to identify speaker.\n"
            "Lips Only: Uses visual movement for both timing and identification (no audio)."
        )
        diarization_layout.addRow("Detection Mode:", self.combo_diarization_mode)
        
        # Switching Quality dropdown
        self.combo_switching_quality = QComboBox()
        self.combo_switching_quality.addItem("⚡ Fast (CPU) - Recommended", SwitchingStrategy.FAST_RULES.value)
        self.combo_switching_quality.addItem("⚖️ Balanced - Hybrid", SwitchingStrategy.BALANCED_LIPS_ENERGY.value)
        self.combo_switching_quality.addItem("🎯 Best - Visual Only", SwitchingStrategy.BEST_LIPS.value)
        self.combo_switching_quality.setToolTip(
            "Fast: Energy + Rules, recommended for most users.\n"
            "Balanced: Hybrid audio + visual detection.\n"
            "Best: Visual-only (may be slow without GPU)."
        )
        diarization_layout.addRow("Switching Quality:", self.combo_switching_quality)
        
        diarization_group.setLayout(diarization_layout)
        layout.addWidget(diarization_group)

        # 3. Advanced Settings Toggle Button
        self.btn_advanced = QPushButton("⚙️ Show Advanced Settings")
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.setObjectName("btnAdvanced")
        self.btn_advanced.toggled.connect(self._toggle_advanced_settings)
        layout.addWidget(self.btn_advanced)

        # 4. Advanced Settings Container
        self.advanced_container = QGroupBox("Advanced Configuration")
        self.advanced_container.setVisible(False)
        advanced_layout = QVBoxLayout()
        advanced_layout.setSpacing(8)
        
        # Audio Mix Settings
        audio_group = QGroupBox("Audio Mix (External Audio)")
        audio_layout = QFormLayout()
        audio_layout.setSpacing(6)

        self.combo_audio_mode = QComboBox()
        self.combo_audio_mode.addItems(["Replace", "Mix"])
        self.combo_audio_mode.currentTextChanged.connect(self._on_audio_mode_changed)
        audio_layout.addRow("Mode:", self.combo_audio_mode)

        self.spin_video_gain = QDoubleSpinBox()
        self.spin_video_gain.setRange(-60.0, 12.0)
        self.spin_video_gain.setSingleStep(1.0)
        self.spin_video_gain.setSuffix(" dB")
        self.spin_video_gain.setDecimals(1)
        audio_layout.addRow("Video Audio Gain:", self.spin_video_gain)

        self.spin_external_gain = QDoubleSpinBox()
        self.spin_external_gain.setRange(-60.0, 12.0)
        self.spin_external_gain.setSingleStep(1.0)
        self.spin_external_gain.setSuffix(" dB")
        self.spin_external_gain.setDecimals(1)
        audio_layout.addRow("External Audio Gain:", self.spin_external_gain)

        self.check_ducking = QCheckBox()
        self.check_ducking.toggled.connect(self._on_ducking_toggled)
        audio_layout.addRow("Enable Ducking:", self.check_ducking)

        self.spin_ducking_amount = QDoubleSpinBox()
        self.spin_ducking_amount.setRange(-60.0, 0.0)
        self.spin_ducking_amount.setSingleStep(1.0)
        self.spin_ducking_amount.setSuffix(" dB")
        self.spin_ducking_amount.setDecimals(1)
        audio_layout.addRow("Ducking Amount:", self.spin_ducking_amount)

        audio_group.setLayout(audio_layout)
        advanced_layout.addWidget(audio_group)

        # Decision Engine Settings
        engine_group = QGroupBox("Decision Engine Rules")
        engine_layout = QFormLayout()
        engine_layout.setSpacing(6)

        self.spin_min_switch = QSpinBox()
        self.spin_min_switch.setRange(100, 10000)
        self.spin_min_switch.setSingleStep(100)
        self.spin_min_switch.setSuffix(" ms")
        self.spin_min_switch.setToolTip("Minimum time between camera switches")
        engine_layout.addRow("Min Switch Interval:", self.spin_min_switch)

        self.spin_min_speech = QSpinBox()
        self.spin_min_speech.setRange(100, 5000)
        self.spin_min_speech.setSingleStep(50)
        self.spin_min_speech.setSuffix(" ms")
        self.spin_min_speech.setToolTip("Minimum speech segment duration to consider")
        engine_layout.addRow("Min Speech Duration:", self.spin_min_speech)

        self.spin_bg_short_remark = QSpinBox()
        self.spin_bg_short_remark.setRange(50, 2000)
        self.spin_bg_short_remark.setSingleStep(50)
        self.spin_bg_short_remark.setSuffix(" ms")
        self.spin_bg_short_remark.setToolTip("Ignore very short noises/remarks")
        engine_layout.addRow("Ignore Short Remarks Below:", self.spin_bg_short_remark)

        engine_group.setLayout(engine_layout)
        advanced_layout.addWidget(engine_group)

        # QA Overlay Settings
        qa_group = QGroupBox("QA / Debugging")
        qa_layout = QFormLayout()

        self.check_qa_overlay = QCheckBox()
        self.check_qa_overlay.setToolTip(
            "Burn timecode, speaker ID, and camera index into exported video.\n"
            "Useful for manual QA review. OFF by default."
        )
        qa_layout.addRow("Enable QA Overlay:", self.check_qa_overlay)

        qa_group.setLayout(qa_layout)
        advanced_layout.addWidget(qa_group)

        # Maintenance / Support
        maint_group = QGroupBox("Maintenance")
        maint_layout = QVBoxLayout()
        
        self.btn_export_debug = QPushButton("Export Debug Package")
        self.btn_export_debug.setToolTip("Create a zip file with logs and diagnostics for support")
        self.btn_export_debug.clicked.connect(self._on_export_debug_clicked)
        maint_layout.addWidget(self.btn_export_debug)

        maint_group.setLayout(maint_layout)
        advanced_layout.addWidget(maint_group)

        self.advanced_container.setLayout(advanced_layout)
        layout.addWidget(self.advanced_container)

        # Add stretch to push content up when there's extra space
        layout.addStretch(1)

        # Finalize scroll area
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)  # Give scroll area stretch priority

        # Dialog buttons (outside scroll area so always visible)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)


    def _on_dark_mode_toggled(self, checked: bool) -> None:
        """Apply dark mode immediately when toggled."""
        theme = "dark" if checked else "light"
        self.settings.setValue("appearance/theme", theme)
        
        # Update button text
        if checked:
            self.btn_theme_toggle.setText("☀️ Light Mode")
        else:
            self.btn_theme_toggle.setText("🌙 Dark Mode")
        
        # Apply theme immediately
        from PyQt6.QtWidgets import QApplication
        from .theme import apply_theme
        app = QApplication.instance()
        if app:
            apply_theme(app, theme)

    def _on_audio_mode_changed(self, mode_text: str) -> None:
        """Update UI state based on audio mode selection."""
        is_mix = mode_text == "Mix"
        self.spin_video_gain.setEnabled(is_mix)
        self.check_ducking.setEnabled(is_mix)
        self.spin_ducking_amount.setEnabled(is_mix and self.check_ducking.isChecked())

    def _on_ducking_toggled(self, checked: bool) -> None:
        """Enable/disable ducking amount based on checkbox."""
        is_mix = self.combo_audio_mode.currentText() == "Mix"
        self.spin_ducking_amount.setEnabled(is_mix and checked)

    def _toggle_advanced_settings(self, checked: bool) -> None:
        """Toggle visibility of advanced settings."""
        self.advanced_container.setVisible(checked)
        if checked:
            self.btn_advanced.setText("⚙️ Hide Advanced Settings")
        else:
            self.btn_advanced.setText("⚙️ Show Advanced Settings")
        # Note: No adjustSize() - dialog has fixed size with scroll area

    def _load_settings(self) -> None:
        """Load current settings from QSettings."""
        # Appearance
        is_dark = self.settings.value("appearance/theme", "light", type=str) == "dark"
        self.btn_theme_toggle.setChecked(is_dark)
        # Set initial button text (without triggering the signal)
        if is_dark:
            self.btn_theme_toggle.setText("☀️ Light Mode")
        else:
            self.btn_theme_toggle.setText("🌙 Dark Mode")
        
        # Output
        self.combo_quality.setCurrentText(
            self.settings.value("output/quality", "1080p", type=str)
        )
        
        # Diarization
        mode_str = self.settings.value("diarization/mode", DiarizationMode.HYBRID.value, type=str)
        index = self.combo_diarization_mode.findData(mode_str)
        if index >= 0:
            self.combo_diarization_mode.setCurrentIndex(index)
        
        # Switching Quality (default to Balanced for backward compatibility)
        strategy_str = self.settings.value(
            "switching/strategy", SwitchingStrategy.BALANCED_LIPS_ENERGY.value, type=str
        )
        strategy_index = self.combo_switching_quality.findData(strategy_str)
        if strategy_index >= 0:
            self.combo_switching_quality.setCurrentIndex(strategy_index)
        
        # Decision engine
        self.spin_min_switch.setValue(
            self.settings.value("decision_engine/min_switch_interval_ms", 1500, type=int)
        )
        self.spin_min_speech.setValue(
            self.settings.value("decision_engine/min_speech_ms", 600, type=int)
        )
        self.spin_bg_short_remark.setValue(
            self.settings.value("decision_engine/bg_short_remark_ms", 500, type=int)
        )

        # Audio mix
        audio_mode = self.settings.value("audio_mix/mode", "Replace", type=str)
        self.combo_audio_mode.setCurrentText(audio_mode)
        self.spin_video_gain.setValue(
            self.settings.value("audio_mix/video_gain_db", 0.0, type=float)
        )
        self.spin_external_gain.setValue(
            self.settings.value("audio_mix/external_gain_db", 0.0, type=float)
        )
        self.check_ducking.setChecked(
            self.settings.value("audio_mix/ducking_enabled", False, type=bool)
        )
        self.spin_ducking_amount.setValue(
            self.settings.value("audio_mix/ducking_amount_db", -12.0, type=float)
        )
        
        # QA Overlay
        self.check_qa_overlay.setChecked(
            self.settings.value("qa_overlay/enabled", False, type=bool)
        )

        # Apply initial UI state
        self._on_audio_mode_changed(audio_mode)

    def _save_and_accept(self) -> None:
        """Save settings to QSettings and accept dialog."""
        # Output
        self.settings.setValue("output/quality", self.combo_quality.currentText())
        
        # Diarization
        self.settings.setValue("diarization/mode", self.combo_diarization_mode.currentData())
        
        # Switching Quality
        selected_strategy = self.combo_switching_quality.currentData()
        self.settings.setValue("switching/strategy", selected_strategy)
        logger.info("Switching strategy saved: %s", selected_strategy)
        
        # Decision engine
        self.settings.setValue(
            "decision_engine/min_switch_interval_ms", self.spin_min_switch.value()
        )
        self.settings.setValue(
            "decision_engine/min_speech_ms", self.spin_min_speech.value()
        )
        self.settings.setValue(
            "decision_engine/bg_short_remark_ms", self.spin_bg_short_remark.value()
        )

        # Audio mix
        self.settings.setValue("audio_mix/mode", self.combo_audio_mode.currentText())
        self.settings.setValue("audio_mix/video_gain_db", self.spin_video_gain.value())
        self.settings.setValue("audio_mix/external_gain_db", self.spin_external_gain.value())
        self.settings.setValue("audio_mix/ducking_enabled", self.check_ducking.isChecked())
        self.settings.setValue("audio_mix/ducking_amount_db", self.spin_ducking_amount.value())

        # QA Overlay
        self.settings.setValue("qa_overlay/enabled", self.check_qa_overlay.isChecked())

        self.accept()

    def _on_export_debug_clicked(self) -> None:
        """Trigger debug package export."""
        try:
            last_dir = self.settings.value("last_export_dir", os.path.expanduser("~"))
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Debug Package", os.path.join(last_dir, "multicam_debug.zip"),
                "Zip Files (*.zip)"
            )
            if not path:
                return

            self.settings.setValue("last_export_dir", os.path.dirname(path))
            success, message, warnings = export_debug_package(path)
            
            if success:
                warning_text = f" ({len(warnings)} warnings)" if warnings else ""
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Debug package exported to:\n{path}\n{warning_text}"
                )
            else:
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Failed to export: {message}"
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Unexpected error: {e}"
            )

    def get_audio_mix_settings(self) -> AudioMixSettings:
        """Return current audio mix settings from the dialog."""
        mode_text = self.combo_audio_mode.currentText()
        mode = AudioMixMode.MIX if mode_text == "Mix" else AudioMixMode.REPLACE
        return AudioMixSettings(
            mode=mode,
            video_gain_db=self.spin_video_gain.value(),
            external_gain_db=self.spin_external_gain.value(),
            ducking_enabled=self.check_ducking.isChecked(),
            ducking_amount_db=self.spin_ducking_amount.value(),
        ).clamp_gains()


def get_audio_mix_settings() -> AudioMixSettings:
    """Load audio mix settings from QSettings (standalone helper)."""
    settings = QSettings("MultiCamEditor", "MultiCamEditor")
    mode_text = settings.value("audio_mix/mode", "Replace", type=str)
    mode = AudioMixMode.MIX if mode_text == "Mix" else AudioMixMode.REPLACE
    return AudioMixSettings(
        mode=mode,
        video_gain_db=settings.value("audio_mix/video_gain_db", 0.0, type=float),
        external_gain_db=settings.value("audio_mix/external_gain_db", 0.0, type=float),
        ducking_enabled=settings.value("audio_mix/ducking_enabled", False, type=bool),
        ducking_amount_db=settings.value("audio_mix/ducking_amount_db", -12.0, type=float),
    ).clamp_gains()


def get_diarization_mode() -> DiarizationMode:
    """Load diarization mode from QSettings (standalone helper)."""
    settings = QSettings("MultiCamEditor", "MultiCamEditor")
    mode_str = settings.value("diarization/mode", DiarizationMode.HYBRID.value, type=str)
    try:
        return DiarizationMode(mode_str)
    except ValueError:
        return DiarizationMode.HYBRID


def get_qa_overlay_enabled() -> bool:
    """Load QA overlay enabled flag from QSettings (standalone helper).

    Returns:
        True if QA overlay is enabled, False otherwise (default: False).
    """
    settings = QSettings("MultiCamEditor", "MultiCamEditor")
    return settings.value("qa_overlay/enabled", False, type=bool)


def get_switching_strategy() -> SwitchingStrategy:
    """Load switching strategy from QSettings (standalone helper).
    
    Returns:
        SwitchingStrategy enum value. Defaults to BALANCED_LIPS_ENERGY for
        backward compatibility with existing installations.
    """
    settings = QSettings("MultiCamEditor", "MultiCamEditor")
    strategy_str = settings.value(
        "switching/strategy", SwitchingStrategy.BALANCED_LIPS_ENERGY.value, type=str
    )
    try:
        strategy = SwitchingStrategy(strategy_str)
        logger.info("Loaded switching strategy from settings: %s", strategy.value)
        return strategy
    except ValueError:
        logger.warning(
            "Unknown switching strategy '%s', using default: %s",
            strategy_str, DEFAULT_STRATEGY.value
        )
        return DEFAULT_STRATEGY
