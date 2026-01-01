"""Processing options widget for multicam editor.

Encapsulates external audio, speaker mapping, and output folder options.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class ProcessingOptionsWidget(QGroupBox):
    """Widget containing all processing options.

    Signals:
        externalAudioChanged: Emitted when external audio enabled/path changes
        outputFolderChanged: Emitted when output folder changes
    """

    externalAudioChanged = pyqtSignal(bool, str)  # enabled, path
    outputFolderChanged = pyqtSignal(str)  # folder path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Processing Options", parent)
        self.setObjectName("groupProcessingOptions")
        self.settings = QSettings("MultiCamEditor", "MultiCamEditor")

        self._external_audio_path: str | None = None
        self._output_folder: str | None = None
        self._camera_combos: dict[int, QComboBox] = {}
        self._available_speakers: list[str] = ["Auto (best effort)"]
        self._mapping_expanded: bool = False

        self._init_ui()
        self._load_settings()

    def _init_ui(self) -> None:
        """Initialize the UI components."""
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(1, 1)

        row = 0

        # External Audio checkbox
        self.chk_external_audio = QCheckBox("Use external audio")
        self.chk_external_audio.setObjectName("chkExternalAudio")
        self.chk_external_audio.setToolTip("Replace camera audio with external audio file")
        self.chk_external_audio.toggled.connect(self._on_external_audio_toggled)
        layout.addWidget(self.chk_external_audio, row, 0, 1, 3)
        row += 1

        # Helper text
        self.lbl_external_audio_hint = QLabel("External audio replaces camera audio in final video")
        self.lbl_external_audio_hint.setObjectName("lblExternalAudioHint")
        self.lbl_external_audio_hint.setStyleSheet("color: gray; font-size: 9pt;")
        self.lbl_external_audio_hint.setContentsMargins(20, 0, 0, 0)
        layout.addWidget(self.lbl_external_audio_hint, row, 0, 1, 3)
        row += 1

        # External audio file chooser
        self.btn_add_external_audio = QPushButton("Choose Audio…")
        self.btn_add_external_audio.setObjectName("btnAddExternalAudio")
        self.btn_add_external_audio.setToolTip("Select external audio file (WAV, MP3, AAC, M4A)")
        self.btn_add_external_audio.setFixedWidth(120)
        self.btn_add_external_audio.clicked.connect(self._on_add_external_audio)
        layout.addWidget(self.btn_add_external_audio, row, 0)

        self.lbl_external_audio = QLabel("No audio selected")
        self.lbl_external_audio.setObjectName("lblExternalAudio")
        self.lbl_external_audio.setStyleSheet("color: gray;")
        layout.addWidget(self.lbl_external_audio, row, 1, 1, 2)
        row += 1

        # Speaker mapping row
        lbl_mapping = QLabel("Speaker mapping")
        lbl_mapping.setObjectName("lblMappingLabel")
        layout.addWidget(lbl_mapping, row, 0)

        self.lbl_mapping_summary = QLabel("Auto")
        self.lbl_mapping_summary.setObjectName("lblMappingSummary")
        layout.addWidget(self.lbl_mapping_summary, row, 1)

        self.btn_edit_mapping = QPushButton("Edit…")
        self.btn_edit_mapping.setObjectName("btnEditMapping")
        self.btn_edit_mapping.setToolTip("Choose which speaker each camera should follow")
        self.btn_edit_mapping.setFixedWidth(80)
        self.btn_edit_mapping.clicked.connect(self._toggle_mapping_expanded)
        layout.addWidget(self.btn_edit_mapping, row, 2)
        row += 1

        # Mapping expanded section
        self.mapping_container = QWidget()
        self.mapping_layout = QVBoxLayout(self.mapping_container)
        self.mapping_layout.setContentsMargins(20, 4, 0, 4)
        self.mapping_layout.setSpacing(4)
        self.mapping_container.setVisible(False)
        layout.addWidget(self.mapping_container, row, 0, 1, 3)
        row += 1

        self.lbl_no_cameras = QLabel("(Add videos to configure mapping)")
        self.lbl_no_cameras.setObjectName("lblNoCameras")
        self.lbl_no_cameras.setStyleSheet("color: gray; font-style: italic;")
        self.mapping_layout.addWidget(self.lbl_no_cameras)

        # Warning label
        self.lbl_mapping_warning = QLabel("")
        self.lbl_mapping_warning.setObjectName("lblMappingWarning")
        self.lbl_mapping_warning.setStyleSheet("color: orange;")
        self.lbl_mapping_warning.setWordWrap(True)
        self.lbl_mapping_warning.setVisible(False)
        layout.addWidget(self.lbl_mapping_warning, row, 0, 1, 3)
        row += 1

        # Output folder row
        lbl_output = QLabel("Output folder")
        lbl_output.setObjectName("lblOutputFolder")
        layout.addWidget(lbl_output, row, 0)

        self.lbl_output_folder = QLabel("Downloads")
        self.lbl_output_folder.setObjectName("lblOutputFolderPath")
        layout.addWidget(self.lbl_output_folder, row, 1)

        self.btn_choose_output_folder = QPushButton("Choose…")
        self.btn_choose_output_folder.setObjectName("btnChooseOutputFolder")
        self.btn_choose_output_folder.setToolTip("Select output folder for processed video")
        self.btn_choose_output_folder.setFixedWidth(80)
        self.btn_choose_output_folder.clicked.connect(self._on_choose_output_folder)
        layout.addWidget(self.btn_choose_output_folder, row, 2)

    def _load_settings(self) -> None:
        """Load saved settings."""
        # Clear any persisted external audio settings - start fresh each session
        self.settings.remove("processing/use_external_audio")
        self.settings.remove("processing/external_audio_path")

        self.chk_external_audio.setChecked(False)
        self._external_audio_path = None
        self.lbl_external_audio.setText("No audio selected")
        self.lbl_external_audio.setStyleSheet("color: gray;")

        self._output_folder = self.settings.value("output/folder", None)
        if self._output_folder:
            self.lbl_output_folder.setText(os.path.basename(self._output_folder))
            self.lbl_output_folder.setToolTip(self._output_folder)

        self._update_external_audio_ui()

    def _on_external_audio_toggled(self, checked: bool) -> None:
        """Handle external audio checkbox toggle."""
        self.settings.setValue("processing/use_external_audio", checked)
        self._update_external_audio_ui()
        self.externalAudioChanged.emit(checked, self._external_audio_path or "")
        logger.debug("External audio: %s", "enabled" if checked else "disabled")

    def _update_external_audio_ui(self) -> None:
        """Update external audio controls state."""
        enabled = self.chk_external_audio.isChecked()
        self.btn_add_external_audio.setEnabled(enabled)
        self.lbl_external_audio.setEnabled(enabled)

    def _on_add_external_audio(self) -> None:
        """Open file dialog to select external audio."""
        last_dir = self.settings.value("last_audio_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select External Audio", last_dir,
            "Audio Files (*.wav *.mp3 *.aac *.m4a);;All Files (*.*)"
        )
        if not path or not os.path.isfile(path):
            return

        self._external_audio_path = path
        self.settings.setValue("processing/external_audio_path", path)
        self.settings.setValue("last_audio_dir", os.path.dirname(path))
        self.lbl_external_audio.setText(os.path.basename(path))
        self.lbl_external_audio.setStyleSheet("")
        self.externalAudioChanged.emit(True, path)
        logger.info("External audio selected: %s", path)

    def _on_choose_output_folder(self) -> None:
        """Open folder dialog to select output folder."""
        start_dir = self._output_folder or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", start_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if not folder:
            return

        self._output_folder = folder
        self.settings.setValue("output/folder", folder)
        self.lbl_output_folder.setText(os.path.basename(folder))
        self.lbl_output_folder.setToolTip(folder)
        self.outputFolderChanged.emit(folder)
        logger.info("Output folder selected: %s", folder)

    def _toggle_mapping_expanded(self) -> None:
        """Toggle speaker mapping section visibility."""
        self._mapping_expanded = not self._mapping_expanded
        self.mapping_container.setVisible(self._mapping_expanded)
        self.btn_edit_mapping.setText("Hide" if self._mapping_expanded else "Edit…")
        if self._mapping_expanded:
            self._check_mapping_warnings()
        else:
            self.lbl_mapping_warning.setVisible(False)

    def refresh_camera_mapping(self, clips: list) -> None:
        """Rebuild camera mapping combos based on clips.

        Args:
            clips: List of clip objects with .path attribute
        """
        # Clear old combos
        for combo in self._camera_combos.values():
            combo.setParent(None)
            combo.deleteLater()
        self._camera_combos.clear()

        if not clips:
            self.lbl_no_cameras.setVisible(True)
            self.lbl_mapping_warning.setVisible(False)
            return

        self.lbl_no_cameras.setVisible(False)

        # Update available speakers
        num_cameras = len(clips)
        self._available_speakers = ["Auto (best effort)"]
        num_speakers = max(2, num_cameras)
        for s in range(num_speakers):
            self._available_speakers.append(f"Speaker {s + 1}")

        # Create combo for each camera
        for i, clip in enumerate(clips):
            row_widget = QWidget()
            row_lay = QHBoxLayout(row_widget)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(4)

            lbl = QLabel(f"Camera {i + 1}:")
            lbl.setMinimumWidth(70)
            row_lay.addWidget(lbl)

            combo = QComboBox()
            combo.setObjectName(f"comboCamera{i}")
            combo.addItems(self._available_speakers)
            saved = self.settings.value(f"processing/camera_{i}_speaker", "Auto (best effort)")
            idx = combo.findText(saved)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentTextChanged.connect(
                lambda text, cam=i: self._on_camera_mapping_changed(cam, text)
            )
            row_lay.addWidget(combo, 1)

            hint = QLabel(os.path.basename(clip.path)[:20])
            hint.setStyleSheet("color: gray; font-size: 10px;")
            row_lay.addWidget(hint)

            self._camera_combos[i] = combo
            self.mapping_layout.addWidget(row_widget)

        self._check_mapping_warnings()

    def _on_camera_mapping_changed(self, camera_index: int, speaker: str) -> None:
        """Save camera-to-speaker mapping."""
        self.settings.setValue(f"processing/camera_{camera_index}_speaker", speaker)
        logger.debug("Camera %d mapped to %s", camera_index, speaker)
        self._check_mapping_warnings()

    def _check_mapping_warnings(self) -> None:
        """Show warning if needed."""
        if not self._mapping_expanded:
            self.lbl_mapping_warning.setVisible(False)
            return
        if not self._camera_combos:
            self.lbl_mapping_warning.setVisible(False)
            return

        all_auto = all(
            combo.currentText() == "Auto (best effort)"
            for combo in self._camera_combos.values()
        )
        if all_auto and len(self._camera_combos) > 1:
            self.lbl_mapping_warning.setText(
                "Tip: For best results, map cameras to specific speakers."
            )
            self.lbl_mapping_warning.setVisible(True)
        else:
            self.lbl_mapping_warning.setVisible(False)

    # --- Public API ---

    def use_external_audio(self) -> bool:
        """Return whether external audio is enabled."""
        return self.chk_external_audio.isChecked()

    def external_audio_path(self) -> str | None:
        """Return external audio file path if valid."""
        if self.use_external_audio() and self._external_audio_path:
            if os.path.isfile(self._external_audio_path):
                return self._external_audio_path
        return None

    def output_folder(self) -> str | None:
        """Return output folder path."""
        return self._output_folder

    def camera_speaker_mapping(self) -> dict[int, str]:
        """Return current camera-to-speaker mapping."""
        return {
            cam: combo.currentText()
            for cam, combo in self._camera_combos.items()
        }
