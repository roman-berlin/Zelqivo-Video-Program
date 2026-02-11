"""Custom PyQt signals for processing tasks."""

from PyQt6.QtCore import QObject, pyqtSignal


class ProcessingSignals(QObject):
    """Signals emitted during the processing pipeline."""

    # Define the signals as class attributes. Type annotations are omitted
    # so that static analysis tools correctly recognise the PyQt signal
    # objects and their ``connect`` methods. Each signal takes a single
    # argument corresponding to the type of value it emits.
    progress = pyqtSignal(int)  # overall percent 0-100
    finished = pyqtSignal(str)  # output path
    error = pyqtSignal(str)     # error message
    status = pyqtSignal(str)    # status message (e.g. "Running preflight checks...")
    stage = pyqtSignal(str, int, str)  # stage_name, stage_percent, message
