# Architecture Document

> **Version**: 1.1  
> **Last Updated**: 2026-02-11  
> **Status**: ALIGNED WITH REALITY

## Overview

Zelqivo (formerly MultiCamEditor) is a PyQt6-based desktop application for automated multicam video editing. The core workflow:

1. **Import** multiple camera video files
2. **Analyze** audio to detect active speaker per time window
3. **Decide** which camera to show based on speaker detection
4. **Render** the final video by cutting between cameras
5. **Export** to MP4 or FCPXML for NLE import

---

## Module Responsibilities

### Entry Points

| Module | Purpose | Notes |
|--------|---------|-------|
| `main.py` | GUI entry point | Creates QApplication, MainWindow |
| `cli.py` | Headless CLI mode | For automation/QA pipelines |
| `__main__.py` | Package runner | `python -m multicam_editor` |
| `logging_setup.py` | Centralized logging config | Console + rotating file handler |

### Core Layer (`core/`)

| Module | Purpose |
|--------|---------|
| `project.py` | Data model for clips, timeline, undo/redo state |

### Logic Layer (`logic/`)

| Module | Purpose | Status |
|--------|---------|--------|
| `processing_pipeline.py` | **Main orchestrator**: probe → align → diarize → decision → render → concat | ✅ Complete |
| `active_speaker.py` | Speaker detection backends (OFF, STUB, ENERGY, REAL, LIPS, HYBRID) | ⚠️ Some backends need optional deps |
| `decision_engine.py` | Convert speaker segments to camera cuts with smoothing | ✅ Complete |
| `fast_rules_engine.py` | Rule-based camera switching (no ML) | ✅ Complete |
| `video_merger.py` | Render video segments, concatenate | ✅ Complete |
| `audio_sync.py` | Cross-correlation audio alignment | ✅ Complete (librosa is core dep) |
| `fcpxml_export.py` | Generate FCPXML 1.11 for NLE import | ✅ Complete |
| `highlights.py` | Teaser cutting infrastructure | 📝 STUB |
| `preflight.py` | GPU preflight checks, warning dialogs | ✅ Complete |
| `eta_estimation.py` | Rolling average ETA calculation | ✅ Complete |
| `checkpoint.py` | Pipeline crash recovery | ✅ Complete |
| `qa_artifacts.py` | Export JSON artifacts for QA | ✅ Complete |
| `commands.py` | Undo/Redo commands (Add, Remove, Trim) | ✅ Complete |
| `processing_worker.py` | QThread wrapper for async processing | ✅ Complete |
| `switching_strategy.py` | Strategy enum and loader | ✅ Complete |
| `video_utils.py` | Video/audio helpers (extract, duration, split) | ✅ Complete |
| `debug_export.py` | Debug package ZIP export for QA/support | ✅ Complete |
| `pipeline_config.py` | Pipeline configuration dataclass | ✅ Complete |

### UI Layer (`ui/`)

| Module | Purpose | Status |
|--------|---------|--------|
| `main_window.py` | Main application window (1955 lines) | ✅ Active |
| `file_list_widget.py` | Video file list with drag-drop | ✅ Active |
| `video_preview.py` | Video playback preview | ✅ Active |
| `progress_dialog.py` | Processing progress with ETA | ✅ Active |
| `settings_dialog.py` | App settings (theme, logs) | ✅ Active |
| `magic_settings_dialog.py` | AI processing options | ✅ Active |
| `export_dialog.py` | Export format options | ✅ Active |
| `loading_dialog.py` | File loading progress | ✅ Active |
| `gpu_warning_dialog.py` | GPU preflight warnings | ✅ Active |
| `waveform_dialog.py` | Sync verification waveforms | ✅ Active |
| `audio_preview_dialog.py` | Audio playback (ffplay) | ⚠️ Fragile |
| `theme.py` | Light/Dark theme system | ✅ Active |
| `custom_title_bar.py` | Frameless window title bar | ✅ Active |
| `trim_panel.py` | Manual trim controls | 🔲 Hidden V1 |
| `timeline/` | Timeline view components | 🔲 Hidden V1 |
| `multiview_dialog.py` | Multi-camera preview | ❌ Removed (freeze bug) |
| `utils/gui.py` | GUI threading helpers | ✅ Active |
| `widgets/range_slider.py` | Custom range slider widget | ✅ Active |
| `widgets/processing_options.py` | Processing options widget | ✅ Active |

### Utils Layer (`utils/`)

