# Phase 0.2 Execution Plan — FFmpeg: GPL → LGPL + encoder selection
> For the executing Claude (Opus) session. Read `WORK_ORDER.md` Phase 0.2 for the *why*;
> this file is the *how*, with facts verified against the repo as of commit `095cb55`
> (Phase 0.1, PySide6 migration — DONE, merged to DEV). Follow the global CLAUDE.md
> protocol (SQUAD loop, BRIEF reports, stop conditions). Stop for Roman's review at the end.

## 0. Environment bootstrap (macOS dev box; Windows build box is Roman's)
```bash
python3.12 -m venv .venv                      # NOT 3.14 — PySide6 wheels lag
.venv/bin/pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen .venv/bin/pytest --no-cov   # expect: 2 failed, 554+ passed
```
Gate quirks — memorize before running anything:
- `pyproject.toml` addopts already has `-q --cov`. Adding `-q` on the CLI = `-qq` = the
  final summary line is suppressed. Use `--no-cov` for speed.
- **Pre-existing failures — do NOT fix, do NOT count against your work**
  (all reproduced on unmodified DEV with identical tool versions):
  ruff 203 errors · black would reformat 79 files · mypy 104 errors (57 + 47 static-only
  PySide6-stub visibility) · 2 pytest failures on macOS (`test_file_utils.py` safe_basename,
  `test_qa_artifacts.py` windows_path — Windows-path tests, Phase 6.1 scope).
  Your acceptance bar: **zero NEW violations, zero NEW failures.** Compare against these numbers.
- macOS has no `timeout`; wrap launch smoke tests in a Python `subprocess` driver.
- Do not touch `logic/decision_engine.py`, `logic/fast_rules_engine.py`,
  `logic/active_speaker.py` switching maths (WORK_ORDER rule 5).

## 1. Verified call-site map (re-verify with grep before editing; drift = re-audit)
| What | Where |
|---|---|
| `"-c:v", "libx264"` — the ONLY 5 encoder sites | `utils/ffmpeg.py:348, 454, 643, 788` · `logic/video_merger.py:444` |
| FFmpeg discovery (module-cached) | `utils/ffmpeg.py` `_find_ffmpeg()` ~line 41: bundled → PATH → Windows common paths. Twin in `utils/ffprobe.py` |
| Hardcoded GPL FFmpeg path | `build_exe.ps1:18` (comment) and `:86`; `multicam_editor.spec:74-75` |
| QSettings usage pattern to copy | `ui/settings_dialog.py` / `ui/main_window.py` — always `value(key, default, type=X)`; coercion is locked by `tests/test_settings_roundtrip.py` |

## 2. Slices (SQUAD: one slice = code + its test in the same edit, PROVE, then next)

### Slice A — `select_h264_encoder()` helper + tests
In `utils/ffmpeg.py` (next to `_find_ffmpeg`, same module-level-cache pattern):
```python
def select_h264_encoder(prefer_hardware: bool = True) -> tuple[str, list[str]]:
    """Return (encoder_name, quality_args), probing `ffmpeg -encoders` once (cached).
    Preference: h264_nvenc > h264_qsv > h264_amf > h264_videotoolbox > libopenh264
    > libx264 (libx264 only if present in the user's own ffmpeg — never bundled).
    """
```
- Probe: `subprocess.run([ffmpeg, "-hide_banner", "-encoders"])`, parse encoder names from
  output lines; cache result module-level; `logger.info` the chosen encoder.
- Quality args per encoder (visually ~CRF 23 parity; verify each against ffmpeg docs and
  PRESERVE the exact `-crf`/`-preset` values currently at each call site for libx264):
  libx264 → existing site flags · libopenh264 → `["-b:v", "6M"]` (no CRF support — note
  quality caveat in docstring) · h264_nvenc → `["-rc", "vbr", "-cq", "23", "-preset", "p4"]`
  · h264_qsv → `["-global_quality", "23"]` · h264_amf → `["-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]`
  · h264_videotoolbox → `["-q:v", "55"]`
- `prefer_hardware=False` → skip straight to software encoders (needed for the test matrix
  and as a QSettings-backed user override later).
