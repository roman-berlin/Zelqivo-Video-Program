# V1 QA Test Guide — Podcast Multicam Export

This document is for manual QA testing of the V1 core features:
1. **Speaker diarization-driven switching**
2. **External audio sync + replace**
3. **Export correctness**

---

## 1. Preconditions

### 1.1 ffmpeg / ffprobe
- **Required:** Both `ffmpeg` and `ffprobe` must be in PATH or standard locations.
- **Verify:** Run in terminal:
  ```cmd
  ffprobe -version
  ffmpeg -version
  ```
- If missing: download from https://ffmpeg.org/download.html, extract to `C:\ffmpeg\bin\` and add to PATH.

### 1.2 Pyannote Model (REAL mode only)
- Model auto-downloads on first run (~500MB to `~/.cache/torch/pyannote/`).
- **Auth:** Some models require HuggingFace token:
  ```cmd
  huggingface-cli login
  ```
  Or set `HF_TOKEN` environment variable.
- **Fallback:** If model fails to load, app falls back to STUB (energy VAD). Check logs for warning.

### 1.3 Codec Notes
| Container | Recommended Codec | Notes |
|-----------|-------------------|-------|
| `.mp4` | H.264/AAC | Best compatibility |
| `.mov` | H.264/AAC | Works on Windows with proper codecs |
| `.wav` | PCM | For external audio |
| `.mp3` | MP3 | Supported for external audio |

**Warning:** Some H.265/HEVC files may fail preview but diarization/export still work via ffmpeg.

---

## 2. Test Data Preparation

### 2.1 Recommended Test Media

| File | Description | Purpose |
|------|-------------|---------|
| `2speakers_clean.mp4` | 2 speakers, clear turns, no overlap | Baseline diarization |
| `2speakers_interruptions.mp4` | Short background remarks (<500ms) | Test bg_short_remark rule |
| `overlapping_speech.mp4` | Speakers talking over each other | Overlap handling |
| `camera_a.mp4` + `camera_b.mp4` | Synced multi-cam recording | Multi-video export |
| `external_audio.wav` | High-quality separate recording | Audio sync test |
| `external_audio_offset.wav` | Same as above but offset by +/-500ms | Offset correction test |

### 2.2 How to Prepare Test Files
1. Record or obtain 2-3 minute podcast clip with 2 speakers.
2. Create variants:
   - **Clean:** Each speaker talks in clear turns (2-5 seconds per turn).
   - **Interruptions:** Add short "uh-huh", "yeah" comments (<500ms).
   - **Overlap:** Speakers talk simultaneously for 1-2 seconds.
3. For external audio: Record same content on separate device, introduce known offset (trim/pad in Audacity).

---

## 3. Manual Test Cases

### TC-01: Two Speakers Clean Audio
**Goal:** Verify basic diarization correctly identifies speaker turns.

**Steps:**
1. Launch app: `python -m multicam_editor`
2. Add 2 video files (one per speaker/camera) via "Add Videos"
3. Open Settings → Diarization Mode = REAL (or STUB for quick test)
4. Click Export → Start processing
5. Wait for completion

**Expected Results:**
- [ ] `diarization.json` shows 2 speakers (`speaker_0`, `speaker_1`)
- [ ] Segments alternate between speakers matching actual speech
- [ ] `cut_plan.json` shows camera switches at speaker changes
- [ ] No cuts during short pauses (<600ms)
- [ ] Exported video shows correct camera for each speaker

**Pass Criteria:** 90%+ of speaker turns correctly identified and switched.

---

### TC-02: Short Interruptions (Background Remark Rule)
**Goal:** Verify short remarks (<500ms) do NOT trigger camera switch.

**Steps:**
1. Load video with short interruptions (e.g., "uh-huh", "right")
2. Process with default thresholds:
   - `bg_short_remark_ms = 500`
   - `min_speech_ms = 600`
3. Export and check artifacts

**Expected Results:**
- [ ] Short remarks appear in `diarization.json` but are filtered in cut plan
- [ ] `cut_plan.json` entries have `reason: "threshold"` for skipped segments
- [ ] Camera stays on main speaker during brief interruptions
- [ ] Log shows: `filtered X segments below bg_short_remark_ms`

**Pass Criteria:** No camera switch for remarks under 500ms.

---

### TC-03: Overlapping Speech
**Goal:** Verify overlap handling doesn't crash and produces reasonable output.

**Steps:**
1. Load video where speakers overlap for 1-2 seconds
2. Process with REAL diarization
3. Check `diarization.json` and `cut_plan.json`

**Expected Results:**
- [ ] No crash during diarization
- [ ] Overlapping segments merged (PyannoteBackend._merge_overlaps)
- [ ] Camera defaults to current speaker during overlap
- [ ] `processing_summary.json` shows correct segment count
- [ ] Exported video doesn't have jarring cuts during overlap

**Pass Criteria:** Stable processing; prefer current camera during overlap.

---

### TC-04: External Audio Missing
**Goal:** Verify graceful handling when external audio file doesn't exist.

**Steps:**
1. In Export dialog, enable "Use External Audio"
2. Enter path to non-existent file: `C:\nonexistent\audio.wav`
3. Start export

**Expected Results:**
- [ ] Error message shown: "File not found: C:\nonexistent\audio.wav"
- [ ] Processing continues with embedded audio OR aborts cleanly
- [ ] No crash
- [ ] Log shows: `External audio not found: ...`
- [ ] `processing_summary.json` shows `external_audio_sync.success = false`

