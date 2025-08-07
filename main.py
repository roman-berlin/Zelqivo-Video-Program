"""Entry point for the Active Speaker Video Merger application.

This module initialises the Qt application, configures logging and
creates the main window. It is intentionally minimal so that all
application logic and UI code lives in separate modules under the
``ui`` and ``logic`` packages. Running this file will launch the
desktop application.
"""

import sys
from PyQt6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .utils.logger import configure_logging


def main() -> None:
    """Start the Qt event loop and show the main window."""
    configure_logging()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
