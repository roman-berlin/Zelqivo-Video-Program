# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **License changed from MIT to Apache-2.0**, with the real copyright holder
  (Roman Berlin) replacing the "Owner" placeholder. Apache-2.0 adds an explicit
  patent grant and trademark reservation, which the open-core model needs.
- README rewritten as a user-first landing page: what it does / doesn't do,
  how it works, platform table, install guide, CLI reference, honest CI note,
  and the new logo. Above the fold: a demo GIF produced by the real pipeline
  on synthetic test cameras (`docs/assets/demo.gif`). Also removed the false
  "CI ready" claim. A social-preview banner was added under
  `Installer/assets/icons/`.
- Internal AI-agent scaffolding (`.clinerules`, `.ai_instructions/`,
  `.human_instructions/`) replaced by a single public `CLAUDE.md` with the
  project's engineering rules.
- Migrated the entire GUI layer from PyQt6 (GPLv3) to PySide6 ≥ 6.8 (LGPLv3):
  34 files, 80 import lines, 37 signal declarations (`pyqtSignal` → `Signal`).
  Unblocks the open-core licensing model (Phase 0.1 of the hardening work order).
- `pyproject.toml` is now the single source of truth for dependencies;
  `pytest-qt` added to the dev extras so the Qt test files run in the standard suite.

### Added
- `tests/test_settings_roundtrip.py`: proves `QSettings.value(..., type=X)` coercion
  for bool/int/float/str plus missing-key defaults, guarding future PySide6 bumps.
- Open-source community files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
  (Contributor Covenant 2.1), `SECURITY.md`, `NOTICE`, `TRADEMARK.md`,
  GitHub issue templates and a pull-request template, `docs/THIRD_PARTY.md`,
  `docs/ROADMAP.md`, and `docs/GOOD_FIRST_ISSUES.md`.
- `src/multicam_editor/ui/widgets/__init__.py` — the widgets folder was an
  implicit namespace package, which breaks some packaging tools.
- New app logo (`Installer/assets/icons/`): PNG plus a multi-size `.ico`,
  now committed so contributors can build the installer; the PyInstaller
  spec uses it as the EXE icon.

### Removed
- `requirements.txt` and `requirements.in` (duplicated and contradicted `pyproject.toml`).
- `PyQt6.sip` hidden import and `pyqt6-sip` dependency (PySide6 uses shiboken6, bundled automatically).
- Committed scratch files (`coverage_report.txt`, `test_new_results.txt`,
  `verification_result.txt`, `verify_settings_persistence.py`, `commands`,
  `shortcuts`); `.gitignore` now blocks them and no longer ignores the
  installer script and app icon that contributors need to build the installer.

> The sections below were reconstructed from git history. These releases were never
> tagged, so dates are approximate (taken from commit dates).

## [1.0.2 – 1.0.3] - 2026-02-08

The version number in the repo jumped from 1.0.1 straight to 1.0.3, so there is no
separate 1.0.2 entry; everything from that period is listed here.

### Added
- New rule-based "fast rules" switching engine, and the switching strategy is now
  selectable in Settings.
- A pre-flight GPU check that warns you before processing starts if your GPU setup
  is not ready, instead of failing in the middle of a render.
- Export of the timeline cuts to FCPXML, so you can keep editing in Final Cut Pro.
- Magic Settings dialog that gathers the AI processing options in one place.
- Audio preview dialog for checking the sound before processing.
- The file list now detects duplicate files and shows a sync status for each one.

### Changed
- The app window is now frameless with a custom title bar.
- The Windows build now bundles the audio-analysis libraries (librosa, soundfile),
  so audio features work out of the box.

### Fixed
- Several fixes in the video preview area of the main window.

## [1.0.1] - 2026-01-14

### Added
- Windows installer (Inno Setup): Zelqivo now installs like a normal Windows
  program, with Start menu and desktop shortcuts, plus a one-step build script.

### Changed
- More detailed log files, which makes problems easier to report and fix.
- The Start menu and desktop shortcuts now use the Zelqivo icon.

### Fixed
- "Fast cut" bug: the automatic edit no longer jumps between cameras too quickly.
  Cuts now respect a minimum clip length and a cooldown between switches, and they
  prefer to land on silent moments.

## [1.0.0] - 2026-01-07

First working build of Zelqivo, shipped as a standalone Windows executable.

### Added
- Multicam podcast editing: drop in the video files from each camera and Zelqivo
  detects who is speaking and cuts to the right camera automatically.
- Active speaker detection with pluggable backends, including an energy-based mode
  that runs on CPU-only machines, and a configurable speaker-to-camera mapping.
- Stage-based processing pipeline with progress tracking and checkpoints, shown in
  a themed progress dialog.
- FFmpeg-based rendering: cutting, effects, an optional QA overlay for reviewing
  the automatic decisions, and merging everything into the final video.
- Settings dialog covering output quality, audio mix, decision engine rules, QA
  overlay, and a light/dark theme toggle.
- Drag-and-drop file list that shows media details for each imported file.
- Standalone Windows executable built with PyInstaller.
