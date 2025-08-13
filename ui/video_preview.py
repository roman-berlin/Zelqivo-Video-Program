# file: ui/video_preview.py
from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel


class VideoPreview(QWidget):
    """Preview shell with safe audio guard (Prompt 1)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel("Select a file to preview", self)
        self._video = QVideoWidget(self)
        self._player = QMediaPlayer(self)

        # Audio may be missing/unavailable on some systems; guard it.
        self._audio = None
        try:
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
        except Exception:
            self._audio = None  # keep preview working (video only)

        self._player.setVideoOutput(self._video)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._label)
        lay.addWidget(self._video, 1)

    def set_source(self, path: str) -> None:
        self._label.setText(Path(path).name)
        try:
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.play()
        except Exception:
            # Keep UI responsive; in Prompt 2 we'll add proper error banners/fallbacks.
            pass