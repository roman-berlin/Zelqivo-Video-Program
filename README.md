## MultiCamEditor – Refactored

MultiCamEditor is a Python‑based desktop application for merging and editing
multi‑camera video footage.  It presents a simple interface for previewing
clips, trimming them and constructing a timeline by selecting the active
speaker.  This repository contains a refactored, test‑backed version of
MultiCamEditor with a modern project layout, automated tooling and a
continuous integration workflow.

### Features

* **Modular structure** – code is organised under `src/multicam_editor` with
  clear separation between core data structures, business logic and the GUI.
* **Guard‑railed splitting** – clips can be split only when both resulting
  segments exceed a minimum duration.  This prevents accidental creation of
  unusable segments.
* **Centralised logging** – the `logging_setup` module configures the root
  logger once, ensuring consistent log formatting and preventing duplicate
  handlers.
* **Type hints & basic type checking** – public APIs are annotated and the
  project is checked with `mypy` in permissive mode (strict mode is a roadmap
  item for future improvement).
* **Tests & coverage** – a small but meaningful test suite validates the
  behaviour of core components and the logging configuration.  Running
  `pytest -q` will report coverage information.
* **CI ready** – a GitHub Actions workflow runs linting, type checking and
  the tests against Python 3.10–3.12.

### Getting Started

The GUI depends on a number of heavy multimedia libraries (PyQt6, torch,
moviepy, etc.) which are *not* included in the default installation.  To
install these optional runtime dependencies use the original `requirements.txt`
or install the packages you need manually.  The following steps focus on
setting up a development environment for running the tests and static
analysis tools.

1. **Create a virtual environment** (recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install development dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the test suite**:

   ```bash
   pytest -q
   ```

4. **Lint, format and type‑check the code**:

   ```bash
   ruff check .
   black --check .
   mypy .
   ```

5. **Run the GUI** (optional):

   ```bash
   python -m multicam_editor
   ```

   Note: Running the GUI requires installing PyQt6 and other multimedia
   libraries which may not be available in minimal environments.  See the
   original project documentation for details.

### Development

The project uses `black` for code formatting, `ruff` for linting and
`mypy` for type checking.  Configuration for these tools lives in
`pyproject.toml`.  Please format your code before committing:

```bash
black .
ruff check --fix .
```

To run the full suite locally:

```bash
pytest --cov=src --cov-report=term-missing
```

### Packaging

The repository is configured with a standard `pyproject.toml` and uses
Setuptools to build a source distribution and wheel.  To build the
package:

```bash
python -m pip install build
python -m build
```

Artifacts will be placed in the `dist/` directory.  Building a standalone
Windows executable via PyInstaller is out of scope for this refactoring,
but the `main.py` entry point remains compatible with PyInstaller.

### License

This project is licensed under the MIT License.  See `LICENSE` for
details.
