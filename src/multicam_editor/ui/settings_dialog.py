"""Settings dialog for configuring application behavior."""

from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QComboBox,
    QVBoxLayout,
    QGroupBox,
)


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

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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

        self.accept()
