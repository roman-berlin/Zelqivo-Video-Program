"""Video preview widget with playback controls using QMediaPlayer."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget


class VideoPreviewWidget(QWidget):
    """Simple player for previewing a single media file."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)

        self.video_widget = QVideoWidget(self)
        self.media_player.setVideoOutput(self.video_widget)

        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop")

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)

        layout = QVBoxLayout()
        layout.addWidget(self.video_widget)
        layout.addWidget(self.position_slider)
        layout.addLayout(controls)
        self.setLayout(layout)

        # Signals
        self.play_button.clicked.connect(self.media_player.play)
        self.pause_button.clicked.connect(self.media_player.pause)
        self.stop_button.clicked.connect(self.media_player.stop)
        self.position_slider.sliderMoved.connect(self.set_position)

        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.positionChanged.connect(self._on_position_changed)

    # API

    def load(self, path: str) -> None:
        """Load a media file for preview."""
        self.media_player.setSource(QUrl.fromLocalFile(path))

    # QMediaPlayer slots

    def _on_position_changed(self, position: int) -> None:
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(position)
        self.position_slider.blockSignals(False)

    def _on_duration_changed(self, duration: int) -> None:
        self.position_slider.setRange(0, duration)

    def set_position(self, position: int) -> None:
        self.media_player.setPosition(position)