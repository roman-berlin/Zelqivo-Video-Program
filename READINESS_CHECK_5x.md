# Repository Readiness Check for 5.x Processing Pipeline

**Date**: 2024-12-19
**Status**: ⚠️ BLOCKED

---

## Summary

| Check | Status |
|-------|--------|
| Tests (`pytest -q`) | ✅ PASS (5/5) |
| Smoke Test | ❌ FAIL |
| Ready for 5.1 | ❌ NO |

---

## Test Results

```
.....                                                                    [100%]
5 passed
```

All unit tests pass.

---

## Smoke Test Results

| Step | Status | Notes |
|------|--------|-------|
| Launch app | ✅ PASS | App starts without crash |
| Add 2-3 videos | ✅ PASS | Files added, counter shows 2/10 |
| Preview play/seek | ❌ FAIL | "no preview available", Duration: 00:00 |
| Timeline matches file list | ✅ PASS | Order syncs correctly |
| Split → Undo → Redo | ⏸️ BLOCKED | Cannot test without working preview |
| Reorder → Undo → Redo | ⏸️ BLOCKED | Cannot verify without preview |

---

## Blockers

### 1. Video Preview Not Working (Critical)

**Symptom**:
- Preview shows "(no preview available)"
- Duration displays "00:00"
- In/Out fields show "00:00"

**Root Cause**:
- QMediaPlayer (Qt6 Multimedia) fails to decode video on Windows
- `durationKnown` signal never fires → TrimPanel never receives duration
- OpenCV thumbnail fallback also fails to read frame

**Affected Files**:
- `src/multicam_editor/ui/video_preview.py` - QMediaPlayer-based playback
- `src/multicam_editor/ui/trim_panel.py` - depends on `durationKnown` signal

**Impact**:
- Cannot preview clips
- Cannot verify seek functionality
- Cannot test split at playhead (needs valid playhead position)
- Trim panel non-functional

**Potential Fixes** (for next prompt):
1. Use `ffprobe` to get duration when QMediaPlayer fails
2. Install Windows codec pack (user-side workaround)
3. Implement ffmpeg-based playback for 5.x pipeline

---

## Guardrails Verified (Code Review)

| Guardrail | Status | Location |
|-----------|--------|----------|
| MIN_SEGMENT_MS = 100 | ✅ | `project.py:L18`, `trim_panel.py:L52` |
| Split at 0/duration blocked | ✅ | `project.py:L115-120`, `trim_panel.py:L180-195` |
| Trim clamp to duration | ✅ | `trim_panel.py:_clamp_pair()` |
| In/Out cannot cross | ✅ | `trim_panel.py:_clamp_pair()` |
| Non-blocking status toast | ✅ | `trim_panel.py:_show_status()` → `main_window._toast()` |

---

## Architecture Verified

| Principle | Status | Evidence |
|-----------|--------|----------|
| Project is source of truth | ✅ | All commands use `project.clips()` |
| Timeline mirrors Project | ✅ | `adapter.refresh_from_project()` pattern |
| File List mirrors Project | ✅ | `_refresh_after_undo_redo()` syncs list |
| Undo via QUndoStack | ✅ | `AddClipsCommand`, `TrimCommand`, `SplitCommand`, `ReorderClipsCommand` |
| No silent `except: pass` | ✅ | Uses `logger.debug(..., exc_info=True)` |

---

## Recommendation

**Before starting 5.1**: Fix video preview to work without native codecs.

Suggested approach for 5.1:
- Add `ffprobe` wrapper to extract duration/metadata
- Emit `durationKnown` from ffprobe result when QMediaPlayer fails
- This naturally leads into 5.x ffmpeg/ffprobe infrastructure

---

## Files Changed

None (readiness check only).

---

## Next Steps

1. **Fix Blocker**: Implement ffprobe-based duration detection as fallback
2. **Re-run Smoke**: Verify preview works after fix
3. **Proceed to 5.1**: Begin ffmpeg/ffprobe pipeline work
