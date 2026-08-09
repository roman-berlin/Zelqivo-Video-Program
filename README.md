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

MultiCamEditor offers two installation modes:

- **Core (default)**: CPU-only operation with energy-based speaker detection.
  No torch/pyannote required. Ideal for non-technical users.
- **AI extras**: Adds real AI diarization (pyannote.audio) and advanced audio
  sync (librosa). Requires ~2GB disk space for models.

#### Option A: Core Installation (Recommended for Most Users)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

The app will run in CPU-only mode with energy-based speaker switching.

#### Option B: Full AI Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[ai]"
```

This enables:
- Real pyannote.audio speaker diarization
- Advanced librosa-based audio sync

#### Option C: Development Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"       # Core + dev tools (pytest, black, ruff, mypy)
pip install -e ".[all]"       # Everything (core + ai + dev)
```

#### Check Backend Status

To verify which features are available:

```bash
python -m multicam_editor.utils.backends
```

Output example:
```
=== MultiCamEditor Backend Status ===

  [OK] Core (PyQt, numpy, ffmpeg)
  [OK] Energy VAD (CPU speaker detection)
  [--] Audio Sync (librosa, soundfile)
       AI audio dependencies not installed...
  [--] Pyannote (AI diarization)
       pyannote.audio not installed...

To enable AI features, install: pip install multicam-editor[ai]
```

#### Run the Test Suite

```bash
# Run non-Qt tests (recommended, no display needed)
pytest tests/ --ignore=tests/test_ui.py --ignore=tests/test_magic_settings.py --ignore=tests/test_file_list_time.py --ignore=tests/test_processing_worker_signals.py --ignore=tests/test_processing_time.py -v

# Quick coverage report
pytest --cov=src --cov-report=term-missing
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

Artifacts will be placed in the `dist/` directory.

#### Building Windows Executable

Build a standalone Windows executable that runs on machines without Python installed.

> **Note:** FFmpeg is bundled with the distribution. No separate FFmpeg install required on target machines.

**Prerequisites:**
- Python 3.10 or later
- FFmpeg binaries at `C:\ffmpeg-7.1.1-full_build\bin\` (for bundling)
- Development dependencies: `pip install -e ".[dev]"`

**Quick Build (Recommended):**

```powershell
# Run from repo root - handles venv, deps, tests, and build
.\build_exe.ps1
```

**Manual Build:**

```powershell
# 1. Activate venv
.\.venv\Scripts\Activate.ps1

# 2. Install deps
pip install -e ".[dev]"

