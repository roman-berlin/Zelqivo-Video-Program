# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

* Added comprehensive architecture review documentation (`ARCHITECTURE_REVIEW.md`)
  analyzing codebase structure, identifying critical issues, and providing
  actionable refactoring recommendations.

### Changed

* Standardized `requirements.txt` comments to English for international
  contributor accessibility.
* Updated `README.md` to accurately reflect mypy configuration (basic type
  checking instead of strict mode).

### Removed

* Removed duplicate `logic/project_state.py` module to eliminate architectural
  confusion. The authoritative `Project` implementation is in `core/project.py`.

## [0.1.0] – 2025-09-01

### Added

* Refactored the original MultiCamEditor project into a proper Python package
  under `src/multicam_editor`.
* Added a `logging_setup` module providing centralised logging configuration.
* Implemented minimum segment length guardrails in both the core `Project`
  splitting logic and the GUI `TrimPanel`.
* Added `pyproject.toml` with configuration for Black, Ruff, Mypy and PyTest.
* Added `.gitignore`, `.editorconfig`, `LICENSE`, `README.md`, and
  `CONTRIBUTING.md`.
* Added basic test suite covering core project logic and logging setup.
* Added continuous integration via GitHub Actions for Python 3.10–3.12.

### Changed

* Converted absolute imports (`core`, `utils`, `ui`) into package‑relative
  imports to support installation and avoid reliance on `sys.path` hacks.

### Removed

* Removed compiled `__pycache__` directories from version control.
