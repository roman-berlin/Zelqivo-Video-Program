# file: ui/utils/gui.py
from __future__ import annotations
from typing import Callable

from PySide6.QtCore import QObject, Signal, QThread, QCoreApplication, QTimer, Qt


class _GuiRunner(QObject):
    _post = Signal(object)  # emits: Callable[[], None]

    def __init__(self) -> None:
        super().__init__()
        # Connect using Qt.ConnectionType.QueuedConnection to ensure callbacks run
        # on the main GUI thread.  Qt must be imported for this constant; see import above.
        self._post.connect(self._invoke, type=Qt.ConnectionType.QueuedConnection)  # queued → GUI thread

    def _invoke(self, fn: object) -> None:
        try:
            callable_fn = fn  # keep name short
            if callable(callable_fn):
                callable_fn()  # type: ignore[misc]
        except Exception:
            # swallow to avoid crashing the event loop; log if you have a logger
            pass

    def post(self, fn: Callable[[], None]) -> None:
        """Execute fn on the GUI thread ASAP (non-blocking)."""
        app = QCoreApplication.instance()
        if app is None:
            # no app yet — schedule when event loop spins
            QTimer.singleShot(0, fn)
            return
        if QThread.currentThread() == app.thread():
            # already on GUI thread
            try:
                fn()
            except Exception:
                pass
        else:
            self._post.emit(fn)


# Singleton
_gui_runner: _GuiRunner | None = None

def gui_runner() -> _GuiRunner:
    global _gui_runner
    if _gui_runner is None:
        _gui_runner = _GuiRunner()
    return _gui_runner
