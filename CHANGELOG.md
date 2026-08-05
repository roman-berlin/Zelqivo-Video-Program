# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Migrated the entire GUI layer from PyQt6 (GPLv3) to PySide6 ≥ 6.8 (LGPLv3):
  34 files, 80 import lines, 37 signal declarations (`pyqtSignal` → `Signal`).
  Unblocks the open-core licensing model (Phase 0.1 of the hardening work order).
- `pyproject.toml` is now the single source of truth for dependencies;
  `pytest-qt` added to the dev extras so the Qt test files run in the standard suite.

### Removed
- `requirements.txt` and `requirements.in` (duplicated and contradicted `pyproject.toml`).
- `PyQt6.sip` hidden import and `pyqt6-sip` dependency (PySide6 uses shiboken6, bundled automatically).

### Added
- `tests/test_settings_roundtrip.py`: proves `QSettings.value(..., type=X)` coercion
  for bool/int/float/str plus missing-key defaults, guarding future PySide6 bumps.
