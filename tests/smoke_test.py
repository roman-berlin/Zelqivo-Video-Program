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

from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MultiCamEditor")

    # NOTE: Do NOT call AA_UseHighDpiPixmaps / AA_EnableHighDpiScaling on Qt6
    # They were removed; defaults are already enabled.

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())