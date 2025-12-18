"""Tests for the core project logic.

These tests exercise the ``Project`` and ``Clip`` classes to ensure that
trimming, duration management and splitting behave as expected.  The
minimum segment length guardrails are validated for both too‑early and
too‑late split positions.
"""

from multicam_editor.core.project import Project


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
