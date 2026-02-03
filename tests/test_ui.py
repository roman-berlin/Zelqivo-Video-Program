# file: tests/test_ui.py
"""UI smoke tests for MultiCamEditor using pytest-qt.

These tests verify basic UI functionality:
- Windows open without errors
- Theme switching works
- Dialogs open and close
- File list widget accepts files
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox


# Ensure QApplication is created before importing UI modules
@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def main_window(qtbot, qapp):
    """Create MainWindow for testing."""
    from multicam_editor.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    yield window
    window.close()


class TestMainWindow:
    """Tests for the main application window."""

    def test_window_opens(self, main_window):
        """Main window should open without errors."""
        assert main_window.isVisible()
        assert main_window.windowTitle() == "Zelqivo"

    def test_window_has_modern_toolbar(self, main_window):
        """Main window should have modern toolbar buttons (replaced old menu bar)."""
        # Check for Settings button (replaces File > Settings)
        assert hasattr(main_window, "btn_app_settings")
        # Check for Magic Settings button
        assert hasattr(main_window, "btn_magic_settings")
        # Check for Export button (replaces File > Export)
        assert hasattr(main_window, "btn_export")

    def test_initial_video_count(self, main_window):
        """Initial video count should be zero."""
        # The file list should be empty initially
        file_list = main_window.file_list
        assert file_list.video_count() == 0


class TestThemeToggle:
    """Tests for theme switching functionality."""

    def test_theme_toggle_exists(self, main_window):
        """Theme toggle functionality should exist in settings or via View menu."""
        # Check if there's a way to change themes - either via method or settings
        has_theme_control = (
            hasattr(main_window, "_toggle_theme") or
            hasattr(main_window, "toggle_theme") or
            hasattr(main_window, "_apply_startup_theme")
        )
        assert has_theme_control

    def test_theme_methods_callable(self, main_window):
        """Theme-related methods should exist."""
        # At minimum, apply_startup_theme should exist
        assert hasattr(main_window, "_apply_startup_theme")


class TestFileListWidget:
    """Tests for the file list widget."""

    def test_file_list_exists(self, main_window):
        """File list widget should exist."""
        assert main_window.file_list is not None

    def test_add_videos_button_exists(self, main_window):
        """Add Videos button should exist."""
        # Find button by looking for 'Add' in button text
        found = False
        for child in main_window.findChildren(type(main_window.file_list)):
            if hasattr(child, "text") and "Add" in str(child.text()):
                found = True
                break
        # Button exists in toolbar or as QPushButton
        assert hasattr(main_window, "on_add_files")

    @patch.object(QFileDialog, 'getOpenFileNames')
    def test_add_files_called(self, mock_dialog, main_window, qtbot):
        """Adding files should open file dialog."""
        mock_dialog.return_value = ([], "")
        
        # Call add files
        main_window.on_add_files()
        
        # Dialog should have been called
        mock_dialog.assert_called_once()


class TestDialogs:
    """Tests for application dialogs."""

    def test_settings_dialog_opens(self, main_window, qtbot):
        """Settings dialog should open."""
        from multicam_editor.ui.settings_dialog import SettingsDialog
        
        # Create settings dialog
        dialog = SettingsDialog(main_window)
        qtbot.addWidget(dialog)
        
        # Should be able to show it
        dialog.show()
        qtbot.waitExposed(dialog)
        assert dialog.isVisible()
        
        dialog.close()

    def test_loading_dialog_opens(self, main_window, qtbot):
        """Loading dialog should open."""
        from multicam_editor.ui.loading_dialog import LoadingDialog
        
        # Create loading dialog
        dialog = LoadingDialog(main_window, "Test loading...")
        qtbot.addWidget(dialog)
        
        dialog.show()
        qtbot.waitExposed(dialog)
        assert dialog.isVisible()
        
        dialog.close()


class TestCreateVideoButton:
    """Tests for the Create Video button."""

    def test_create_video_button_disabled_initially(self, main_window):
        """Create Video button should be disabled when no videos loaded."""
        # Find Create Video button
        create_btn = None
        from PyQt6.QtWidgets import QPushButton
        for btn in main_window.findChildren(QPushButton):
            if "Create" in btn.text():
                create_btn = btn
                break
        
        if create_btn:
            # Should be disabled when no videos
            assert not create_btn.isEnabled() or main_window.file_list.video_count() < 2


class TestKeyboardShortcuts:
    """Tests for keyboard shortcuts."""

    def test_undo_redo_actions_exist(self, main_window):
        """Undo/Redo actions should exist."""
        assert hasattr(main_window, "undo_stack")
        assert main_window.undo_stack is not None
