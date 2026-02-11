"""Tests for the pipeline checkpoint system."""

import json
import time
from unittest.mock import patch

import pytest

from multicam_editor.logic.checkpoint import (
    PipelineCheckpoint,
    save_checkpoint,
    load_checkpoint,
    delete_checkpoint,
    find_incomplete_checkpoints,
    cleanup_old_checkpoints,
    get_checkpoint_path,
)


class TestPipelineCheckpointDataclass:
    """Tests for the PipelineCheckpoint dataclass."""

    def test_create_with_defaults(self):
        """Dataclass should be creatable with only required fields."""
        cp = PipelineCheckpoint(run_id="abc123", current_stage="PROBE")
        assert cp.run_id == "abc123"
        assert cp.current_stage == "PROBE"
        assert cp.completed_stages == []
        assert cp.input_files == []
        assert cp.rendered_segments == []
        assert cp.camera_offsets == {}
        assert cp.cut_plan_json == ""
        assert cp.output_path == ""
        assert cp.timestamp == ""
        assert cp.version == "1.0"

    def test_create_with_all_fields(self):
        """Dataclass should accept all fields."""
        cp = PipelineCheckpoint(
            run_id="run-42",
            current_stage="RENDER",
            completed_stages=["PROBE", "ALIGN", "DIARIZE"],
            input_files=["a.mp4", "b.mp4"],
            rendered_segments=["seg1.mp4"],
            camera_offsets={0: 0.0, 1: 150.5},
            cut_plan_json='{"cuts": []}',
            output_path="/out/video.mp4",
            timestamp="2026-01-01 00:00:00",
            version="1.0",
        )
        assert cp.completed_stages == ["PROBE", "ALIGN", "DIARIZE"]
        assert cp.camera_offsets[1] == 150.5
        assert cp.cut_plan_json == '{"cuts": []}'


class TestCheckpointPersistence:
    """Tests for save/load/delete checkpoint operations."""

    @pytest.fixture(autouse=True)
    def use_tmp_dir(self, tmp_path):
        """Redirect checkpoint storage to a temp directory."""
        with patch(
            "multicam_editor.logic.checkpoint.get_checkpoint_dir",
            return_value=tmp_path,
        ):
            self.tmp_dir = tmp_path
            yield

    def _make_checkpoint(self, run_id="test-run", stage="PROBE", **kwargs):
        return PipelineCheckpoint(run_id=run_id, current_stage=stage, **kwargs)

    def test_save_and_load_roundtrip(self):
        """Save then load should return identical checkpoint."""
        cp = self._make_checkpoint(
            input_files=["a.mp4", "b.mp4"],
            completed_stages=["PROBE"],
            camera_offsets={0: 0.0, 1: -200.0},
        )
        assert save_checkpoint(cp) is True

        loaded = load_checkpoint("test-run")
        assert loaded is not None
        assert loaded.run_id == "test-run"
        assert loaded.current_stage == "PROBE"
        assert loaded.input_files == ["a.mp4", "b.mp4"]
        assert loaded.completed_stages == ["PROBE"]
        assert loaded.camera_offsets == {0: 0.0, 1: -200.0}

    def test_save_sets_timestamp(self):
        """Save should populate the timestamp field."""
        cp = self._make_checkpoint()
        save_checkpoint(cp)

        loaded = load_checkpoint("test-run")
        assert loaded.timestamp != ""

    def test_load_nonexistent_returns_none(self):
        """Loading a nonexistent checkpoint should return None."""
        result = load_checkpoint("does-not-exist")
        assert result is None

    def test_load_corrupt_file_returns_none(self):
        """Loading a corrupt checkpoint file should return None."""
        path = get_checkpoint_path("corrupt")
        path.write_text("not valid json", encoding="utf-8")

        result = load_checkpoint("corrupt")
        assert result is None

    def test_delete_checkpoint(self):
        """Delete should remove the checkpoint file."""
        cp = self._make_checkpoint(run_id="to-delete")
        save_checkpoint(cp)
        assert get_checkpoint_path("to-delete").exists()

        assert delete_checkpoint("to-delete") is True
        assert not get_checkpoint_path("to-delete").exists()

    def test_delete_nonexistent_returns_true(self):
        """Deleting a nonexistent checkpoint should return True (no-op)."""
        assert delete_checkpoint("no-such-run") is True

    def test_find_incomplete_excludes_done(self):
        """find_incomplete_checkpoints should exclude DONE runs."""
        save_checkpoint(self._make_checkpoint(run_id="done1", stage="DONE"))
        save_checkpoint(self._make_checkpoint(run_id="incomplete1", stage="RENDER"))
        save_checkpoint(self._make_checkpoint(run_id="incomplete2", stage="PROBE"))

        result = find_incomplete_checkpoints()
        run_ids = [cp.run_id for cp in result]
        assert "done1" not in run_ids
        assert "incomplete1" in run_ids
        assert "incomplete2" in run_ids

    def test_cleanup_old_checkpoints(self):
        """cleanup_old_checkpoints should delete files older than max_age_days."""
        # Create a checkpoint
        cp = self._make_checkpoint(run_id="old-run")
        save_checkpoint(cp)
        path = get_checkpoint_path("old-run")

        # Backdate the file's modified time by 10 days
        old_time = time.time() - (10 * 24 * 60 * 60)
        import os
        os.utime(path, (old_time, old_time))

        deleted = cleanup_old_checkpoints(max_age_days=7)
        assert deleted == 1
        assert not path.exists()

    def test_cleanup_keeps_recent_checkpoints(self):
        """cleanup_old_checkpoints should keep recent files."""
        cp = self._make_checkpoint(run_id="recent-run")
        save_checkpoint(cp)
        path = get_checkpoint_path("recent-run")

        deleted = cleanup_old_checkpoints(max_age_days=7)
        assert deleted == 0
        assert path.exists()
