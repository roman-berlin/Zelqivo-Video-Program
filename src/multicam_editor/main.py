# file: main.py
from __future__ import annotations
import os
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# High‑DPI env for CI/Windows
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

# Optional (Qt6+): safer DPI rounding; ignore if not available
try:
    from PyQt6.QtGui import QGuiApplication  # type: ignore
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass
except Exception:
    pass

"""Application entry point for the MultiCamEditor GUI.

This module sets up some high‑DPI defaults for Qt on supported platforms
and configures a basic logging sink before creating the Qt application.
It imports the main window from within the package and exposes a
``main()`` function so that the application can be run via
``python -m multicam_editor`` or ``python src/multicam_editor/main.py``.

"""

try:
    # Normal package-relative imports when executed via ``python -m multicam_editor``
    # or when running as a PyInstaller frozen executable
    from .logging_setup import configure_logging  # type: ignore
    from .ui.main_window import MainWindow  # type: ignore
except ImportError:
    # Fallback for running this file directly (``python src/multicam_editor/main.py``)
    # When executed as a script, __package__ is ``None`` and relative imports fail.
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle - use absolute imports from the package
        from multicam_editor.logging_setup import configure_logging  # type: ignore
        from multicam_editor.ui.main_window import MainWindow  # type: ignore
    else:
        # Running as script - add current directory to path
        import pathlib as _pathlib
        _current_dir = _pathlib.Path(__file__).resolve().parent
        if str(_current_dir) not in sys.path:
            sys.path.insert(0, str(_current_dir))
        # Attempt to import using absolute module names
        from logging_setup import configure_logging  # type: ignore
        from ui.main_window import MainWindow  # type: ignore


def main() -> int:
    """Entrypoint used by the ``if __name__ == '__main__'`` guard.

    It instantiates the QApplication, configures the application name
    and logging, constructs the main window and starts the Qt event loop.

    Returns:
        The integer exit code returned by ``QApplication.exec()``.
    """
    # Initialise logging before any other imports or UI code.
    configure_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("MultiCamEditor")

    # NOTE: Do NOT call AA_UseHighDpiPixmaps / AA_EnableHighDpiScaling on Qt6
    # They were removed; defaults are already enabled.

    win = MainWindow()
    win.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())