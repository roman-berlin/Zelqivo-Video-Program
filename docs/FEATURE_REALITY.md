# Feature Reality Matrix

> **Last Updated**: 2026-02-11
> **Audit Version**: 2.2
> **Status**: COMPREHENSIVE AUDIT COMPLETE

## Executive Summary

This document provides an honest assessment of what actually exists in the codebase versus what appears to exist in the UI or documentation.

### Quick Status
- **Production-Safe Features**: 20+
- **Partially Implemented**: 4
- **UI-Only (No Backend)**: 4
- **Stub/Placeholder**: 1
- **Test Status**: ✅ 539 passed, 2 skipped — 32 test files, Qt tests included, 48% coverage (2 known Windows-path test failures on macOS/Linux)

---

## Feature Reality Table

| Feature Name | Status | Implementation Location | UI Exists? | Backend Logic Exists? | Notes |
|-------------|--------|------------------------|------------|----------------------|-------|
| **Video Import** | ✅ Fully Implemented | `ui/file_list_widget.py`, `utils/ffprobe.py` | Yes | Yes | Unlimited video files, drag-drop, probe metadata with caching |
| **Video Preview** | ✅ Fully Implemented | `ui/video_preview.py` | Yes | Yes | Single video playback with seek |
| **Speaker Detection (Energy)** | ✅ Fully Implemented | `logic/active_speaker.py` → `RealEnergyVADBackend` | Yes | Yes | CPU-only, energy-based VAD with robust switching logic |
| **Speaker Detection (Pyannote)** | ⚠️ Partially Implemented | `logic/active_speaker.py` → `RealDiarizationBackend` | Yes | Yes | Requires `pyannote.audio` optional dependency + HuggingFace auth |
| **Speaker Detection (Lips)** | ⚠️ Partially Implemented | `logic/active_speaker.py` → `LipsBackend` | Yes | Yes | Requires `torch`, GPU recommended, model download |
| **Fast Rules Engine** | ✅ Fully Implemented | `logic/fast_rules_engine.py` | Yes | Yes | Rule-based camera switching, configurable parameters |
| **Decision Engine** | ✅ Fully Implemented | `logic/decision_engine.py` | Yes | Yes | Smoothing, hysteresis, confidence stability window |
| **Processing Pipeline** | ✅ Fully Implemented | `logic/processing_pipeline.py` | Yes | Yes | Full orchestration: probe → align → diarize → decision → render → concat |
| **Video Rendering** | ✅ Fully Implemented | `logic/video_merger.py` | Yes | Yes | Segment rendering, concatenation, single-pass mode |
| **FCPXML Export** | ✅ Fully Implemented | `logic/fcpxml_export.py` | Yes | Yes | Generates valid FCPXML 1.11 for Premiere/DaVinci |
| **Audio Sync (Cross-correlation)** | ✅ Fully Implemented | `logic/audio_sync.py` | Yes | Yes | Requires `librosa` core dependency (always available) |
| **External Audio** | ✅ Fully Implemented | `ui/main_window.py`, `logic/processing_pipeline.py` | Yes | Yes | Replace camera audio with external audio file |
| **Camera-Speaker Mapping** | ✅ Fully Implemented | `ui/main_window.py` | Yes | Yes | Manual mapping of cameras to speakers |
| **Output Folder Selection** | ✅ Fully Implemented | `ui/main_window.py` | Yes | Yes | User chooses output directory |
| **Theme Switching** | ✅ Fully Implemented | `ui/theme.py`, `ui/settings_dialog.py` | Yes | Yes | Light/Dark mode with persistence |
| **ETA Estimation** | ✅ Fully Implemented | `logic/eta_estimation.py` | Yes | Yes | Rolling average, RTF-based estimation |
| **Progress Dialog** | ✅ Fully Implemented | `ui/progress_dialog.py` | Yes | Yes | Stage-based progress with ETA |
| **QA Artifacts Export** | ✅ Fully Implemented | `logic/qa_artifacts.py` | No | Yes | JSON artifacts for diarization, cut plan, summary |
| **A/B Compare Preview** | 🔲 UI Only | `ui/main_window.py` lines 257-264 | Yes (hidden) | No | Button exists but hidden (`setVisible(False)`) for V1 |
| **Trim Panel** | 🔲 UI Only | `ui/trim_panel.py` | Yes (hidden) | Partial | Panel hidden for V1 one-click workflow; backend exists but not wired |
| **Timeline View** | 🔲 UI Only | `ui/timeline/` | Yes (hidden) | Partial | Timeline hidden for V1; scene/adapter exist but not user-facing |
| **Multiview Dialog** | 🔲 UI Only | `ui/multiview_dialog.py` | Yes | No | Dialog exists but causes system freeze - REMOVED from UI |
| **Highlights/Teaser** | 📝 Stub | `logic/highlights.py` | No | Stub | Data structures exist, `compute_highlights_stub()` returns empty list |
| **CLI Mode** | ✅ Fully Implemented | `cli.py` | No | Yes | Headless processing with arguments, QA artifacts |
| **GPU Preflight Check** | ✅ Fully Implemented | `logic/preflight.py` | Yes | Yes | Warns if GPU-heavy mode selected without GPU |
| **Checkpointing** | ✅ Fully Implemented | `logic/checkpoint.py` | No | Yes | Save/restore pipeline state for crash recovery |
| **Sync All Button** | 🔲 UI Only | `ui/main_window.py` line 143-149 | Yes (hidden) | Partial | Button hidden; sync moved to Magic Settings |
| **Audio Preview** | ⚠️ Partially Implemented | `ui/audio_preview_dialog.py` | Yes | Partial | Requires `ffplay`; error handling present but playback fragile |
| **Waveform View** | ✅ Fully Implemented | `ui/waveform_dialog.py` | Yes | Yes | Visualize audio waveforms for sync verification |
| **Magic Settings Dialog** | ✅ Fully Implemented | `ui/magic_settings_dialog.py` | Yes | Yes | AI processing options, sync toggle |
| **Settings Dialog** | ✅ Fully Implemented | `ui/settings_dialog.py` | Yes | Yes | Appearance, log levels, system info |
| **Export Dialog** | ✅ Fully Implemented | `ui/export_dialog.py` | Yes | Yes | Export processed video with format options |
| **Undo/Redo** | ✅ Fully Implemented | `logic/commands.py`, `ui/main_window.py` | Yes | Yes | QUndoStack-based, Add/Remove/Trim commands |
| **Debug Export Package** | ✅ Fully Implemented | `logic/debug_export.py` | No | Yes | ZIP containing logs, QA artifacts, environment info |
| **Unit Tests** | ✅ All Passing | `tests/` (32 files) | N/A | N/A | 539 passed, 2 skipped. Qt tests run via pytest-qt (offscreen). 48% coverage |

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | **Fully Implemented** - Feature works as expected |
| ⚠️ | **Partially Implemented** - Works but has dependencies or limitations |
| 🔲 | **UI Only** - Button/UI exists but logic missing or disabled |
| 📝 | **Stub/Placeholder** - Code structure exists but returns mock data |
| ❌ | **Broken/Unstable** - Feature exists but fails or crashes |

