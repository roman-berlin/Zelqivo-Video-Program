"""Settings dialog for configuring application behavior."""

from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QComboBox,
    QVBoxLayout,
    QGroupBox,
)

from multicam_editor.core.project import AudioMixMode, AudioMixSettings
from multicam_editor.logic.active_speaker import DiarizationMode
from multicam_editor.utils.backends import check_backends


class SettingsDialog(QDialog):
    """Dialog for editing application settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(400, 300)
        self.settings = QSettings("MultiCamEditor", "MultiCamEditor")

        self._init_ui()
        self._load_settings()

    def _init_ui(self) -> None:
        """Initialize the UI components."""
        layout = QVBoxLayout(self)

        # 1. Basic Settings (Always Visible)
        
        # Diarization Settings
        diarization_group = QGroupBox("Diarization")
        diarization_layout = QFormLayout()

        self.combo_diarization = QComboBox()
        # Add items with display names and store enum values as user data
        self.combo_diarization.addItem("Hybrid (Recommended)", DiarizationMode.HYBRID.value)
        self.combo_diarization.addItem("Lips Only (Visual)", DiarizationMode.LIPS.value)
        self.combo_diarization.addItem("Off (single camera)", DiarizationMode.OFF.value)
        self.combo_diarization.setToolTip(
            "Hybrid: Audio + Visual detection - fastest and most accurate (recommended)\n"
            "Lips Only: Pure visual detection - slower but works without audio\n"
            "Off: Single camera output, no switching"
        )
        diarization_layout.addRow("Backend:", self.combo_diarization)

        # Status label showing if pyannote is available
        self.label_diarization_status = QLabel()
        self._update_diarization_status()
        diarization_layout.addRow("Status:", self.label_diarization_status)

        diarization_group.setLayout(diarization_layout)
        layout.addWidget(diarization_group)

        # Output Settings
        output_group = QGroupBox("Output")
        output_layout = QFormLayout()

        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["1080p", "720p", "480p"])
        output_layout.addRow("Output Quality:", self.combo_quality)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # 2. Advanced Settings Toggle
        self.check_advanced = QCheckBox("Show Advanced Settings")
        self.check_advanced.toggled.connect(self._toggle_advanced_settings)
        layout.addWidget(self.check_advanced)

        # 3. Advanced Settings Container
        self.advanced_container = QGroupBox("Advanced Configuration")
        self.advanced_container.setVisible(False)
        advanced_layout = QVBoxLayout()
        
        # Audio Mix Settings
        audio_group = QGroupBox("Audio Mix (External Audio)")
        audio_layout = QFormLayout()

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

        self.advanced_container.setLayout(advanced_layout)
        layout.addWidget(self.advanced_container)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_audio_mode_changed(self, mode_text: str) -> None:
        """Update UI state based on audio mode selection."""
        is_mix = mode_text == "Mix"
        # Video gain only matters in Mix mode
        self.spin_video_gain.setEnabled(is_mix)
        # Ducking only available in Mix mode
        self.check_ducking.setEnabled(is_mix)
        self.spin_ducking_amount.setEnabled(is_mix and self.check_ducking.isChecked())

    def _on_ducking_toggled(self, checked: bool) -> None:
        """Enable/disable ducking amount based on checkbox."""
        is_mix = self.combo_audio_mode.currentText() == "Mix"
        self.spin_ducking_amount.setEnabled(is_mix and checked)

    def _update_diarization_status(self) -> None:
        """Update the diarization status label with actionable guidance."""
        # Use fast check to avoid freezing UI
        from multicam_editor.logic.active_speaker import PyannoteBackend
        available, error = PyannoteBackend.check_install()

        if available:
            self.label_diarization_status.setText("OK pyannote.audio ready")
            self.label_diarization_status.setStyleSheet("color: green;")
            self.label_diarization_status.setToolTip("")
        else:
            # Parse error and provide actionable message
            short_msg, tooltip = self._parse_diarization_error(error or "Unknown error")
            self.label_diarization_status.setText(f"[!] {short_msg}")
            self.label_diarization_status.setStyleSheet("color: orange;")
            self.label_diarization_status.setToolTip(tooltip)

    def _toggle_advanced_settings(self, checked: bool) -> None:
        """Toggle visibility of advanced settings."""
        self.advanced_container.setVisible(checked)
        # Resize dialog to fit content
        self.adjustSize()

    @staticmethod
    def _parse_diarization_error(error: str) -> tuple[str, str]:
        """Parse pyannote error and return (short_msg, tooltip)."""
        error_lower = error.lower()

        if "401" in error or "unauthorized" in error_lower:
            return (
                "Auth required → hf auth login",
                "Run 'hf auth login' in terminal with your HuggingFace token"
            )
        if "gated" in error_lower or "access" in error_lower:
            return (
                "Accept model → hf.co/pyannote",
                "Visit https://hf.co/pyannote/speaker-diarization-3.1 and click 'Agree'"
            )
        if "token" in error_lower:
            return (
                "Missing token → hf auth login",
                "Create token at hf.co/settings/tokens, then run 'hf auth login'"
            )
        if "not installed" in error_lower:
            return (
                "pyannote not installed",
                "Run: pip install pyannote.audio"
            )
        if "could not load" in error_lower or "could not download" in error_lower:
            return (
                "Model unavailable → check auth",
                "Run 'hf auth login' and accept model at hf.co/pyannote/speaker-diarization-3.1"
            )
        # Fallback: truncate error
        return (error[:40] + "..." if len(error) > 40 else error, error)

    def _load_settings(self) -> None:
        """Load current settings from QSettings."""
        self.spin_min_switch.setValue(
            self.settings.value("decision_engine/min_switch_interval_ms", 1500, type=int)
        )
        self.spin_min_speech.setValue(
            self.settings.value("decision_engine/min_speech_ms", 600, type=int)
        )
        self.spin_bg_short_remark.setValue(
            self.settings.value("decision_engine/bg_short_remark_ms", 500, type=int)
        )
        self.combo_quality.setCurrentText(
            self.settings.value("output/quality", "1080p", type=str)
        )
        # Diarization: find index by stored value
        diarization_value = self.settings.value(
            "diarization/mode", DiarizationMode.HYBRID.value, type=str
        )
        for i in range(self.combo_diarization.count()):
            if self.combo_diarization.itemData(i) == diarization_value:
                self.combo_diarization.setCurrentIndex(i)
                break

        # Audio mix settings
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
        # QA Overlay setting (Prompt 5)
        self.check_qa_overlay.setChecked(
            self.settings.value("qa_overlay/enabled", False, type=bool)
        )

        # Apply initial UI state
        self._on_audio_mode_changed(audio_mode)

    def _save_and_accept(self) -> None:
        """Save settings to QSettings and accept dialog."""
        self.settings.setValue(
            "decision_engine/min_switch_interval_ms", self.spin_min_switch.value()
        )
        self.settings.setValue(
            "decision_engine/min_speech_ms", self.spin_min_speech.value()
        )
        self.settings.setValue(
            "decision_engine/bg_short_remark_ms", self.spin_bg_short_remark.value()
        )
        self.settings.setValue("output/quality", self.combo_quality.currentText())
        # Save the enum value (from itemData), not the display text
        self.settings.setValue(
            "diarization/mode", self.combo_diarization.currentData()
        )

        # Audio mix settings
        self.settings.setValue("audio_mix/mode", self.combo_audio_mode.currentText())
        self.settings.setValue("audio_mix/video_gain_db", self.spin_video_gain.value())
        self.settings.setValue("audio_mix/external_gain_db", self.spin_external_gain.value())
        self.settings.setValue("audio_mix/ducking_enabled", self.check_ducking.isChecked())
        self.settings.setValue("audio_mix/ducking_amount_db", self.spin_ducking_amount.value())

        # QA Overlay setting (Prompt 5)
        self.settings.setValue("qa_overlay/enabled", self.check_qa_overlay.isChecked())

        self.accept()

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
    mode_value = settings.value("diarization/mode", DiarizationMode.REAL.value, type=str)
    try:
        return DiarizationMode(mode_value)
    except ValueError:
        return DiarizationMode.REAL


def get_qa_overlay_enabled() -> bool:
    """Load QA overlay enabled flag from QSettings (standalone helper).

    Returns:
        True if QA overlay is enabled, False otherwise (default: False).
    """
    settings = QSettings("MultiCamEditor", "MultiCamEditor")
    return settings.value("qa_overlay/enabled", False, type=bool)
