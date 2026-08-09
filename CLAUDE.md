# Zelqivo — rules for AI-assisted development

Read `CONTRIBUTING.md` first; it defines setup, tests, style, and what gets
merged. These are the additional hard rules for any AI coding assistant
(Claude, Cursor, Copilot, ...) working in this repo.

## Architecture (non-negotiable)

- `core/project.py` `Project` is the single source of truth: clips list,
  ordering, trims, `clip_id`. Timeline and File List always mirror Project
  order — never keep independent ordering.
- Every user action that changes Project state must be undoable via
  `QUndoStack` commands.
- Undo command vocabulary: `AddClipsCommand` / `RemoveClipsCommand` /
  `ReorderClipsCommand` (clip_id list) / `TrimCommand` (coalesce drags) /
  `SplitCommand` (merge on undo).
- No silent `except Exception: pass` — catch the specific exception and
  `logger.debug(..., exc_info=True)`, or let it propagate.

## Guardrails (always)

- Trim: clamp to duration; in/out cannot cross; equal allowed.
- Split: forbidden at 0 ms or at duration; `MIN_SEGMENT_MS = 100`.
- Invalid user action → non-blocking status toast, never a modal.
- Never allow duplicate clips or a broken selection.

## FFmpeg / probing

- All ffmpeg/ffprobe access goes through `utils/ffmpeg.py` and
  `utils/ffprobe.py` wrappers — never call the binaries directly elsewhere.
- Cache probe results by `(path, mtime)`.
- Every subprocess must support cancel + cleanup of temp files.
- Validate ffmpeg/ffprobe presence and fail with a clear message, never a crash.
- No GPL dependencies or GPL ffmpeg builds — licensing depends on it
  (see `docs/THIRD_PARTY.md`).

## Scope discipline

- One change set per task, PR-sized, minimum files touched.
- No new runtime dependencies without prior agreement in an issue.
- Do not modify the switching engine (`logic/decision_engine.py`,
  `logic/fast_rules_engine.py`, `logic/active_speaker.py`) without an
  explicit issue discussing the change — that is the product.
- Never hide unfinished features behind `setVisible(False)` — finish or drop.
- If user-visible behavior changes, update `docs/FEATURE_REALITY.md` (the
  repo's honesty contract) and `CHANGELOG.md` in the same change.

## Gate before claiming "done"

```bash
# macOS/Linux (Windows: omit the env var)
QT_QPA_PLATFORM=offscreen pytest --no-cov
```

- Baseline: 539 passed; 2 pre-existing failures on macOS/Linux
  (`test_file_utils`, `test_qa_artifacts` Windows-path cases). No NEW failures.
- pytest quirk: `pyproject.toml` addopts already include `-q` — adding another
  `-q` silences the final summary line.
- Lint/format/type-check your changed lines (`black`, `ruff`, `mypy` — configs
  in `pyproject.toml`); do not reformat untouched files.
- GUI-affecting change? Smoke it: launch → add 2 videos → preview →
  seek → undo/redo → quit.