- Tests (`tests/test_encoder_selection.py`): mock the `-encoders` probe output for each
  vendor case (NVIDIA-only, Intel-only, AMD-only, macOS/videotoolbox, openh264-only,
  everything-available → nvenc wins, nothing-but-x264 → x264, empty → raise/clear error).
  Assert the probe runs once (cache). Mutation-check: break the preference order on purpose,
  confirm the test fails, restore (SQUAD lesson 6).

### Slice B — replace the 5 call sites
- Each site: replace literal `"-c:v", "libx264"` + its x264-specific quality flags with the
  helper's `(encoder, args)`. Read each site's full command list first — `-crf`/`-preset`
  move INTO the helper's libx264 branch so behavior is identical when x264 is chosen.
- Surface the chosen encoder in the QA artifacts summary (`logic/qa_artifacts.py`).
- PROVE: full suite + a real tiny encode on this machine:
  `ffmpeg -f lavfi -i testsrc=duration=2 -f lavfi -i sine=duration=2 in.mp4` × 2, run the
  pipeline, assert output probes playable (this is also Phase 4.4's CLI e2e seed — write it
  as `tests/test_encoder_e2e.py` marked `integration` if a CLI entry exists, else a script).

### Slice C — "Use my own FFmpeg" escape hatch
- QSettings key `ffmpeg/custom_path` (string, default ""). Step **0** in `_find_ffmpeg()`
  AND `ffprobe`'s twin: if set and the file exists, use it (and derive ffprobe via
  `Path(p).with_name(...)` — do NOT use `str.replace`, see WORK_ORDER 6.1.3).
- Settings dialog: path picker row + "clear" (copy an existing row's pattern). If the user's
  ffmpeg has libx264, the helper naturally selects it — that is the whole feature.
- Test: monkeypatched QSettings temp-INI pointing at a fake ffmpeg script that echoes an
  `-encoders` list containing libx264 → helper returns libx264.

### Slice D — build scripts + docs
- `build_exe.ps1`: read `$env:ZELQIVO_FFMPEG_DIR`, fail with a clear message naming the env
  var and the expected BtbN `*-lgpl` build if unset/missing. Kill both hardcoded mentions
  (`:18`, `:86`). Same env var in `multicam_editor.spec:74-75` via `os.environ.get`, with the
  existing "not found" warning path kept.
- Start `docs/THIRD_PARTY.md` with the FFmpeg section only (full manifest is Phase 0.3):
  bundled BtbN LGPL build URL + SHA-256 (Roman downloads on the Windows box; leave a
  `TODO(roman): checksum` placeholder), plus the TWO other FFmpeg copies already in the tree:
  Qt Multimedia's own **FFmpeg 7.1.3 LGPL** (observed in app log at launch) and
  `imageio_ffmpeg`'s fallback binary bundled by `multicam_editor.spec:66-71` — verify its
  license flavor (`imageio_ffmpeg` ships GPL builds by default!) and if GPL, EXCLUDE it from
  the spec datas and record that decision here.
- `CHANGELOG.md` under `[Unreleased]`.

## 3. Frozen acceptance list (ACCEPT gate runs in a fresh subagent, per SQUAD)
1. `grep -rn '"libx264"' src/` → only inside `select_h264_encoder`'s preference table.
2. Encoder tests cover all 6 vendors + cache + empty-probe; suite green (no NEW failures vs §0 baselines).
3. Custom-ffmpeg QSettings override works, tested, and ffprobe derivation uses path surgery not `str.replace`.
4. `build_exe.ps1` + spec have zero hardcoded `C:\ffmpeg...` strings; env-var driven; clear failure message.
5. `docs/THIRD_PARTY.md` exists listing all three FFmpeg copies with license + disposition.
6. Real 2-video encode on a machine WITHOUT libx264 preference produces a playable MP4 (paste ffprobe of output).
7. QA artifacts summary names the chosen encoder.

## 4. Report + stop
WORK_ORDER report format (max 40 lines), gate outputs pasted, then STOP for Roman's review
before Phase 0.3. Recommend effort tier for 0.3 (docs/legal-heavy → Medium/High).
Commit message: `feat: runtime H.264 encoder selection, LGPL FFmpeg builds, custom-ffmpeg override`.
