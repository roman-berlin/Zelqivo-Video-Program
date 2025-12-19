"""Settings dialog for configuring application behavior."""

from __future__ import annotations

from PyQt6.QtCore import QSettings
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
)

from multicam_editor.core.project import AudioMixMode, AudioMixSettings


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

        # Decision Engine Settings Group
        engine_group = QGroupBox("Decision Engine")
        engine_layout = QFormLayout()

        self.spin_min_switch = QSpinBox()
        self.spin_min_switch.setRange(100, 10000)
        self.spin_min_switch.setSingleStep(100)
        self.spin_min_switch.setSuffix(" ms")
        engine_layout.addRow("Min Switch Interval:", self.spin_min_switch)

        self.spin_min_speech = QSpinBox()
        self.spin_min_speech.setRange(100, 5000)
        self.spin_min_speech.setSingleStep(50)
        self.spin_min_speech.setSuffix(" ms")
        engine_layout.addRow("Min Speech Duration:", self.spin_min_speech)

        self.spin_bg_short_remark = QSpinBox()
        self.spin_bg_short_remark.setRange(50, 2000)
        self.spin_bg_short_remark.setSingleStep(50)
        self.spin_bg_short_remark.setSuffix(" ms")
        engine_layout.addRow("Ignore Short Remarks Below:", self.spin_bg_short_remark)

        engine_group.setLayout(engine_layout)
        layout.addWidget(engine_group)

        # Output Settings Group
        output_group = QGroupBox("Output")
        output_layout = QFormLayout()

        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["1080p", "720p", "480p"])
        output_layout.addRow("Output Quality:", self.combo_quality)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Diarization Settings Group
        diarization_group = QGroupBox("Diarization")
        diarization_layout = QFormLayout()

        self.combo_diarization = QComboBox()
        self.combo_diarization.addItems(["mock", "pyannote", "whisper"])
        diarization_layout.addRow("Backend:", self.combo_diarization)

        diarization_group.setLayout(diarization_layout)
        layout.addWidget(diarization_group)

        # Audio Mix Settings Group
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
        layout.addWidget(audio_group)

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
        self.combo_diarization.setCurrentText(
            self.settings.value("diarization/backend", "mock", type=str)
        )

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
        self.settings.setValue("diarization/backend", self.combo_diarization.currentText())

        # Audio mix settings
        self.settings.setValue("audio_mix/mode", self.combo_audio_mode.currentText())
        self.settings.setValue("audio_mix/video_gain_db", self.spin_video_gain.value())
        self.settings.setValue("audio_mix/external_gain_db", self.spin_external_gain.value())
        self.settings.setValue("audio_mix/ducking_enabled", self.check_ducking.isChecked())
        self.settings.setValue("audio_mix/ducking_amount_db", self.spin_ducking_amount.value())

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
