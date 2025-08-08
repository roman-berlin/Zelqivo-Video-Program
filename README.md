
---

````markdown
# MultiCamEditor (Active Speaker Video Merger)

MultiCamEditor is a desktop application that helps you merge and edit
multi‑camera video footage, selecting only the active speaker and
providing a simple preview and save workflow. The application is built
using Python and PyQt6.

## Setup

1. **Install Python** – make sure Python 3.10 or higher is available on your machine.
2. **Create a virtual environment** (recommended):

   ```bash
   python -m venv .venv
````

3. **Activate the virtual environment:**

   * **Windows:**

     ```cmd
     .venv\Scripts\activate
     ```
   * **macOS/Linux:**

     ```bash
     source .venv/bin/activate
     ```

4. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

## Run

To launch the application for development/testing:

```bash
python main.py
```

## Build Standalone Windows EXE

1. **Ensure PyInstaller is installed:**

   ```bash
   pip install pyinstaller
   ```

2. **Build the executable** (Windows):

   ```cmd
   build_exe.bat
   ```

   The resulting EXE will appear in the `dist` directory as `MultiCamEditor.exe`.

3. (Advanced) If you need to add data files or icons to the build,
   edit the `MultiCamEditor.spec` file and rebuild.

---

## Project Structure

```
project_root/
│   main.py
│   requirements.txt
│   build_exe.bat
│   MultiCamEditor.spec
│   README.md
├── logic/
├── ui/
├── utils/
```

---

## Notes

* **Dependencies** include: PyQt6, pyannote.audio, SpeechBrain, librosa, numpy, ffmpeg-python, moviepy, opencv-python, torch, tqdm, soundfile, and more.
* For best results, run and test your EXE on the same environment as you build.
* If you encounter issues with missing DLLs or runtime dependencies, consult the PyInstaller and PyQt6 documentation.

---

**Enjoy MultiCamEditor!**

```

---

אם תרצה שאשלב הסבר נוסף או תבנית Markdown שונה – רק תבקש!
```
