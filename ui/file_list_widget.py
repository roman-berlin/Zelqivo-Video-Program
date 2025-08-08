"""Custom widget for managing uploaded video and audio files.

This widget accepts drag‑and‑drop of supported video (mp4, avi, mov)
and audio (wav, mp3) files. It displays them in a simple list and
allows removal.
"""

from PyQt6.QtWidgets import QListWidget, QListWidgetItem

from ..utils.file_utils import is_supported_video_file, is_supported_audio_file


class FileListWidget(QListWidget):
    """A QListWidget subclass that supports drag‑and‑drop for files."""

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(self.SelectionMode.SingleSelection)

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

    def get_file_paths(self):
        """Return a list of file paths currently in the list widget."""
        return [self.item(i).text() for i in range(self.count())]
