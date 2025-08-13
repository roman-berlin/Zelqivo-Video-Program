# file: ui/video_preview.py
from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel


class VideoPreview(QWidget):
    """Lightweight preview shell; full controls come in Prompt 2."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel("Select a file to preview", self)
        self._video = QVideoWidget(self)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._label)
        lay.addWidget(self._video, 1)

    def set_source(self, path: str) -> None:
        # Keep it minimal; robust fallback lands in Prompt 2
        self._label.setText(Path(path).name)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()