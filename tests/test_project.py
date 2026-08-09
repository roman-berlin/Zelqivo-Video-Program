"""Tests for the core project logic.

These tests exercise the ``Project`` and ``Clip`` classes to ensure that
trimming, duration management and splitting behave as expected.  The
minimum segment length guardrails are validated for both too‑early and
too‑late split positions.
"""

import os
from multicam_editor.core.project import Clip, Project


def test_clip_effect_defaults() -> None:
    """Clip effect fields have correct defaults (Prompt 8.1)."""
    clip = Clip(id="test", path="video.mp4")
    assert clip.fade_in_ms == 0
    assert clip.fade_out_ms == 0
    assert clip.grayscale is False
    assert clip.speed == 1.0


def test_clip_with_effects() -> None:
    """Clip can be created with custom effect values."""
    clip = Clip(
        id="test",
        path="video.mp4",
        fade_in_ms=500,
        fade_out_ms=300,
        grayscale=True,
        speed=2.0,
    )
    assert clip.fade_in_ms == 500
    assert clip.fade_out_ms == 300
    assert clip.grayscale is True
    assert clip.speed == 2.0


def test_add_and_split() -> None:
    """Verify adding a clip and splitting it respects guardrails."""
    p = Project()
    # Add a single clip and record its duration.  The clip's ``out_ms``
    # should be initialised to the duration when first set.
    clip = p.add_path("video.mp4")
    p.set_duration_by_path("video.mp4", 1000)
    assert clip.out_ms == 1000

    # Splitting too close to the start should be rejected.
    assert p.split_clip_by_path("video.mp4", p.MIN_SEGMENT_MS - 10) is None
    # Splitting too close to the end should also be rejected.
    assert p.split_clip_by_path("video.mp4", 1000 - (p.MIN_SEGMENT_MS - 10)) is None

    # A valid split point produces two clips with the expected boundaries.
    result = p.split_clip_by_path("video.mp4", 500)
    assert result is not None
    left, right = result
    assert left.in_ms == 0 and left.out_ms == 500
    assert right.in_ms == 500 and right.out_ms == 1000


def test_trim_and_get_trim() -> None:
    """Ensure trim values are clamped and retrieved correctly."""
    p = Project()
    p.add_path("a.mp4")
    # Without duration the default trim range is (0,0).
    assert p.get_trim_by_path("a.mp4") == (0, 0)

    p.set_duration_by_path("a.mp4", 1000)
    # Setting a trim within the duration should stick.
    p.set_trim_by_path("a.mp4", 100, 900)
    assert p.get_trim_by_path("a.mp4") == (100, 900)

    # Out of range trims are clamped into the duration.
    p.set_trim_by_path("a.mp4", -50, 2000)
    # Negative in_ms becomes 0, out_ms is clamped to duration.
    assert p.get_trim_by_path("a.mp4") == (0, 1000)


def test_split_produces_unique_clip_ids() -> None:
    """Verify split creates two clips with same path but different IDs."""
    p = Project()
    clip = p.add_path("video.mp4")
    assert clip is not None

    # Set duration so split can proceed
    p.set_duration_by_path("video.mp4", 1000)

    # Perform split
    result = p.split_clip_by_path("video.mp4", 500)
    assert result is not None
    left, right = result

    # Both clips should have same source path
    assert left.path == "video.mp4"
    assert right.path == "video.mp4"

    # But different IDs (stable identity)
    assert left.id != right.id
    assert left.id != clip.id  # Neither should match original
    assert right.id != clip.id

    # Correct in/out boundaries
    assert left.in_ms == 0
    assert left.out_ms == 500
    assert right.in_ms == 500
    assert right.out_ms == 1000

    # Duration should be preserved from original
    assert left.duration_ms == 1000
    assert right.duration_ms == 1000


# ============== Guardrails Tests (Prompt 4.5) ==============


def test_split_at_zero_rejected() -> None:
    """Split at 0ms (start) must be prevented."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    assert p.split_clip_by_path("v.mp4", 0) is None


def test_split_at_duration_rejected() -> None:
    """Split at duration (end) must be prevented."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    assert p.split_clip_by_path("v.mp4", 1000) is None


def test_split_at_exact_min_segment_allowed() -> None:
    """Split at exactly MIN_SEGMENT_MS from edges should succeed."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    # Split at exactly 100ms from start
    result = p.split_clip_by_path("v.mp4", p.MIN_SEGMENT_MS)
    assert result is not None
    left, right = result
    assert left.out_ms == 100
    assert right.in_ms == 100


def test_split_at_exact_min_segment_from_end_allowed() -> None:
    """Split at exactly MIN_SEGMENT_MS from end should succeed."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    # Split at 900ms (100ms from end)
    result = p.split_clip_by_path("v.mp4", 1000 - p.MIN_SEGMENT_MS)
    assert result is not None
    left, right = result
    assert left.out_ms == 900
    assert right.in_ms == 900


