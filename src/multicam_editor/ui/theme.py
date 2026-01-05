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
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 26px;
}
QPushButton:hover {
    background-color: #d0d0d0;
    border-color: #9e9e9e;
}
QPushButton:pressed {
    background-color: #bdbdbd;
}
QPushButton:disabled {
    background-color: #f5f5f5;
    color: #9e9e9e;
    border-color: #e0e0e0;
}
QPushButton:checked {
    background-color: #1976d2;
    color: white;
    border-color: #1565c0;
}
QPushButton#btnPlayResult {
    background-color: #4caf50;
    color: white;
    border-color: #43a047;
    font-weight: bold;
}
QPushButton#btnPlayResult:hover {
    background-color: #43a047;
}
QPushButton#btnThemeToggle {
    background-color: #e3f2fd;
    border: 1px solid #90caf9;
    min-width: 120px;
}
QPushButton#btnThemeToggle:checked {
    background-color: #1565c0;
    color: white;
    border-color: #0d47a1;
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
    border-radius: 6px;
}
QLabel {
    background-color: transparent;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #d0d0d0;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background-color: #ffffff;
}
QGroupBox#groupResult {
    border: 2px solid #4caf50;
    background-color: #e8f5e9;
}
QComboBox {
    border: 1px solid #bdbdbd;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}
QComboBox:hover {
    border-color: #9e9e9e;
}
QCheckBox {
    spacing: 6px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 3px;
}
QSpinBox, QDoubleSpinBox {
    border: 1px solid #bdbdbd;
    border-radius: 4px;
    padding: 4px;
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
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 26px;
    color: #e0e0e0;
}
QPushButton:hover {
    background-color: #4a4a4a;
    border-color: #666666;
}
QPushButton:pressed {
    background-color: #555555;
}
QPushButton:disabled {
    background-color: #2d2d2d;
    color: #666666;
    border-color: #3c3c3c;
}
QPushButton:checked {
    background-color: #1976d2;
    color: white;
    border-color: #1565c0;
}
QPushButton#btnPlayResult {
    background-color: #4caf50;
    color: white;
    border-color: #43a047;
    font-weight: bold;
}
QPushButton#btnPlayResult:hover {
    background-color: #43a047;
}
QPushButton#btnThemeToggle {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    min-width: 120px;
}
QPushButton#btnThemeToggle:checked {
    background-color: #1565c0;
    color: white;
    border-color: #0d47a1;
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
    border-radius: 6px;
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
QGroupBox {
    font-weight: bold;
    border: 1px solid #555555;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    color: #e0e0e0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background-color: #2d2d2d;
}
QGroupBox#groupResult {
    border: 2px solid #4caf50;
    background-color: #1b3d1f;
}
QComboBox {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
    color: #e0e0e0;
}
QComboBox:hover {
    border-color: #666666;
}
QComboBox QAbstractItemView {
    background-color: #3c3c3c;
    color: #e0e0e0;
    selection-background-color: #555555;
}
QCheckBox {
    spacing: 6px;
    color: #e0e0e0;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 3px;
}
QSpinBox, QDoubleSpinBox {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 4px;
    color: #e0e0e0;
}
QLineEdit {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 4px;
    color: #e0e0e0;
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
