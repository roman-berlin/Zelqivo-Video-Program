# Contributing to Zelqivo

Thanks for your interest! Zelqivo is a desktop app that edits multicam podcast
recordings automatically. Contributions of all sizes are welcome — bug fixes,
tests, docs, and platform-correctness work especially.

**New here?** Pick something from [docs/GOOD_FIRST_ISSUES.md](docs/GOOD_FIRST_ISSUES.md)
or the [`good first issue`](../../labels/good%20first%20issue) label and leave a
comment on the issue so we know you're on it.

## The project is open core — said plainly

The desktop app you see here is free forever and Apache-2.0. A paid Pro tier
(cloud diarization, batch licensing) is planned as a separate closed-source
product. Your contributions to this repo stay Apache-2.0 and benefit the free
app; by contributing you accept that the maintainer may also ship them in the
Pro product, as the Apache license allows. If that's not okay with you, we
understand — thank you for reading this far.

## Development setup

You need Python 3.10–3.12 (3.12 recommended) and FFmpeg on your PATH.

```bash
git clone https://github.com/roman-berlin/Zelqivo-Video-Program.git
cd Zelqivo-Video-Program
python3.12 -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   |   macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

Run the app:

```bash
python -m multicam_editor
```

## Running the tests

The full suite, Qt tests included:

```bash
# macOS/Linux (headless-safe):
QT_QPA_PLATFORM=offscreen pytest --no-cov

# Windows:
pytest --no-cov
```

Two things to know:

- `pyproject.toml` already passes `-q` and coverage flags to pytest. Do **not**
  add another `-q` (it becomes `-qq` and hides the final summary line). Use
  `--no-cov` for faster local runs.
- Two tests currently fail on macOS/Linux (`test_file_utils`,
  `test_qa_artifacts` Windows-path cases) — known, pre-existing, and one of our
  good first issues. Everything else should pass: **539 passed** is the current
  baseline.

## Code style

`black`, `ruff`, and `mypy` are configured in `pyproject.toml`:

```bash
black <files you changed> && ruff check <files you changed> && mypy src/
```

Honest note: the existing codebase does not yet pass these tools repo-wide
(cleanup is on the [roadmap](docs/ROADMAP.md)). The rule for PRs is simple:
**your changed lines must be clean, and don't reformat files you didn't
otherwise touch** — mass reformatting makes PRs unreviewable.

## Commits and sign-off

- Use [Conventional Commits](https://www.conventionalcommits.org/):
  `fix: derive ffplay path with pathlib`, `feat: add macOS log directory`.
- Sign off every commit (DCO): `git commit -s`. This certifies you have the
  right to submit the change under Apache-2.0.

## What we merge — and what we don't

**Gladly merged:** bug fixes with a test, platform correctness (macOS/Linux),
new tests for existing behavior, docs, performance fixes with measurements.

**Talk to us first (open an issue):** new features, UI changes, anything
touching the switching engine (`logic/decision_engine.py`,
`logic/fast_rules_engine.py`, `logic/active_speaker.py`) — that's the heart of
the product and changes there need discussion.

**Won't merge:** new runtime dependencies without prior agreement, GPL-licensed
dependencies (they would break our LGPL/Apache licensing — see
[docs/THIRD_PARTY.md](docs/THIRD_PARTY.md)), features hidden behind
`setVisible(False)`, and PRs that reduce test coverage.

## Before you open the PR

1. Tests pass locally (see above — no new failures vs the baseline).
2. If you changed behavior, update [docs/FEATURE_REALITY.md](docs/FEATURE_REALITY.md) —
   it is the repo's honesty contract and must always match reality.
3. Update `CHANGELOG.md` under `[Unreleased]`.
4. Commits are signed off (`-s`) and conventionally named.

The PR template will walk you through this checklist.

## Project map (60 seconds)

```
src/multicam_editor/
  core/       Project model — clips, ordering, trims (single source of truth)
  logic/      Pipeline: probe → audio-sync → speaker detection → cuts → render
  ui/         PySide6 widgets and dialogs (main_window.py is the hub)
  utils/      ffmpeg/ffprobe wrappers, settings, logging
tests/        pytest + pytest-qt (Qt tests run headless via offscreen platform)
```

Architecture rules (short version — AI assistants get the same rules from
`CLAUDE.md`): the `Project` is the single source of truth; every user action
that changes it must be undoable via `QUndoStack` commands; all FFmpeg access
goes through `utils/ffmpeg.py` / `utils/ffprobe.py`; never
`except Exception: pass`.

Questions? Open a [discussion](../../discussions) or an issue. Thanks! 🎬