def test_split_one_less_than_min_segment_rejected() -> None:
    """Split at MIN_SEGMENT_MS - 1 from edges must be rejected."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    # 99ms from start
    assert p.split_clip_by_path("v.mp4", p.MIN_SEGMENT_MS - 1) is None


def test_split_one_less_from_end_rejected() -> None:
    """Split at MIN_SEGMENT_MS - 1 from end must be rejected."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    # 901ms (99ms from end)
    assert p.split_clip_by_path("v.mp4", 1000 - p.MIN_SEGMENT_MS + 1) is None


def test_trim_in_out_equal_allowed() -> None:
    """In/Out can be equal (zero-length trim)."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    p.set_trim_by_path("v.mp4", 500, 500)
    assert p.get_trim_by_path("v.mp4") == (500, 500)


def test_trim_in_out_cannot_cross() -> None:
    """If in > out after clamping, out is raised to match in."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    # Set in=700, out=300 - out should be clamped to in
    p.set_trim_by_path("v.mp4", 700, 300)
    in_ms, out_ms = p.get_trim_by_path("v.mp4")
    assert out_ms >= in_ms


def test_trim_clamp_negative_in() -> None:
    """Negative in_ms is clamped to 0."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    p.set_trim_by_path("v.mp4", -100, 500)
    assert p.get_trim_by_path("v.mp4") == (0, 500)


def test_trim_clamp_out_over_duration() -> None:
    """out_ms exceeding duration is clamped to duration."""
    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    p.set_trim_by_path("v.mp4", 100, 9999)
    assert p.get_trim_by_path("v.mp4") == (100, 1000)


def test_no_duplicate_clips_on_add() -> None:
    """Adding the same path twice returns None (no duplicate)."""
    p = Project()
    clip1 = p.add_path("v.mp4")
    assert clip1 is not None
    clip2 = p.add_path("v.mp4")
    assert clip2 is None
    assert len(p.clips()) == 1


# ============== TrimCommand Undo/Redo Tests (Prompt 4a.4) ==============


def test_trim_command_undo_redo() -> None:
    """TrimCommand undo restores previous in/out, redo reapplies."""
    from PySide6.QtGui import QUndoStack
    from multicam_editor.logic.commands import TrimCommand

    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    p.set_trim_by_path("v.mp4", 0, 1000)  # initial state

    stack = QUndoStack()
    cmd = TrimCommand(p, "v.mp4", 0, 1000, 100, 900)
    stack.push(cmd)

    # After push, trim should be updated
    assert p.get_trim_by_path("v.mp4") == (100, 900)

    # Undo restores original
    stack.undo()
    assert p.get_trim_by_path("v.mp4") == (0, 1000)

    # Redo reapplies
    stack.redo()
    assert p.get_trim_by_path("v.mp4") == (100, 900)


def test_trim_command_coalesces_multiple_drags() -> None:
    """Multiple TrimCommands on same clip coalesce into one undo operation."""
    from PySide6.QtGui import QUndoStack
    from multicam_editor.logic.commands import TrimCommand

    p = Project()
    p.add_path("v.mp4")
    p.set_duration_by_path("v.mp4", 1000)
    p.set_trim_by_path("v.mp4", 0, 1000)  # initial

    stack = QUndoStack()

    # Simulate dragging: multiple small adjustments
    cmd1 = TrimCommand(p, "v.mp4", 0, 1000, 50, 1000)
    stack.push(cmd1)
    assert p.get_trim_by_path("v.mp4") == (50, 1000)

    cmd2 = TrimCommand(p, "v.mp4", 50, 1000, 100, 1000)
    stack.push(cmd2)
    assert p.get_trim_by_path("v.mp4") == (100, 1000)

    cmd3 = TrimCommand(p, "v.mp4", 100, 1000, 150, 900)
    stack.push(cmd3)
    assert p.get_trim_by_path("v.mp4") == (150, 900)

    # Only ONE undo should restore to original (coalesced)
    stack.undo()
    assert p.get_trim_by_path("v.mp4") == (0, 1000)

    # Stack should have only 1 command (merged)
    assert stack.count() == 1


def test_trim_command_different_clips_not_coalesced() -> None:
    """TrimCommands on different clips are NOT coalesced."""
    from PySide6.QtGui import QUndoStack
    from multicam_editor.logic.commands import TrimCommand

    p = Project()
    p.add_path("a.mp4")
    p.add_path("b.mp4")
    p.set_duration_by_path("a.mp4", 1000)
    p.set_duration_by_path("b.mp4", 1000)

    stack = QUndoStack()

    cmd1 = TrimCommand(p, "a.mp4", 0, 1000, 100, 900)
    stack.push(cmd1)

    cmd2 = TrimCommand(p, "b.mp4", 0, 1000, 200, 800)
    stack.push(cmd2)

    # Two separate commands (not merged)
    assert stack.count() == 2

    # Undo first one
    stack.undo()
    assert p.get_trim_by_path("b.mp4") == (0, 1000)
    assert p.get_trim_by_path("a.mp4") == (100, 900)

    # Undo second
    stack.undo()
    assert p.get_trim_by_path("a.mp4") == (0, 1000)


# ============== Save/Load Tests (Prompt 9.1) ==============


def test_save_load_roundtrip(tmp_path) -> None:
    """Save -> load restores project state 1:1."""
    import tempfile

    # Create project with clips
    p1 = Project()
    clip1 = p1.add_path("video1.mp4")
    clip2 = p1.add_path("video2.mp4")
    p1.set_duration_by_path("video1.mp4", 5000)
    p1.set_duration_by_path("video2.mp4", 3000)
    p1.set_trim_by_path("video1.mp4", 100, 4500)

    # Save to temp file
    project_file = tmp_path / "test_project.json"
    p1.save_to_json(str(project_file))

    # Load from file
    p2 = Project.load_from_json(str(project_file))

    # Verify clips count and order
    assert len(p2.clips()) == 2

    # Verify first clip
    clips = p2.clips()
    assert clips[0].id == clip1.id
    assert os.path.basename(clips[0].path) == "video1.mp4"
    assert clips[0].in_ms == 100
    assert clips[0].out_ms == 4500
    assert clips[0].duration_ms == 5000

    # Verify second clip
    assert clips[1].id == clip2.id
    assert os.path.basename(clips[1].path) == "video2.mp4"
    assert clips[1].duration_ms == 3000


def test_save_load_with_effects(tmp_path) -> None:
    """Save/load preserves effect settings."""
    p1 = Project()
    clip = p1.add_path("video.mp4")
    p1.set_duration_by_path("video.mp4", 1000)

    # Modify effects on the clip
    clips = p1.clips()
    clips[0].fade_in_ms = 250
    clips[0].fade_out_ms = 300
    clips[0].grayscale = True
    clips[0].speed = 1.5

    # Save and load
    project_file = tmp_path / "effects_project.json"
    p1.save_to_json(str(project_file))
    p2 = Project.load_from_json(str(project_file))

    # Verify effects preserved
    loaded = p2.clips()[0]
    assert loaded.fade_in_ms == 250
    assert loaded.fade_out_ms == 300
    assert loaded.grayscale is True
    assert loaded.speed == 1.5


def test_save_load_with_split_clips(tmp_path) -> None:
    """Save/load preserves split clips with same path."""
    p1 = Project()
    p1.add_path("video.mp4")
    p1.set_duration_by_path("video.mp4", 1000)

    # Split the clip
    result = p1.split_clip_by_path("video.mp4", 500)
    assert result is not None
    left, right = result

    # Save and load
    project_file = tmp_path / "split_project.json"
    p1.save_to_json(str(project_file))
    p2 = Project.load_from_json(str(project_file))

    # Verify both clips preserved
    clips = p2.clips()
    assert len(clips) == 2

    # Verify IDs preserved
    assert clips[0].id == left.id
    assert clips[1].id == right.id

    # Verify trim boundaries
    assert clips[0].in_ms == 0
    assert clips[0].out_ms == 500
    assert clips[1].in_ms == 500
    assert clips[1].out_ms == 1000


def test_save_load_empty_project(tmp_path) -> None:
    """Save/load works with empty project."""
    p1 = Project()

    project_file = tmp_path / "empty_project.json"
    p1.save_to_json(str(project_file))
    p2 = Project.load_from_json(str(project_file))

    assert len(p2.clips()) == 0


def test_load_checks_schema_version(tmp_path) -> None:
    """Loading project with wrong schema version raises error."""
    import json

    project_file = tmp_path / "bad_schema.json"
    with open(project_file, "w") as f:
        json.dump({"schema_version": 999, "clips": []}, f)

    try:
        Project.load_from_json(str(project_file))
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unsupported schema version" in str(e)
