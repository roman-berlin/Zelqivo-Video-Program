# file: tests/test_magic_settings.py
"""Tests for Magic Settings dialog and settings persistence."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication


# Ensure QApplication is created before importing UI modules
@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def clear_magic_settings():
    """Clear magic settings before each test."""
    settings = QSettings("MultiCamEditor", "MultiCamEditor")
    # Clear all magic/* keys
    settings.beginGroup("magic")
    settings.remove("")  # Remove all keys in this group
    settings.endGroup()
    yield
    # Cleanup after test
    settings.beginGroup("magic")
    settings.remove("")
    settings.endGroup()


class TestMagicSettingsDialog:
    """Tests for MagicSettingsDialog component."""

    def test_dialog_opens(self, qtbot, qapp, clear_magic_settings):
        """Dialog should open without errors."""
        from multicam_editor.ui.magic_settings_dialog import MagicSettingsDialog
        
        dialog = MagicSettingsDialog()
        qtbot.addWidget(dialog)
        
        dialog.show()
        qtbot.waitExposed(dialog)
        assert dialog.isVisible()
        assert dialog.windowTitle() == "✨ Magic Settings"
        
        dialog.close()

    def test_dialog_has_all_tabs(self, qtbot, qapp, clear_magic_settings):
        """Dialog should have all four tabs."""
        from multicam_editor.ui.magic_settings_dialog import MagicSettingsDialog
        
        dialog = MagicSettingsDialog()
        qtbot.addWidget(dialog)
        
        # Find tab widget
        tabs = dialog.findChild(type(dialog), "magicSettingsTabs")
        # We can check by checking widget attribute
        assert hasattr(dialog, "chk_split_screen")  # AI Director
        assert hasattr(dialog, "chk_auto_leveling")  # Audio
        assert hasattr(dialog, "cmb_caption_style")  # Captions
        assert hasattr(dialog, "chk_vertical_teasers")  # Repurpose
        
        dialog.close()

    def test_settings_persist_to_qsettings(self, qtbot, qapp, clear_magic_settings):
        """Settings should persist to QSettings when saved."""
        from multicam_editor.ui.magic_settings_dialog import MagicSettingsDialog
        
        dialog = MagicSettingsDialog()
        qtbot.addWidget(dialog)
        
        # Toggle some settings
        dialog.chk_split_screen.setChecked(True)
        dialog.chk_noise_reduction.setChecked(True)
        dialog.chk_vertical_teasers.setChecked(True)
        dialog.cmb_caption_style.setCurrentIndex(2)  # "Clean"
        
        # Save
        dialog._save_and_accept()
        
        # Verify in QSettings
        settings = QSettings("MultiCamEditor", "MultiCamEditor")
        assert settings.value("magic/director/split_screen", False, type=bool) is True
        assert settings.value("magic/audio/noise_reduction", False, type=bool) is True
        assert settings.value("magic/repurpose/vertical_teasers", False, type=bool) is True
        assert settings.value("magic/captions/style_index", 0, type=int) == 2

    def test_settings_load_on_reopen(self, qtbot, qapp, clear_magic_settings):
        """Settings should load correctly when dialog is reopened."""
        from multicam_editor.ui.magic_settings_dialog import MagicSettingsDialog
        
        # First dialog: set and save
        dialog1 = MagicSettingsDialog()
        qtbot.addWidget(dialog1)
        dialog1.chk_reaction_shots.setChecked(True)
        dialog1.chk_auto_ducking.setChecked(True)
        dialog1._save_and_accept()
        
        # Second dialog: verify loaded
        dialog2 = MagicSettingsDialog()
        qtbot.addWidget(dialog2)
        
        assert dialog2.chk_reaction_shots.isChecked() is True
        assert dialog2.chk_auto_ducking.isChecked() is True
        
        dialog2.close()


class TestGetMagicSettings:
    """Tests for the get_magic_settings helper function."""

    def test_get_magic_settings_returns_dict(self, clear_magic_settings):
        """Helper function returns structured dictionary."""
        from multicam_editor.ui.magic_settings_dialog import get_magic_settings
        
        result = get_magic_settings()
        
        assert isinstance(result, dict)
        assert "director" in result
        assert "audio" in result
        assert "captions" in result
        assert "repurpose" in result

    def test_get_magic_settings_has_correct_structure(self, clear_magic_settings):
        """Helper function returns all expected keys."""
        from multicam_editor.ui.magic_settings_dialog import get_magic_settings
        
        result = get_magic_settings()
        
        # Check director keys
        assert "split_screen" in result["director"]
        assert "reaction_shots" in result["director"]
        assert "wide_reset" in result["director"]
        
        # Check audio keys
        assert "auto_leveling" in result["audio"]
        assert "noise_reduction" in result["audio"]
        assert "auto_ducking" in result["audio"]
        
        # Check repurpose keys
        assert "vertical_teasers" in result["repurpose"]
        assert "remove_silence" in result["repurpose"]

    def test_get_magic_settings_default_values(self, clear_magic_settings):
        """Default values should be sensible."""
        from multicam_editor.ui.magic_settings_dialog import get_magic_settings
        
        result = get_magic_settings()
        
        # Most should default to False (disabled)
        assert result["director"]["split_screen"] is False
        assert result["audio"]["noise_reduction"] is False
        assert result["repurpose"]["vertical_teasers"] is False
        
        # Auto-leveling defaults to True (commonly wanted)
        assert result["audio"]["auto_leveling"] is True
