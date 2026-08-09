"""Custom Qt signals for processing tasks."""

from PySide6.QtCore import QObject, Signal


class ProcessingSignals(QObject):
    """Signals emitted during the processing pipeline."""

    # Define the signals as class attributes. Type annotations are omitted
    # so that static analysis tools correctly recognise the Qt signal
    # objects and their ``connect`` methods. Each signal takes a single
    # argument corresponding to the type of value it emits.
    progress = Signal(int)  # overall percent 0-100
    finished = Signal(str)  # output path
    error = Signal(str)     # error message
    status = Signal(str)    # status message (e.g. "Running preflight checks...")
    stage = Signal(str, int, str)  # stage_name, stage_percent, message
