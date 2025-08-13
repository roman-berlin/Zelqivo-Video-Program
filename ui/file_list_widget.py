"""Custom widget for managing uploaded video and audio files."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

from utils.file_utils import is_supported_audio_file, is_supported_video_file


class FileListWidget(QListWidget):
    """Drag-and-drop enabled list of media paths."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(self.SelectionMode.SingleSelection)

    # --- drag & drop

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            if is_supported_video_file(path) or is_supported_audio_file(path):
                self.addItem(QListWidgetItem(path))
        event.acceptProposedAction()

    def add_path(self, path: str) -> None:
        if is_supported_video_file(path) or is_supported_audio_file(path):
            self.addItem(QListWidgetItem(path))

    def get_file_paths(self) -> list[str]:
        return [self.item(i).text() for i in range(self.count())]