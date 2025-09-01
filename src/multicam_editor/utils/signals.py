"""Custom PyQt signals for processing tasks."""

from PyQt6.QtCore import QObject, pyqtSignal


class ProcessingSignals(QObject):
    """Signals emitted during the processing pipeline."""

    # Define the signals as class attributes. Type annotations are omitted
    # so that static analysis tools correctly recognise the PyQt signal
    # objects and their ``connect`` methods. Each signal takes a single
    # argument corresponding to the type of value it emits.
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

