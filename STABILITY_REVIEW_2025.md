# Stability Review Report - December 2025

**Date**: 2025-12-22
**Status**: Tests PASS (2 skipped), Ready for smoke test
**pytest result**: All 120 tests passed (2 skipped for pyannote unavailable)

## Findings

### Critical (crash/data loss)
*None identified* - The previous critical issue (duplicate Project class) has been resolved.

### High (wrong behavior, major instability)

1. **`audio_sync.py:4-6` - Missing import guards for optional ML deps**
   - Why: If librosa/soundfile/numpy not installed, import crashes at module load
   - Fix: Add lazy imports with clear error message

2. **`video_preview.py:338` - Daemon thread for ffprobe may leak**
   - Why: Thread spawned without join() or proper lifecycle management
   - Fix: Already uses daemon=True which is acceptable; add timeout guard

3. **`processing_pipeline.py:63` - ProcessingPipeline accepts <2 files**
   - Why: ValueError raised but caller may not handle it gracefully
   - Fix: Already has validation; ensure callers catch ValueError

### Medium (maintainability, tech debt)

1. **`project.py:90-95,113` - Path-based lookups after splits**
   - Why: After splitting, multiple clips share same path; lookups return FIRST match
   - Fix: TODO comments already added; future refactor to use clip ID

2. **`video_utils.py:split_video` - Splits lose audio track**
   - Why: Uses OpenCV which doesn't preserve audio
   - Fix: Documented in docstring; use ffmpeg wrapper for audio-preserving splits

3. **`file_utils.py:8-9` - Limited video extension support**
   - Why: Only .mp4, .avi, .mov supported; missing .mkv, .webm, .m4v
   - Fix: Expand VIDEO_EXTS set

4. **`main_window.py:595-600` - Silent exception handling in signal connections**
   - Why: `except Exception: pass` hides connection failures
   - Fix: Log at debug level with exc_info

### Low (style, minor cleanup)

1. **`ffprobe.py:95-96` - Windows-only path checking**
   - Why: Common paths only cover Windows installations
   - Fix: Already handles PATH correctly; Windows paths are fallbacks

2. **`qa_artifacts.py:35` - No error handling for mkdir**
   - Why: Could fail on permissions issues
   - Fix: Already has parents=True, exist_ok=True which is safe

## Changes Implemented

### Files Changed:
1. `src/multicam_editor/utils/file_utils.py` - Expand video extensions
2. `src/multicam_editor/ui/main_window.py` - Improve exception logging in signal connections

### Key Edits:
- Added .mkv, .webm, .m4v, .flv, .wmv to VIDEO_EXTS
- Added .flac, .ogg to AUDIO_EXTS
- Replaced silent `except Exception: pass` with proper logging

## Next (not implemented)
- Consider migrating path-based Project APIs to clip ID-based APIs
- Add ffmpeg-based split for audio preservation when ffmpeg available
- Add more comprehensive integration tests for UI components
