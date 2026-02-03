# file: ui/custom_title_bar.py
"""Custom title bar widget for frameless window with modern dark mode styling."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt6.QtGui import QMouseEvent


class CustomTitleBar(QWidget):
    """Modern custom title bar with minimize, maximize, and close buttons.
    
    Designed for dark mode with subtle hover effects.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._parent = parent
        self._drag_pos: QPoint | None = None
        self._is_maximized = False
        
        self.setObjectName("customTitleBar")
        self.setFixedHeight(32)
        self._init_ui()
        self._apply_styles()
    
    def _init_ui(self) -> None:
        """Initialize the title bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)
        
        # App icon/title
        self.lbl_title = QLabel("Zelqivo")
        self.lbl_title.setObjectName("lblWindowTitle")
        layout.addWidget(self.lbl_title)
        
        # Spacer
        layout.addStretch()
        
        # Window control buttons
        btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                color: #888;
                font-size: 14px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #fff;
            }
        """
        
        close_btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                color: #888;
                font-size: 14px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background: #e81123;
                color: #fff;
            }
        """
        
        # Minimize button
        self.btn_minimize = QPushButton("─")
        self.btn_minimize.setObjectName("btnMinimize")
        self.btn_minimize.setFixedSize(46, 32)
        self.btn_minimize.setStyleSheet(btn_style)
        self.btn_minimize.clicked.connect(self._on_minimize)
        layout.addWidget(self.btn_minimize)
        
        # Maximize/Restore button
        self.btn_maximize = QPushButton("□")
        self.btn_maximize.setObjectName("btnMaximize")
        self.btn_maximize.setFixedSize(46, 32)
        self.btn_maximize.setStyleSheet(btn_style)
        self.btn_maximize.clicked.connect(self._on_maximize)
        layout.addWidget(self.btn_maximize)
        
        # Close button - red on hover
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("btnClose")
        self.btn_close.setFixedSize(46, 32)
        self.btn_close.setStyleSheet(close_btn_style)
        self.btn_close.clicked.connect(self._on_close)
        layout.addWidget(self.btn_close)
    
    def _apply_styles(self) -> None:
        """Apply dark mode styling to the title bar."""
        self.setStyleSheet("""
            #customTitleBar {
                background: #1a1a1a;
                border-bottom: 1px solid #333;
            }
            #lblWindowTitle {
                color: #ccc;
                font-size: 12px;
                font-weight: 500;
            }
        """)
    
    def _on_minimize(self) -> None:
        """Minimize the window."""
        self._parent.showMinimized()
    
    def _on_maximize(self) -> None:
        """Toggle maximize/restore."""
        if self._is_maximized:
            self._parent.showNormal()
            self.btn_maximize.setText("□")
            self._is_maximized = False
        else:
            self._parent.showMaximized()
            self.btn_maximize.setText("❐")
            self._is_maximized = True
    
    def _on_close(self) -> None:
        """Close the window."""
        self._parent.close()
    
    # --- Drag support ---
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Start window drag on left click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._parent.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Move window while dragging."""
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            # If maximized, restore before dragging
            if self._is_maximized:
                self._on_maximize()
            self._parent.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """End window drag."""
        self._drag_pos = None
        event.accept()
    
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Toggle maximize on double-click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_maximize()
            event.accept()
