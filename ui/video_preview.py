"""Video preview widget with playback controls using QMediaPlayer."""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSlider,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget


class VideoPreviewWidget(QWidget):
    """
    A widget that previews a video with basic playback controls.

    This widget embeds a ``QVideoWidget`` for rendering video frames and
    a ``QMediaPlayer`` for media playback. It also provides play, pause
    buttons and a horizontal slider for seeking within the loaded video.
    """

    def __init__(self) -> None:
        super().__init__()
        # Video output widget
        self.video_widget = QVideoWidget()
        # Media player configuration with audio output
        self.audio_output = QAudioOutput()
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        # Controls: play and pause buttons
        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        # Slider to represent playback position
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)

        # Layout setup
        layout = QVBoxLayout(self)
        layout.addWidget(self.video_widget)
        layout.addWidget(self.position_slider)
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.play_button)
        controls_layout.addWidget(self.pause_button)
        layout.addLayout(controls_layout)

        # Connect controls to player actions
        self.play_button.clicked.connect(self.media_player.play)
        self.pause_button.clicked.connect(self.media_player.pause)
        self.position_slider.sliderMoved.connect(self.set_position)

        # Update slider range and value based on media duration/position
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)

        # Provide a default message when no video is loaded
        self._placeholder_label = QLabel("No video loaded.")
        self._placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._placeholder_label)
        # Initially show placeholder and hide video and controls
        self.video_widget.hide()
        self.position_slider.hide()
        self.play_button.hide()
        self.pause_button.hide()
        self._placeholder_label.show()

    def load_video(self, file_path: str) -> None:
        """
        Load a video file into the preview widget.

        Parameters
        ----------
        file_path : str
            The path to the video file to load. If the path is empty or
            invalid, the method does nothing.
        """
        if not file_path:
            # If no file is provided, show placeholder text
            self.media_player.stop()
            self.video_widget.hide()
            self.position_slider.hide()
            self.play_button.hide()
            self.pause_button.hide()
            self._placeholder_label.setText("No video loaded.")
            self._placeholder_label.show()
            return

        # Convert local file path to QUrl and set as source
        url = QUrl.fromLocalFile(file_path)
        self.media_player.setSource(url)
        # Show video and controls while hiding placeholder
        self.video_widget.show()
        self.position_slider.show()
        self.play_button.show()
        self.pause_button.show()
        self._placeholder_label.hide()

    def _on_position_changed(self, position: int) -> None:
        """
        Internal slot to update the slider when the playback position changes.

        Parameters
        ----------
        position : int
            Current position of playback in milliseconds.
        """
        self.position_slider.setValue(position)

    def _on_duration_changed(self, duration: int) -> None:
        """
        Internal slot to update the slider's range when the media duration changes.

        Parameters
        ----------
        duration : int
            The total duration of the loaded media in milliseconds.
        """
        self.position_slider.setRange(0, duration)

    def set_position(self, position: int) -> None:
        """
        Seek to the specified playback position when the user moves the slider.

        Parameters
        ----------
        position : int
            The desired position in milliseconds.
        """
        self.media_player.setPosition(position)