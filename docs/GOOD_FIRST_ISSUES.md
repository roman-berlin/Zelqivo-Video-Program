# Good First Issues

Welcome! This is a list of 10 small, well-defined tasks that a newcomer can finish in
an evening. Each one names the exact files and lines to touch, what to do, and how to
prove it works.

**How to claim one:** find (or open) the matching issue on GitHub and leave a comment
saying you're taking it — that stops two people from doing the same work. Then read
[CONTRIBUTING.md](../CONTRIBUTING.md) for the development setup, code style, and how
to send a pull request.

Two notes before you start:

- Run tests with `--no-cov` for speed: `python -m pytest tests/ --no-cov`
  (the project's pytest config adds coverage by default).
- Two tests currently **fail on macOS and Linux** — that is issue 6 below, not
  something you broke.

Line numbers below were checked against the `DEV` branch and may drift a little as
the code changes. If a number looks off, the function name will get you there.

---

## 1. Fix ffplay path derivation that corrupts paths containing "ffmpeg" twice

**Files:**
- `src/multicam_editor/ui/main_window.py` — lines 1786–1792 (the fix)
- `src/multicam_editor/utils/ffmpeg.py` — good home for a small helper
- `tests/test_ffprobe_ffmpeg.py` — add the test here

**What to do:** The audio preview derives the ffplay path from the ffmpeg path with
`ffmpeg_path.replace("ffmpeg.exe", "ffplay.exe").replace("ffmpeg", "ffplay")`
(line 1791). The second `.replace` rewrites **every** occurrence of "ffmpeg" in the
path, so a path like `C:\tools\ffmpeg\bin\ffmpeg.exe` becomes
`C:\tools\ffplay\bin\ffplay.exe` — a directory that does not exist. Replace only the
file name: add a small pure function (for example `derive_ffplay_path(ffmpeg_path: str) -> str`)
in `utils/ffmpeg.py` using `pathlib.Path(...).with_name(...)`, and call it from
`main_window.py` instead of the two chained replaces.

**Acceptance criteria:**
- A path with "ffmpeg" in a directory name (e.g. `C:\tools\ffmpeg\bin\ffmpeg.exe`
  and `/opt/ffmpeg/bin/ffmpeg`) derives correctly — only the file name changes.
- The bare-command case (`"ffmpeg"` → `"ffplay"`) still works.
- New unit test in `tests/test_ffprobe_ffmpeg.py` covering both cases above.
- `python -m pytest tests/test_ffprobe_ffmpeg.py --no-cov` passes.

**Difficulty:** Easy

---

## 2. Use the macOS log folder convention (`~/Library/Logs/Zelqivo`)

**Files:**
- `src/multicam_editor/logging_setup.py` — `_get_log_directory()`, lines 35–49
- `tests/test_logging.py` — add the test here

**What to do:** Right now every non-Windows platform logs to `~/.zelqivo/logs/`
(line 48). On macOS the convention is `~/Library/Logs/<AppName>`, which is where
users (and Console.app) look for logs. Add a `sys.platform == "darwin"` branch that
returns `Path.home() / "Library" / "Logs" / "Zelqivo"`. Keep Linux on
`~/.zelqivo/logs/`, and update the docstring (lines 38–39).

**Acceptance criteria:**
- New test in `tests/test_logging.py` that monkeypatches `sys.platform` to
  `"darwin"`, `"win32"`, and `"linux"` and checks the directory returned by
  `_get_log_directory()` for each.
- `python -m pytest tests/test_logging.py --no-cov` passes.
- Note: issue 9 documents log paths in the README — if you do this issue, update
  the README rows too (or coordinate with whoever took issue 9).

**Difficulty:** Easy

---

## 3. Find FFmpeg in common macOS install locations

**Files:**
- `src/multicam_editor/utils/ffmpeg.py` — `_find_ffmpeg()`, lines 71–93
- `src/multicam_editor/utils/ffprobe.py` — `_find_ffprobe()`, lines 108–127 (same
  pattern, twin function)
- `tests/test_ffprobe_ffmpeg.py` — add tests here

**What to do:** When ffmpeg/ffprobe is not on `PATH`, the fallback search only runs
on Windows (`if os.name == "nt":` at `ffmpeg.py` line 72 and `ffprobe.py` line 109).
GUI apps launched from Finder on macOS often get a minimal `PATH` that misses
Homebrew, so discovery fails even though FFmpeg is installed. Add a
`sys.platform == "darwin"` branch to **both** functions checking, in order:
`/opt/homebrew/bin`, `/usr/local/bin`, `/opt/local/bin` (Apple Silicon Homebrew,
Intel Homebrew, MacPorts).

**Acceptance criteria:**
- New tests that monkeypatch the platform check plus `os.path.isfile` (or point the
  search at a `tmp_path` fake binary) and assert the darwin locations are found.
  The autouse `reset_caches` fixture in `tests/test_ffprobe_ffmpeg.py` (line 40)
  already clears the module-level cache between tests — keep your tests in that file
  so it applies.
- Both `_find_ffmpeg` and `_find_ffprobe` are covered.
- `python -m pytest tests/test_ffprobe_ffmpeg.py --no-cov` passes.

**Difficulty:** Medium

---

## 4. Detect Apple Silicon GPUs (MPS) in the GPU preflight check

**Files:**
- `src/multicam_editor/logic/preflight.py` — `detect_gpu()`, lines 435–456
- `tests/test_gpu_preflight.py` — extend `TestDetectGpu` (starts line 19)

**What to do:** `detect_gpu()` only checks `torch.cuda.is_available()` (line 444),
so every Mac reports "no GPU" and users get pushed toward slower modes. After the
CUDA check, also check `torch.backends.mps.is_available()` (guard with
`getattr(torch.backends, "mps", None)` so old torch builds don't crash) and return
`True` when MPS is available, logging which kind of GPU was found.

**Acceptance criteria:**
- New tests in `tests/test_gpu_preflight.py` mocking torch: (a) CUDA off + MPS on
  returns `True`, (b) CUDA off + MPS missing/off returns `False`, (c) torch not
  installed still returns `False`. Follow the existing mock style in that file.
- `python -m pytest tests/test_gpu_preflight.py --no-cov` passes.

**Difficulty:** Medium

---

## 5. Delete stale "not implemented" text for FAST_RULES

**Files:**
- `src/multicam_editor/logic/switching_strategy.py` — lines 9, 32, and 49–52

**What to do:** The module docstring (line 9), the enum comment (line 32), and the
`select_switching_engine` docstring (lines 49–52, including the `Raises:
NotImplementedError` section) all say FAST_RULES is "not implemented" — but it IS
implemented right below, at lines 85–92, returning a `FastRulesEngine`. Delete the
stale text and replace it with a one-line accurate description (e.g. "Rule-based
energy switching, fastest option"). Documentation-only change; do not touch the code.

**Acceptance criteria:**
- `grep -n "not yet implemented\|not implemented\|NotImplementedError" src/multicam_editor/logic/switching_strategy.py`
  returns nothing.
- `python -m pytest tests/test_switching_strategy.py --no-cov` still passes (the
  existing test at line 54 already proves FAST_RULES works).

**Difficulty:** Easy

---

## 6. Make two Windows-path tests pass on macOS and Linux

**Files:**
- `tests/test_file_utils.py` — lines 59–62 (`test_safe_basename_normal_path`)
- `tests/test_qa_artifacts.py` — lines 26–27 (`test_windows_path`)

**What to do:** Both tests assert that a hard-coded Windows path like
`C:\Users\me\video.mp4` reduces to just the file name. The production code uses
`os.path.basename`, which on macOS/Linux does not treat `\` as a separator — so
these two tests fail on every non-Windows machine (they are the two known failures
mentioned at the top of this document). Split the Windows-path assertions into their
own tests and mark them with
`@pytest.mark.skipif(sys.platform != "win32", reason="Windows path semantics")`,
keeping the POSIX assertions running everywhere.

**Acceptance criteria:**
- `python -m pytest tests/test_file_utils.py tests/test_qa_artifacts.py --no-cov`
  passes on macOS/Linux with the Windows-specific tests reported as skipped.
- No production code changes — this issue is test-only. (Making `safe_basename` and
  `_sanitize_path` handle both separator styles is a fine follow-up issue, but keep
  it separate.)

**Difficulty:** Easy

---

## 7. Replace silent `except Exception: pass` in utils with specific exceptions + debug logging

**Files:**
- `src/multicam_editor/utils/ffmpeg.py` — lines 68–69 (PATH probe) and 204–208
  (`cancel()`)
- `src/multicam_editor/utils/ffprobe.py` — lines 106–107 (PATH probe)
- `src/multicam_editor/utils/backends.py` — lines 178–179 (ffprobe path lookup in
  `run_health_check`)

**What to do:** These four spots swallow every exception silently, which makes
"FFmpeg not found" reports impossible to debug. For each, catch the specific
exceptions that can actually happen (for the subprocess PATH probes:
`OSError` and `subprocess.TimeoutExpired`) and log at debug level with the
traceback, e.g. `logger.debug("ffmpeg PATH probe failed", exc_info=True)`. In
`cancel()` the broad catch around `kill()` may stay broad (it is a last-resort
cleanup), but it should still log instead of `pass`.

**Acceptance criteria:**
- No bare `except Exception:` followed by `pass` remains in
  `src/multicam_editor/utils/` — verify with
  `grep -rn -A1 "except Exception" src/multicam_editor/utils/ | grep -B1 "pass"`.
- Every changed site logs via `logger.debug(..., exc_info=True)`.
- `python -m pytest tests/test_ffprobe_ffmpeg.py tests/test_backends.py --no-cov`
  passes.

**Difficulty:** Medium

---

## 8. Single-source the version number

**Files:**
- `src/multicam_editor/__init__.py` — currently empty
- `pyproject.toml` — line 12 (`version = "1.0.3"`)

**What to do:** The version lives only in `pyproject.toml`, so the code itself has
no way to report which version it is (About dialogs, logs, bug reports). Add
`__version__ = "1.0.3"` to `src/multicam_editor/__init__.py`, then make
`pyproject.toml` read it: change line 12 to `dynamic = ["version"]` inside
`[project]` and add a `[tool.setuptools.dynamic]` section with
`version = {attr = "multicam_editor.__version__"}`.

**Acceptance criteria:**
- `pip install -e .` succeeds and `pip show multicam-editor` reports `1.0.3`.
- `python -c "import multicam_editor; print(multicam_editor.__version__)"` prints
  `1.0.3`.
- Add a small test (e.g. in `tests/test_import.py`) asserting `__version__` exists
  and is a non-empty string; `python -m pytest tests/test_import.py --no-cov` passes.

**Difficulty:** Easy

---

## 9. Document macOS/Linux log locations in the README

**Files:**
- `README.md` — lines 188–192 ("Log Files" section); also mentions at lines 202
  and 219

**What to do:** The README only tells Windows users where the logs are
(`%LOCALAPPDATA%\Zelqivo\logs\zelqivo.log`). The code in
`src/multicam_editor/logging_setup.py` (lines 35–49) writes to `~/.zelqivo/logs/`
on every other platform. Add macOS and Linux rows to the "Log Files" section, and
check the troubleshooting mentions at lines 202 and 219 read sensibly for
non-Windows users too.

**Acceptance criteria:**
- README lists the log path for Windows, macOS, and Linux, matching what
  `_get_log_directory()` actually does.
- If issue 2 (macOS log folder) has already landed, document the new
  `~/Library/Logs/Zelqivo` path; otherwise document the current `~/.zelqivo/logs/`.
- Docs-only change; `python -m pytest tests/test_logging.py --no-cov` still passes.

**Difficulty:** Easy

---

## 10. Pin the clip-lookup-after-split behavior with tests

**Files:**
- `src/multicam_editor/core/project.py` — `_find_first_by_path` (lines 139–150),
  `get_trim_by_path` (152–171), `set_trim_by_path` (191–211),
  `split_clip_by_path` (line 214) — read only, do not change
- `tests/test_project.py` — add tests here

**What to do:** Four TODO comments in `project.py` (lines 142, 158, 180, 197) warn
that after a split, two clips share the same path, and all path-based lookups
silently operate on the **first** match only. No test currently pins that behavior,
so a future refactor to ID-based lookups has no safety net. Write characterization
tests: split a clip, then show that `get_trim_by_path` returns the first segment's
trim and `set_trim_by_path` modifies only the first clip while the second is
untouched. Follow the style of `test_split_produces_unique_clip_ids`
(line 78 in `tests/test_project.py`).

**Acceptance criteria:**
- At least two new tests: one for `get_trim_by_path` after a split, one for
  `set_trim_by_path` after a split, each asserting the second clip is unaffected.
- Test docstrings reference the TODOs so the future refactor finds them.
- No production code changes.
- `python -m pytest tests/test_project.py --no-cov` passes.

**Difficulty:** Medium
