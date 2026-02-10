"""Tests for the undo/redo command infrastructure."""

import pytest
from unittest.mock import MagicMock, call

from multicam_editor.logic.commands import (
    UndoableCommand,
    TrimCommand,
    SplitCommand,
    AddClipsCommand,
    RemoveClipsCommand,
    ReorderClipsCommand,
)


class TestUndoableCommand:
    """Tests for the base UndoableCommand class."""

    def test_init_text(self):
        cmd = UndoableCommand("Test Action")
        assert cmd.text() == "Test Action"

    def test_default_redo_does_nothing(self):
        cmd = UndoableCommand("noop")
        cmd.redo()  # Should not raise

    def test_default_undo_does_nothing(self):
        cmd = UndoableCommand("noop")
        cmd.undo()  # Should not raise

    def test_default_id_is_negative_one(self):
        cmd = UndoableCommand("noop")
        assert cmd.id() == -1

    def test_default_merge_returns_false(self):
        cmd1 = UndoableCommand("a")
        cmd2 = UndoableCommand("b")
        assert cmd1.mergeWith(cmd2) is False

    def test_first_redo_flag(self):
        cmd = UndoableCommand("test")
        assert cmd._first_redo is True


class TestTrimCommand:
    """Tests for the TrimCommand."""

    def _make_project(self):
        project = MagicMock()
        return project

    def test_redo_applies_new_trim(self):
        project = self._make_project()
        cmd = TrimCommand(project, "clip.mp4", old_in=0, old_out=5000, new_in=500, new_out=4500)
        cmd.redo()
        project.set_trim_by_path.assert_called_once_with("clip.mp4", 500, 4500)

    def test_undo_restores_old_trim(self):
        project = self._make_project()
        cmd = TrimCommand(project, "clip.mp4", old_in=0, old_out=5000, new_in=500, new_out=4500)
        cmd.undo()
        project.set_trim_by_path.assert_called_once_with("clip.mp4", 0, 5000)

    def test_redo_calls_refresh_callback(self):
        project = self._make_project()
        callback = MagicMock()
        cmd = TrimCommand(project, "clip.mp4", 0, 5000, 500, 4500, refresh_callback=callback)
        cmd.redo()
        callback.assert_called_once()

    def test_undo_calls_refresh_callback(self):
        project = self._make_project()
        callback = MagicMock()
        cmd = TrimCommand(project, "clip.mp4", 0, 5000, 500, 4500, refresh_callback=callback)
        cmd.undo()
        callback.assert_called_once()

    def test_id_returns_one(self):
        project = self._make_project()
        cmd = TrimCommand(project, "clip.mp4", 0, 5000, 500, 4500)
        assert cmd.id() == 1

    def test_merge_same_clip(self):
        """Consecutive trims on the same clip should merge."""
        project = self._make_project()
        cmd1 = TrimCommand(project, "clip.mp4", old_in=0, old_out=5000, new_in=100, new_out=4900)
        cmd2 = TrimCommand(project, "clip.mp4", old_in=100, old_out=4900, new_in=200, new_out=4800)
        assert cmd1.mergeWith(cmd2) is True
        # After merge, cmd1 should have cmd2's new values
        assert cmd1.new_in == 200
        assert cmd1.new_out == 4800

    def test_merge_different_clip_returns_false(self):
        """Trims on different clips should not merge."""
        project = self._make_project()
        cmd1 = TrimCommand(project, "clip1.mp4", 0, 5000, 100, 4900)
        cmd2 = TrimCommand(project, "clip2.mp4", 0, 5000, 100, 4900)
        assert cmd1.mergeWith(cmd2) is False

    def test_merge_with_non_trim_returns_false(self):
        """TrimCommand should not merge with non-TrimCommand."""
        project = self._make_project()
        cmd1 = TrimCommand(project, "clip.mp4", 0, 5000, 100, 4900)
        cmd2 = UndoableCommand("other")
        assert cmd1.mergeWith(cmd2) is False

    def test_no_refresh_callback(self):
        """Commands without refresh_callback should not crash."""
        project = self._make_project()
        cmd = TrimCommand(project, "clip.mp4", 0, 5000, 500, 4500, refresh_callback=None)
        cmd.redo()
        cmd.undo()