# 3. Build
pyinstaller multicam_editor.spec --clean --noconfirm
```

**Output:**
```
dist\MulticamEditor\MulticamEditor.exe
```

The `dist\MulticamEditor\` folder contains the EXE and all required DLLs/resources.
Copy the entire folder to distribute the application.

**Log Files:**

Logs are automatically written to:
- Windows: `%LOCALAPPDATA%\Zelqivo\logs\zelqivo.log`
- macOS and Linux: `~/.zelqivo/logs/zelqivo.log`
- Logs rotate automatically (5 files × 1MB max)

**Troubleshooting:**

| Error | Solution |
|-------|----------|
| "Qt platform plugin 'windows' not found" | Reinstall PyQt6: `pip uninstall PyQt6 PyQt6-Qt6 -y && pip install PyQt6` |
| "ffmpeg not found" | FFmpeg should be bundled. Check `dist\MulticamEditor\tools\ffmpeg\` exists |
| Missing VC++ Runtime | Install [VC++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| ImportError on launch | Rebuild with `--clean` flag |
| No logs created | Check folder permissions for `%LOCALAPPDATA%\Zelqivo\` on Windows, or `~/.zelqivo/logs/` on macOS/Linux |
| Black screen / no video | Ensure Qt Multimedia plugins are in `_internal\PyQt6\Qt6\plugins\multimedia\` |

#### Smoke Test Checklist

After building, verify the EXE works correctly (~2 minutes):

1. [ ] Launch `dist\MulticamEditor\MulticamEditor.exe`
2. [ ] Verify no console window appears (windowed mode)
3. [ ] No "missing plugin" error dialogs
4. [ ] Import 2+ video files via "Add Files" button
5. [ ] (Optional) Add external audio file
6. [ ] Play preview – video displays correctly
7. [ ] Confirm audio plays during preview
8. [ ] Seek on the timeline works
9. [ ] Click "Create Video" (Process) and export
10. [ ] Verify output MP4 plays in VLC or Windows Media Player
11. [ ] Check logs exist at `%LOCALAPPDATA%\Zelqivo\logs\`


### Real Speaker Diarization (pyannote.audio) – Windows Setup

The REAL diarization backend uses `pyannote.audio` which requires HuggingFace
authentication due to gated model access.

#### 1. Create a HuggingFace Account
Visit https://huggingface.co/join and create a free account.

#### 2. Accept Gated Model Access
Visit https://hf.co/pyannote/speaker-diarization-3.1 and click **"Agree and access repository"**.
You must accept the model's user conditions before downloading.

#### 3. Create a Read Token
Go to https://hf.co/settings/tokens → **Create new token** → Select **Read** access → Copy the token.

#### 4. Login to HuggingFace

**Preferred (new CLI):**
```powershell
hf auth login
# Paste your token when prompted
```

**Legacy CLI:**
```powershell
huggingface-cli login
```

#### 5. Verify Authentication
The `hf whoami` command may not exist in all environments. Use these instead:

```powershell
# Option A: Check auth status
hf auth status

# Option B: Python verification
python -c "from huggingface_hub import HfApi; print(HfApi().whoami())"
```

#### 6. First Run
On first use, the model downloads to:
- Windows: `C:\Users\<username>\.cache\huggingface\hub\`
- Linux/Mac: `~/.cache/huggingface/hub/`

Initial download is ~1-2GB. Subsequent runs use the cached model.

#### Troubleshooting
- **401 Unauthorized**: Run `hf auth login` again with a valid token
- **Gated model not accepted**: Visit the model page and click "Agree and access"
- **Model not found**: Check your internet connection and HuggingFace status

### QA CLI Mode (Headless Processing)

For automated QA and CI/CD pipelines, use the CLI entry point to run
processing without the GUI:

```bash
python -m multicam_editor.cli \
  --videos cam1.mp4 cam2.mp4 \
  --external-audio podcast.wav \
  --enable-speaker-switching true \
  --mapping cam1:speaker_0 cam2:speaker_1 \
  --preset 1080p \
  --out output.mp4 \
  --export-artifacts true
```

#### CLI Arguments

| Argument                     | Required | Default | Description                                      |
|-----------------------------|----------|---------|--------------------------------------------------|
| `--videos`                  | Yes      | -       | Input video files (at least 2)                   |
| `--external-audio`          | No       | -       | External audio file to sync                      |
| `--enable-speaker-switching`| No       | true    | Enable speaker-based camera switching            |
| `--mapping`                 | No       | -       | Camera-to-speaker mapping (reserved for future)  |
| `--preset`                  | No       | 1080p   | Output resolution: 1080p, 720p, 480p             |
| `--out`                     | Yes      | -       | Output file path                                 |
| `--export-artifacts`        | No       | true    | Export QA artifacts (diarization.json, etc.)     |
| `--verbose` / `-v`          | No       | false   | Enable verbose logging                           |

#### Exit Codes

- `0` - Success
- `1` - Failure (check logs for details)

#### QA Artifacts

When `--export-artifacts true`, the CLI prints the artifacts folder path:
```
Artifacts: C:\Users\...\AppData\Local\MultiCamEditor\qa_runs\run_20241221_143052
```

This folder contains:
- `diarization.json` - Speaker segments detected
- `cut_plan.json` - Final cut decisions with reasons
- `processing_summary.json` - Counts, thresholds, sync info

### License

This project is licensed under the MIT License.  See `LICENSE` for
details.
