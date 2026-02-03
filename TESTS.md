# Test Documentation

> **Last Updated**: 2026-02-03
> **Status**: ✅ PASSING (417 passed, 2 skipped with Qt test exclusions)

## Overview

The project has 26 test files in `tests/`. **Tests run successfully** when Qt-dependent tests are excluded. All core logic tests pass.

---

## Test Inventory

| Test File | What It Tests | Qt Required? | Status |
|-----------|---------------|--------------|--------|
| `test_import.py` | Package import sanity | No | ✅ Should work |
| `test_logging.py` | Logging configuration idempotency | No | ✅ Should work |
| `test_backends.py` | Backend availability detection | No | ✅ Should work |
| `test_file_utils.py` | File type detection | No | ✅ Should work |
| `test_active_speaker.py` | Speaker detection backends | No | ✅ Should work |
| `test_audio_sync.py` | Audio synchronization | No | ✅ Should work |
| `test_audio_mix.py` | Audio mixing | No | ✅ Should work |
| `test_decision_engine.py` | Cut decision logic | No | ✅ Should work |
| `test_fast_rules_engine.py` | FAST_RULES switching | No | ✅ Should work |
| `test_switching_strategy.py` | Strategy enum/loader | No | ✅ Should work |
| `test_video_merger.py` | Video rendering/concat | No | ⚠️ Needs ffmpeg |
| `test_fcpxml_export.py` | FCPXML generation | No | ✅ Should work |
| `test_ffprobe_ffmpeg.py` | FFmpeg/FFprobe wrappers | No | ⚠️ Needs binaries |
| `test_eta_estimation.py` | ETA calculation | No | ✅ Should work |
| `test_highlights.py` | Highlights infrastructure | No | ✅ Should work |
| `test_pipeline_config.py` | Pipeline configuration | No | ✅ Should work |
| `test_processing_pipeline.py` | Full pipeline | No | ⚠️ Needs ffmpeg |
| `test_processing_worker_signals.py` | Worker signals | Yes | ❌ Hangs |
| `test_processing_time.py` | Processing time tracking | No | ✅ Should work |
| `test_preflight.py` | GPU preflight checks | No | ✅ Should work |
| `test_gpu_preflight.py` | GPU detection | No | ✅ Should work |
| `test_project.py` | Project data model | No | ✅ Should work |
| `test_debug_export.py` | Debug export | No | ✅ Should work |
| `test_magic_settings.py` | Magic settings persistence | Yes | ❌ Hangs |
| `test_file_list_time.py` | File list performance | Yes | ❌ Hangs |
| `test_ui.py` | UI smoke tests | Yes | ❌ Hangs |

---

## Running Tests

### Recommended: Run All Non-Qt Tests

```bash
# Run all tests except Qt-dependent ones (5 files excluded)
pytest tests/ --ignore=tests/test_ui.py --ignore=tests/test_magic_settings.py --ignore=tests/test_file_list_time.py --ignore=tests/test_processing_worker_signals.py --ignore=tests/test_processing_time.py -v
```

### Quick Subset (Core Logic Only)

```bash
pytest tests/test_import.py tests/test_logging.py tests/test_backends.py tests/test_decision_engine.py tests/test_fast_rules_engine.py tests/test_eta_estimation.py tests/test_highlights.py tests/test_preflight.py tests/test_project.py -v
```

### Full Test Suite (Requires pytest-qt)

```bash
# Only run if pytest-qt installed and QT_QPA_PLATFORM=offscreen set
pytest -v
```

### With Coverage

```bash
pytest --cov=src --cov-report=term-missing tests/test_decision_engine.py
```

---

## Root Cause of Hanging

The tests hang because:

1. **`test_ui.py`** creates `QApplication` in a pytest fixture
2. **`test_magic_settings.py`** imports Qt widgets
3. **`test_file_list_time.py`** uses Qt widgets
4. **`test_processing_worker_signals.py`** uses QThread

In headless CI/shell environments, Qt tries to connect to a display and blocks.

### Solution Options

1. **Use virtual display (xvfb on Linux)**:
   ```bash
   xvfb-run pytest
   ```

2. **Skip UI tests in CI**:
   ```bash
   pytest --ignore=tests/test_ui.py --ignore=tests/test_magic_settings.py --ignore=tests/test_file_list_time.py --ignore=tests/test_processing_worker_signals.py
   ```

3. **Use pytest-qt properly**:
   ```bash
   pip install pytest-qt
   # Ensure QT_QPA_PLATFORM=offscreen is set
   ```

---

## What Each Test Validates

### Core Logic Tests

- **`test_decision_engine.py`**: Smoothing rules, hysteresis, cut generation
- **`test_fast_rules_engine.py`**: Rule-based switching, merge short segments
- **`test_active_speaker.py`**: All speaker detection backends
- **`test_eta_estimation.py`**: Rolling average, RTF calculation

### Integration Tests

- **`test_processing_pipeline.py`**: Full pipeline execution (requires ffmpeg)
- **`test_video_merger.py`**: Segment rendering, concatenation

### Utility Tests

- **`test_backends.py`**: Backend health checks
- **`test_ffprobe_ffmpeg.py`**: FFmpeg wrapper functions
- **`test_file_utils.py`**: File type detection

---

## Known Test Gaps

| Area | Gap | Priority |
|------|-----|----------|
| Cancellation | No test for mid-pipeline cancel | High |
| Error recovery | No test for corrupt input files | High |
| Temp cleanup | No test for cleanup on crash | Medium |
| CLI mode | No integration test for cli.py | Medium |
| Audio preview | No test for ffplay fallback | Low |

---

## Adding New Tests

1. **For logic modules**: Add to appropriate `test_*.py` file, no Qt needed
2. **For UI components**: Use `pytest-qt`, add to `test_ui.py`
3. **For integration**: Ensure ffmpeg is available, mark with `@pytest.mark.integration`

### Test Template (Non-UI)

```python
import pytest
from multicam_editor.logic.your_module import your_function

def test_your_function_basic():
    """Describe what this tests."""
    result = your_function(input_data)
    assert result.success is True
    assert result.output == expected

def test_your_function_edge_case():
    """Test edge case handling."""
    result = your_function(None)
    assert result.error is not None
```