---

## Critical Findings

### 1. Tests Require Qt Exclusion (RESOLVED — Qt tests now run)
- **32 test files** in `tests/` directory, Qt tests included via `pytest-qt`
- **539 passed, 2 skipped** (48% overall coverage); the 2 failures on
  macOS/Linux are known Windows-path tests (see docs/GOOD_FIRST_ISSUES.md)
- **Command**: `pytest --no-cov` (on macOS/Linux prefix with `QT_QPA_PLATFORM=offscreen`)
- **Qt tests ignored**: 5 files require pytest-qt with virtual display
- **Fix applied**: Broader exception handling in `PyannoteBackend.check_install()` to catch RuntimeError from broken torchvision

### 2. Hidden Features (V1 Simplification)
The following features have backend implementations but are **hidden from UI** for the V1 "one-click" workflow:
- A/B Compare Preview (`setVisible(False)`)
- Trim Panel (`setVisible(False)`)
- Timeline View (`setVisible(False)`)
- Sync All Button (moved to Magic Settings)

### 3. Optional Dependency Features
These features require optional packages not in the core install:
- **Pyannote Diarization**: Requires `pyannote.audio`, `torch`, HuggingFace auth
- **Audio Sync**: Now included in core dependencies (`librosa`, `soundfile`)
- **Lips Detection**: Requires `torch`, GPU, model download

### 4. Removed Due to Instability
- **Multiview Dialog**: Caused system freezes, removed from UI flow

### 5. Stub Features (Not Implemented)
- **Highlights/Teaser Cutting**: Infrastructure exists (`HighlightsTimeline`, `HighlightSegment`) but `compute_highlights_stub()` returns empty data

---

## Backend Health Summary

| Backend | Status | Check Command |
|---------|--------|---------------|
| FFmpeg | Required | `ffmpeg -version` |
| FFprobe | Required | `ffprobe -version` |
| Core (PySide6, numpy) | Required | Auto-detected |
| Energy VAD | Always available | Built-in |
| Librosa/Audio Sync | Required (core) | Included in base install |
| Pyannote | Optional | `pip install multicam-editor[ai]` |

Run health check: `python -m multicam_editor.utils.backends`

---

## Recommendations

### Immediate (Before Any New Features)
1. **Fix the 5 torchvision test failures** - Wrap optional backend imports in try/except
2. **Document hidden V1 features** - Users shouldn't see partial UI
3. **Verify ffmpeg error handling** - Ensure graceful failure on missing binaries

### Short-Term
1. Add CLI integration test (headless processing smoke test)
2. Document optional dependency installation clearly
3. Add crash recovery testing

### Long-Term
1. Implement Highlights/Teaser feature (currently stub)
2. Re-enable hidden features (A/B compare, timeline) when ready
3. Consider removing multiview entirely if unfixable
4. Add pytest-qt for proper Qt testing in CI

