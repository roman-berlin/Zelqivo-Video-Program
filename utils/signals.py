"""Custom PyQt signals for processing tasks."""

from PyQt6.QtCore import QObject, pyqtSignal


class ProcessingSignals(QObject):
    """Signals emitted during the processing pipeline."""

    progress: pyqtSignal = pyqtSignal(int)
    finished: pyqtSignal = pyqtSignal(str)
    error: pyqtSignal = pyqtSignal(str)