| Module | Purpose |
|--------|---------|
| `ffmpeg.py` | FFmpeg wrapper with cancellation | ✅ Complete |
| `ffprobe.py` | Cached metadata probing | ✅ Complete |
| `backends.py` | Health check, backend availability | ✅ Complete |
| `file_utils.py` | File type detection | ✅ Complete |
| `settings.py` | QSettings wrapper | ✅ Complete |
| `signals.py` | Processing signals | ✅ Complete |

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          ProcessingPipeline                             │
├─────────────────────────────────────────────────────────────────────────┤
│  Stage 1: PROBE                                                         │
│  └─ ffprobe.probe() → duration, fps, resolution per video              │
│                                                                         │
│  Stage 2: ALIGN (optional)                                              │
│  └─ audio_sync.align_cameras() → offset_ms per camera                  │
│                                                                         │
│  Stage 3: DIARIZE                                                       │
│  └─ active_speaker.diarize() → List[SpeakerSegment]                    │
│     ├─ EnergyVADBackend (CPU, always available)                        │
│     ├─ RealDiarizationBackend (pyannote, optional)                     │
│     └─ LipsBackend (torch, optional, GPU)                              │
│                                                                         │
│  Stage 4: DECISION                                                      │
│  └─ decision_engine.generate_cut_plan() → List[CutSegment]             │
│     └─ Smoothing: stability window, hysteresis, min clip length        │
│                                                                         │
│  Stage 5: RENDER                                                        │
│  └─ video_merger.render_segments() → temp MP4 segments                 │
│                                                                         │
│  Stage 6: CONCAT                                                        │
│  └─ video_merger.concatenate_segments() → final output MP4            │
│                                                                         │
│  Output: PipelineResult { success, output_path, speaker_segments }     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Error Handling Strategy

### Current Implementation

1. **FFmpeg/FFprobe failures**: Return `ProbeResult.error` or `FFmpegResult.error` - no exceptions
2. **Missing audio streams**: `has_audio_stream()` check, fallback to stub segments
3. **Cancellation**: `_cancelled` flag checked between stages, cleanup on cancel
4. **Temp file cleanup**: `_cleanup()` method with retry logic for locked files
5. **Optional dependencies**: Graceful fallback when pyannote/librosa unavailable

### Gaps (Needs Improvement)

- Silent exception swallowing in some UI callbacks
- No structured error codes for CLI mode
- Some long operations block UI thread (should use QThread)

---

## Temp File Management

| Component | Temp Location | Cleanup |
|-----------|---------------|---------|
| Audio WAV extraction | System temp | `_cleanup()` after pipeline |
| Rendered segments | System temp | `_cleanup()` after concat |
| Sync preview files | System temp | `_cleanup_sync_state()` on remove |

**Risk**: Crash during processing may leave orphan temp files.

---

## Where Logic Is Incomplete

| Area | Current State | Missing |
|------|--------------|---------|
| Highlights/Teaser | Data structures exist | Actual detection algorithm |
| Lips Detection | Backend exists | Model download UX, error handling |
| Audio Preview | ffplay-based | Proper error feedback if ffplay missing |
| A/B Compare | UI hidden | Integration with comparison logic |
| Timeline Editing | Components exist | User-facing workflow |

---

## Safe Extension Points

To add new features safely:

1. **New diarization backend**: Implement `DiarizationBackend` protocol, register in `get_backend()`
2. **New switching strategy**: Add to `SwitchingStrategy` enum, handle in `_load_switching_strategy()`
3. **New export format**: Add alongside `fcpxml_export.py`, wire to export dialog
4. **New UI dialog**: Follow pattern of `magic_settings_dialog.py` (modal, non-blocking)

---

## Dependencies

### Required (Core Install)
- Python 3.10+
- PyQt6, pyqt6-sip
- numpy, opencv-python
- ffmpeg-python, moviepy
- librosa, soundfile (audio sync)
- tqdm (progress bars)
- FFmpeg/FFprobe binaries

### Optional (AI Install)
- torch (for LIPS mode)
- pyannote.audio (for real diarization)
- pydub, speechbrain

---

## Known Technical Debt

1. **Qt tests hang** on initialization without `pytest-qt` + virtual display (5 test files excluded)
2. **Multiview dialog** causes system freeze - removed from UI but code file remains
3. **Some UI hidden for V1** - trim panel, timeline, A/B compare
4. **Highlights stub** returns empty data - infrastructure without implementation
5. **Overall test coverage at 35%** - core logic well tested, UI layer largely untested