class TestAddClipsCommand:
    """Tests for AddClipsCommand."""

    def test_text_single_clip(self):
        project = MagicMock()
        cmd = AddClipsCommand(project, ["a.mp4"])
        assert cmd.text() == "Add 1 Clip"

    def test_text_multiple_clips(self):
        project = MagicMock()
        cmd = AddClipsCommand(project, ["a.mp4", "b.mp4", "c.mp4"])
        assert cmd.text() == "Add 3 Clips"

    def test_redo_calls_add_path(self):
        project = MagicMock()
        clip_mock = MagicMock()
        project.add_path.return_value = clip_mock
        project.clips.return_value = []

        cmd = AddClipsCommand(project, ["a.mp4", "b.mp4"])
        cmd.redo()
        assert project.add_path.call_count == 2

    def test_undo_removes_added_clips(self):
        project = MagicMock()
        clip_a = MagicMock()
        clip_b = MagicMock()
        project.add_path.side_effect = [clip_a, clip_b]
        project.clips.return_value = []

        cmd = AddClipsCommand(project, ["a.mp4", "b.mp4"])
        cmd.redo()

        # Now undo
        project.clips.return_value = [clip_a, clip_b]
        cmd.undo()
        # set_clips should be called with empty list (all added clips removed)
        project.set_clips.assert_called_once()
        kept = project.set_clips.call_args[0][0]
        assert clip_a not in kept
        assert clip_b not in kept


class TestRemoveClipsCommand:
    """Tests for RemoveClipsCommand."""

    def test_text_correct(self):
        project = MagicMock()
        cmd = RemoveClipsCommand(project, ["id1", "id2"])
        assert cmd.text() == "Remove 2 Clips"

    def test_redo_removes_clips(self):
        clip1 = MagicMock()
        clip1.id = "id1"
        clip2 = MagicMock()
        clip2.id = "id2"
        clip3 = MagicMock()
        clip3.id = "id3"

        project = MagicMock()
        project.clips.return_value = [clip1, clip2, clip3]

        cmd = RemoveClipsCommand(project, ["id1", "id3"])
        cmd.redo()

        project.set_clips.assert_called_once()
        kept = project.set_clips.call_args[0][0]
        kept_ids = [c.id for c in kept]
        assert "id2" in kept_ids
        assert "id1" not in kept_ids
        assert "id3" not in kept_ids

    def test_undo_restores_clips(self):
        clip1 = MagicMock()
        clip1.id = "id1"
        clip2 = MagicMock()
        clip2.id = "id2"

        project = MagicMock()
        project.clips.return_value = [clip1, clip2]

        cmd = RemoveClipsCommand(project, ["id1"])
        cmd.redo()

        # Now undo - only clip2 remains
        project.clips.return_value = [clip2]
        cmd.undo()

        project.set_clips.assert_called()
        restored = project.set_clips.call_args[0][0]
        restored_ids = [c.id for c in restored]
        assert "id1" in restored_ids


class TestReorderClipsCommand:
    """Tests for ReorderClipsCommand."""

    def test_text_correct(self):
        project = MagicMock()
        cmd = ReorderClipsCommand(project, ["a", "b"], ["b", "a"])
        assert cmd.text() == "Reorder Clips"

    def test_redo_applies_new_order(self):
        clip_a = MagicMock()
        clip_a.id = "a"
        clip_b = MagicMock()
        clip_b.id = "b"

        project = MagicMock()
        project.clips.return_value = [clip_a, clip_b]

        cmd = ReorderClipsCommand(project, ["a", "b"], ["b", "a"])
        cmd.redo()

        project.set_clips.assert_called_once()
        reordered = project.set_clips.call_args[0][0]
        assert reordered[0].id == "b"
        assert reordered[1].id == "a"

    def test_undo_restores_old_order(self):
        clip_a = MagicMock()
        clip_a.id = "a"
        clip_b = MagicMock()
        clip_b.id = "b"

        project = MagicMock()
        project.clips.return_value = [clip_b, clip_a]  # After redo

        cmd = ReorderClipsCommand(project, ["a", "b"], ["b", "a"])
        cmd.undo()

        project.set_clips.assert_called_once()
        restored = project.set_clips.call_args[0][0]
        assert restored[0].id == "a"
        assert restored[1].id == "b"

    def test_redo_calls_refresh_callback(self):
        project = MagicMock()
        project.clips.return_value = []
        callback = MagicMock()
        cmd = ReorderClipsCommand(project, [], [], refresh_callback=callback)
        cmd.redo()
        callback.assert_called_once()
