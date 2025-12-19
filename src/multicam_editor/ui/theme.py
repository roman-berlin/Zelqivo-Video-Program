# file: ui/theme.py
"""Theme management and stylesheets."""

LIGHT_THEME = """
QMainWindow {
    background-color: #f5f5f5;
}
QWidget {
    background-color: #ffffff;
    color: #212121;
}
QPushButton {
    background-color: #e0e0e0;
    border: 1px solid #bdbdbd;
    border-radius: 4px;
    padding: 6px 12px;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #d0d0d0;
}
QPushButton:pressed {
    background-color: #bdbdbd;
}
QPushButton:disabled {
    background-color: #f5f5f5;
    color: #9e9e9e;
}
QPushButton:checked {
    background-color: #1976d2;
    color: white;
}
QToolBar {
    background-color: #fafafa;
    border-bottom: 1px solid #e0e0e0;
    spacing: 8px;
    padding: 4px;
}
QMenuBar {
    background-color: #fafafa;
    border-bottom: 1px solid #e0e0e0;
}
QMenuBar::item:selected {
    background-color: #e0e0e0;
}
QMenu {
    background-color: #ffffff;
    border: 1px solid #bdbdbd;
}
QMenu::item:selected {
    background-color: #e0e0e0;
}
QStatusBar {
    background-color: #fafafa;
    border-top: 1px solid #e0e0e0;
}
QListWidget {
    border: 1px solid #bdbdbd;
    border-radius: 4px;
}
QLabel {
    background-color: transparent;
}
"""

DARK_THEME = """
QMainWindow {
    background-color: #1e1e1e;
}
QWidget {
    background-color: #2d2d2d;
    color: #e0e0e0;
}
QPushButton {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 6px 12px;
    min-height: 24px;
    color: #e0e0e0;
}
QPushButton:hover {
    background-color: #4a4a4a;
}
QPushButton:pressed {
    background-color: #555555;
}
QPushButton:disabled {
    background-color: #2d2d2d;
    color: #666666;
}
QPushButton:checked {
    background-color: #1976d2;
    color: white;
}
QToolBar {
    background-color: #252525;
    border-bottom: 1px solid #3c3c3c;
    spacing: 8px;
    padding: 4px;
}
QMenuBar {
    background-color: #252525;
    border-bottom: 1px solid #3c3c3c;
    color: #e0e0e0;
}
QMenuBar::item {
    background-color: transparent;
    color: #e0e0e0;
}
QMenuBar::item:selected {
    background-color: #3c3c3c;
}
QMenu {
    background-color: #2d2d2d;
    border: 1px solid #555555;
    color: #e0e0e0;
}
QMenu::item:selected {
    background-color: #3c3c3c;
}
QStatusBar {
    background-color: #252525;
    border-top: 1px solid #3c3c3c;
    color: #e0e0e0;
}
QListWidget {
    background-color: #2d2d2d;
    border: 1px solid #555555;
    border-radius: 4px;
    color: #e0e0e0;
}
QLabel {
    background-color: transparent;
    color: #e0e0e0;
}
QGraphicsView {
    background-color: #2d2d2d;
    border: 1px solid #555555;
}
"""


def get_theme_stylesheet(theme: str) -> str:
    """Get stylesheet for the specified theme."""
    if theme == "dark":
        return DARK_THEME
    return LIGHT_THEME


def apply_theme(app, theme: str) -> None:
    """Apply theme to the application."""
    stylesheet = get_theme_stylesheet(theme)
    app.setStyleSheet(stylesheet)