**Pass Criteria:** Non-blocking error; no crash.

---

### TC-05: External Audio Offset Scenario
**Goal:** Verify cross-correlation correctly detects and corrects offset.

**Steps:**
1. Prepare external audio with known offset (+500ms or -500ms from video)
2. Load video files
3. Enable "Use External Audio" with the offset file
4. Process and export

**Expected Results:**
- [ ] Log shows: `Detected offset: ~500 ms` (±50ms tolerance)
- [ ] `_synced.wav` file created with trimmed/padded audio
- [ ] `processing_summary.json` shows:
  ```json
  "external_audio_sync": {
    "used": true,
    "offset_ms": 500.0,
    "success": true
  }
  ```
- [ ] Exported video audio is in sync with video
- [ ] Status shows "trimmed" or "padded" based on offset direction

**Pass Criteria:** Offset detected within 100ms of actual; audio synced in export.

---

### TC-06: Export Correctness
**Goal:** Verify final export matches cut plan exactly.

**Steps:**
1. Process any test video with multiple speaker turns
2. Note `cut_plan.json` cut points (start_ms, end_ms, camera_id)
3. Play exported video and verify:
   - Camera switches at documented times (±100ms)
   - Correct camera shown for each segment
   - No audio glitches at cut points
   - Total duration matches input

**Expected Results:**
- [ ] Each cut in `cut_plan.json` visible in output video
- [ ] Camera assignments match `chosen_camera_index`
- [ ] Audio continuous (no gaps/pops at cuts)
- [ ] Output duration = input duration (±50ms)

**Pass Criteria:** 100% of cuts executed; no audio artifacts.

---

## 4. QA Artifacts for Bug Reports

When filing a bug, attach these files from `%LOCALAPPDATA%\Zelqivo\qa_runs\run_YYYYMMDD_HHMMSS\`:

| File | Description |
|------|-------------|
| `diarization.json` | Raw speaker segments from diarization |
| `cut_plan.json` | Final cut decisions with reasons |
| `processing_summary.json` | Counts, thresholds, sync info |
| Application logs | Console output (DEBUG level preferred) |

### How to Enable DEBUG Logging
```python
# In src/multicam_editor/main.py, change:
configure_logging()
# to:
configure_logging(level=logging.DEBUG)
```

### Artifact Location
```
Windows: %LOCALAPPDATA%\Zelqivo\qa_runs\
Linux:   ~/.local/share/Zelqivo/qa_runs/
```

### Bug Report Template
```
**Summary:** [One line description]

**Steps to Reproduce:**
1. ...
2. ...

**Expected:** ...
**Actual:** ...

**Attachments:**
- [ ] diarization.json
- [ ] cut_plan.json
- [ ] processing_summary.json
- [ ] Console log (DEBUG level)
- [ ] Input file info (duration, codec, resolution)

**Environment:**
- OS: Windows 11 / Ubuntu 22.04
- Python: 3.11.x
- ffmpeg: 6.x
- Diarization mode: REAL / STUB
```

---

## 5. V1 Acceptance Criteria

### Must Pass (Blocking)
| # | Criterion | Test Case |
|---|-----------|-----------|
| A1 | 2-speaker diarization produces valid segments | TC-01 |
| A2 | Short remarks (<500ms) don't trigger switch | TC-02 |
| A3 | No crash on overlap | TC-03 |
| A4 | Missing external audio handled gracefully | TC-04 |
| A5 | External audio offset detected ±100ms | TC-05 |
| A6 | Export matches cut_plan.json | TC-06 |
| A7 | QA artifacts written to run folder | All |

### Should Pass (Non-blocking for V1)
| # | Criterion | Notes |
|---|-----------|-------|
| B1 | >3 speakers detected correctly | May require tuning |
| B2 | Very long recordings (>30min) process without memory issues | Best-effort |
| B3 | HEVC/H.265 preview works | Codec dependent |

### Pass/Fail Decision
- **PASS V1:** All A1-A7 pass
- **CONDITIONAL:** 6/7 pass, 1 with documented workaround
- **FAIL:** Any A1-A6 fails, or A7 (no artifacts for debugging)

---

## 6. Quick Reference — Thresholds

| Parameter | Default | Effect |
|-----------|---------|--------|
| `min_switch_interval_ms` | 1500 | Min time between camera switches |
| `min_speech_ms` | 600 | Min speech duration to trigger switch |
| `bg_short_remark_ms` | 500 | Remarks shorter than this are ignored |
| `default_camera` | 0 | Fallback camera when uncertain |

Configurable via Settings dialog or code.

---

## 7. Diarization Mode Reference

| Mode | Backend | Use Case |
|------|---------|----------|
| OFF | NullBackend | Single camera, no switching |
| STUB | EnergyVADBackend | Dev/test without ML model |
| ENERGY | RealEnergyVADBackend | CPU-only energy-based VAD (production) |
| REAL | PyannoteBackend | ML-based diarization (requires pyannote.audio) |
| LIPS | LipsBackend | Visual lip-movement detection (requires torch + GPU) |
| HYBRID | Composite | Combines audio + visual detection |

Check logs for: `"Loaded model: pyannote/speaker-diarization-3.1"` to confirm REAL mode active.

---

*Document version: V1.1 — 2026-02-11*
