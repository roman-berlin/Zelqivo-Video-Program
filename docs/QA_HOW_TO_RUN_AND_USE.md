# QA Guide: How to Run and Use the Multicam Video Editor

This document provides manual QA testers with instructions for running the application, understanding expected behaviors, and troubleshooting common issues.

---

## Prerequisites

### Python Environment
- **Python 3.8+** required
- **Virtual environment recommended** (venv or similar)

### External Dependencies
- **ffmpeg** and **ffprobe** must be available:
  - **Option 1 (Recommended):** Add ffmpeg/ffprobe to system PATH
  - **Option 2:** Place executables in one of these Windows locations:
    - `C:\ffmpeg\bin\ffprobe.exe` / `C:\ffmpeg\bin\ffmpeg.exe`
    - `C:\Program Files\ffmpeg\bin\`
    - `%USERPROFILE%\ffmpeg\bin\`
  - **Verification:** Run `ffprobe -version` and `ffmpeg -version` in a terminal

### Supported Video Formats
The app currently validates and accepts:
- `.mp4`
- `.avi`
- `.mov`

Files with other extensions will be rejected during import.

---

## Install and Run (Windows)

### Option 1: Running from Source (Recommended for QA)

1. **Clone/extract the project** to a local directory (e.g., `C:\Python Project\Video_Program`)

2. **Open a terminal** (Command Prompt or PowerShell) and navigate to the project root:
   ```cmd
   cd "C:\Python Project\Video_Program"
   ```

3. **Create and activate a virtual environment** (first time only):
   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

4. **Install dependencies** (first time or after requirements change):
   ```cmd
   pip install -r requirements.txt
   ```

5. **Run the application**:
   ```cmd
   python -m multicam_editor
   ```

6. The main window should launch. Check the console for log output.

### Option 2: Running via Packaged Build (If Available)

If a packaged `.exe` has been built (via PyInstaller):

1. Navigate to the `dist/` folder
2. Double-click `multicam_editor.exe` (or `MultiCamEditor.exe`)
3. The app should launch without requiring Python installation
4. Logs may be written to a `.log` file in the same directory or to console if run from terminal

---

## Logging

### Default Logging Behavior
- **Log Level:** `INFO` by default
- **Output:** Console (stdout/stderr)
- **Format:** `YYYY-MM-DD HH:MM:SS LEVEL module_name: message`

### Enabling Debug Logging
To see more detailed logs (recommended when debugging issues):

1. Edit `src/multicam_editor/main.py`
2. Change the line:
   ```python
   configure_logging()
   ```
   to:
   ```python
   configure_logging(level=logging.DEBUG)
   ```
3. Save and re-run the app
4. Debug logs will include ffprobe calls, cache hits, trim operations, etc.

### Where Logs Are Written
- **Source runs:** Console only (visible in the terminal where you ran `python -m multicam_editor`)
- **Packaged builds:** May redirect to `.log` file or console depending on build configuration

---

## Quick Start Flow (2-3 Minutes)

This is a minimal smoke test to verify core functionality.

### 1. Launch the App
```cmd
python -m multicam_editor
```
Wait for the main window to appear.

### 2. Add 2-3 Videos
- Click **"Add Videos"** button (or use File menu / Ctrl+O)
- Select 2-3 `.mp4`, `.avi`, or `.mov` files
- Files should appear in the **File List** (left panel)
- **Timeline** should show the same clips in the same order

### 3. Select a Clip and Preview
- Click a clip in the File List **or** Timeline
- The **Preview Panel** should load the video
  - If successful: video preview appears with playback controls
  - If codec unsupported: thumbnail or "(no preview available)" message
  - Duration label should **always** populate (via ffprobe fallback if needed)

### 4. Play/Seek
- Click **Play button (▶)** to start playback
- Seek using the slider
- Verify timeline updates and playhead moves

### 5. Check File List ↔ Timeline Sync
- Click different clips in File List → Timeline should highlight the same clip
- Click different clips in Timeline → File List should select the same clip
- **Order must always match** between File List and Timeline

### 6. Quick Undo/Redo Test
- Perform any operation (add, remove, reorder, trim, or split)
- Press **Ctrl+Z** to undo
- Press **Ctrl+Shift+Z** (or Ctrl+Y) to redo
- State should revert and restore correctly

---

## Full User Flow Walkthrough

This section provides a comprehensive step-by-step guide for testing all major features.

### A. Launch and Initial State

**Steps:**
1. Run `python -m multicam_editor`
2. Main window appears with:
   - Empty File List (left)
   - Empty Timeline (bottom)
   - Preview panel (center-right) showing placeholder or empty state
   - Menu bar and toolbar

**Expected Behavior:**
- No errors in console
- Window is responsive
- All UI panels visible

---

### B. Adding Videos

**Steps:**
1. Click **"Add Videos"** button or **File → Open Videos** (Ctrl+O)
2. Navigate to a folder with video files
3. Select 2-3 `.mp4`, `.avi`, or `.mov` files
4. Click **Open**

**Expected Behavior:**
- Files appear in **File List** in the order selected
- Each clip shows:
  - Filename
  - Duration (once ffprobe completes)
- **Timeline** displays the same clips in the same order
- Console logs show ffprobe calls (if DEBUG logging enabled)
- Status bar may show "Added X clips" or similar toast message

**Edge Cases:**
- **Unsupported format** (e.g., `.mkv`): Should be rejected with error message
- **ffprobe not found:** App should show error dialog or toast; duration shows as "00:00"
- **Corrupt/missing file:** Should show error; clip may be added with 0 duration

---

### C. Selecting Clips and Preview Behavior

**Steps:**
1. Click a clip in the **File List**
2. Observe **Preview Panel**
3. Click a different clip in the **Timeline**
4. Observe Preview Panel updates

**Expected Behavior:**
- Clicking a clip in File List:
  - Highlights the clip in File List
  - Selects and highlights the same clip in Timeline
  - Preview loads the video and resets to 00:00
- Clicking a clip in Timeline:
  - Highlights the clip in Timeline
  - Selects the same clip in File List
  - Preview loads the video
- **Selection is always synced** between File List and Timeline

**Preview Decoding:**
- **Success:** Video frame displays, playback controls active, duration shows
- **Failure (Windows codec issue):**
  - Video widget may show "(no preview available)" or a thumbnail (if OpenCV extracts frame)
  - Duration **must still populate** via ffprobe fallback (after ~800ms)
  - Controls (slider, time labels) should still work
  - Trim/Split operations **must still work** even without preview

---

### D. Timeline Behavior

**Steps:**
1. Observe Timeline with multiple clips
2. Scroll horizontally if timeline extends beyond visible area
3. Zoom in/out (if zoom controls exist)

**Expected Behavior:**
- Timeline displays all clips as contiguous blocks
- Each block shows clip name and duration
- Selected clip is highlighted
- Playhead (red line or marker) indicates current preview position
- Scrollbar appears if needed

---

### E. Trimming In/Out Points

**Steps:**
1. Select a clip
2. Locate the **Trim Panel** (may be in right panel or bottom area)
3. Adjust **In slider** to trim the start of the clip
4. Adjust **Out slider** to trim the end of the clip
5. Observe timeline updates
6. Press **Ctrl+Z** to undo
7. Press **Ctrl+Shift+Z** to redo

**Expected Behavior:**
- Dragging **In slider** right:
  - Clip start trims forward
  - Timeline block shrinks from left
  - Duration label updates
- Dragging **Out slider** left:
  - Clip end trims backward
  - Timeline block shrinks from right
  - Duration label updates
- **Constraints:**
  - In point cannot exceed Out point (clamped)
  - Out point cannot go before In point (clamped)
  - In and Out can be equal (allowed, creates 0-duration clip in edge cases)
- **Undo/Redo:**
  - Multiple consecutive trim adjustments **merge into a single undo** (TrimCommand coalescing)
  - Undo restores original In/Out values
  - Redo reapplies trim

**Edge Cases:**
- Trim to extremes (In=Out): Allowed but may cause issues in export
- Preview fails but trim works: Duration from ffprobe allows trim even without preview

---

### F. Split at Playhead

**Steps:**
1. Select a clip
2. Seek to a position in the preview (not at 0ms or end)
3. Click **"Split"** button or use **Edit → Split Clip** (keyboard shortcut if mapped)
4. Observe split result
5. Press **Ctrl+Z** to undo split
6. Press **Ctrl+Shift+Z** to redo split

**Expected Behavior:**
- **Split operation:**
  - Original clip is replaced by two clips:
    - **Left clip:** From original In to split position
    - **Right clip:** From split position to original Out
  - Both clips appear in File List and Timeline in correct order
  - Left clip is selected after split
  - Timeline updates immediately
- **Constraints:**
  - Cannot split at **0ms** (start of clip)
  - Cannot split at **duration** (end of clip)
  - Minimum segment duration: **100ms** (MIN_SEGMENT_MS)
  - Invalid split shows non-blocking error toast
- **Undo:**
  - Left and right clips are merged back into original clip
  - Original clip ID and trim values restored
  - Selection returns to original clip
- **Redo:**
  - Split is reapplied
  - Same left/right clip IDs are used
  - Selection returns to left clip

**Edge Cases:**
- Split a clip that has trim applied: Split position is relative to trimmed segment
- Split near start/end (within 100ms): Should show error, no split occurs

---

### G. Reordering Clips

**Steps:**
1. In the Timeline, click and drag a clip to a new position
2. Drop the clip in the new location
3. Observe File List updates
4. Press **Ctrl+Z** to undo reorder
5. Press **Ctrl+Shift+Z** to redo reorder

**Expected Behavior:**
- **Drag-and-drop:**
  - Clip moves visually in Timeline during drag
  - Drop indicator shows target position
  - On drop, clip is repositioned in Timeline
  - **File List immediately reflects the new order**
- **Undo/Redo:**
  - Undo restores original order in both Timeline and File List
  - Redo reapplies the reorder

**Important:**
- **Project is the single source of truth for clip order**
- Timeline and File List must always mirror Project order (never independent sorting)

---

### H. Removing Clips

**Steps:**
1. Select one or more clips in File List or Timeline
2. Press **Delete** key or click **"Remove"** button
3. Observe clips are removed from both File List and Timeline
4. Press **Ctrl+Z** to undo removal
5. Clips should reappear in original positions

**Expected Behavior:**
- **Remove:**
  - Selected clips disappear from File List and Timeline
  - Timeline reflows to fill gaps
  - Remaining clips maintain order
- **Undo:**
  - Removed clips are restored at their original indices
  - Order is preserved
- **Redo:**
  - Clips are removed again

---

### I. Undo/Redo for Every Operation

**Steps:**
Test undo/redo after each of the following:
1. Add clips → Undo → clips removed → Redo → clips restored
2. Remove clips → Undo → clips restored in correct positions → Redo → removed again
3. Trim → Undo → trim reset → Redo → trim reapplied
4. Split → Undo → merged back → Redo → split again
5. Reorder → Undo → original order → Redo → new order

**Expected Behavior:**
- **Ctrl+Z (Undo):** Reverses last operation, updates UI immediately
- **Ctrl+Shift+Z or Ctrl+Y (Redo):** Reapplies last undone operation
- **Undo history:** Can undo multiple operations in reverse order
- **Redo cleared:** Performing a new operation clears redo history
- **No crashes or broken state** after any undo/redo sequence

---

## Expected Behaviors / Known Limitations

### Preview Decoding Failures (Windows Codec Issues)

**Issue:**
- Some video files (especially H.264/H.265 in `.mp4`) may not decode in the Qt6 QMediaPlayer preview on Windows due to missing codecs.

**Expected Behavior:**
- Preview panel shows:
  - **(Preferred)** Thumbnail extracted via OpenCV (if available)
  - **(Fallback)** Text: "(no preview available)"
- **Duration label MUST still populate:**
  - QMediaPlayer attempts to report duration
  - If QMediaPlayer fails, app falls back to ffprobe after ~800ms
  - Duration is used for trim and split operations
- **Trim/Split operations MUST still work:**
  - Trim sliders use duration from ffprobe
  - Split position is calculated based on ffprobe duration
  - No preview is needed for these operations

**How to Verify:**
1. Add a video that fails to preview (e.g., some `.avi` or `.mov` files)
2. Check that duration still appears (wait ~1 second for ffprobe fallback)
3. Attempt to trim the clip → should work
4. Attempt to split the clip → should work
5. Console logs (if DEBUG enabled) should show ffprobe fallback being used

---

### ffprobe/ffmpeg Availability

**Issue:**
- If ffprobe is not found in PATH or common locations, the app cannot extract metadata.

**Expected Behavior:**
- On first video load, app attempts to locate ffprobe
- If not found:
  - Error dialog or status toast: "ffprobe not found"
  - Videos may be added but duration shows as "00:00"
  - Trim/Split operations are disabled or show errors
- Console logs show: `ffprobe not found` or similar message

**Resolution:**
- Install ffmpeg/ffprobe
- Add to PATH
- Restart app

---

### Minimum Clip/Segment Duration

**Constraints:**
- **Minimum segment after split:** 100ms (MIN_SEGMENT_MS)
- Attempting to split within 100ms of start/end shows error toast

**Why:**
- Prevents creating zero-length or near-zero clips that cause issues in export/processing

---

### Timeline and File List Sync

**Requirement:**
- **Project is the single source of truth**
- Timeline and File List must **always** show clips in the same order
- No independent sorting or filtering
- Any operation that changes Project order must update both views immediately

**Testing:**
- After every operation (add, remove, reorder, split), verify:
  - File List and Timeline show same clips
  - Same order
  - Same selection state

---

## Troubleshooting (Where to Look When Something Fails)

### 1. Check the Console Logs

**What to look for:**
- Error messages (red/ERROR level)
- Warnings (yellow/WARNING level)
- ffprobe/ffmpeg calls (DEBUG level)
- Exceptions with stack traces

**Common signatures:**
- `ffprobe not found` → Install ffprobe
- `File not found` → Check file path
- `No duration in file` → File may be corrupt or unsupported
- `QMediaPlayer error` → Preview codec issue (expected for some files)

### 2. Check Status Bar and Toast Messages

**What to look for:**
- Non-blocking error messages appear as toast/status messages
- "Cannot split at clip start/end"
- "Invalid file format"
- "Added X clips"

### 3. Check UI State

**What to verify:**
- Is a clip selected? (Some operations require selection)
- Is preview loaded? (Duration should still show even if preview fails)
- Is playhead at valid position? (Split requires valid playhead position)

### 4. Typical Failure Signatures

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| Duration shows "00:00" | ffprobe not found or file corrupt | Install ffprobe; check file |
| Preview shows "(no preview available)" | Codec issue (expected) | Duration should still work; proceed |
| Split button disabled/error | Invalid split position (0ms or end) | Seek to middle of clip |
| Trim sliders unresponsive | No clip selected | Select a clip |
| File List and Timeline out of sync | Bug (should never happen) | Report as critical bug |
| Undo does nothing | No undoable action in history | Expected if no operations performed |
| App crashes on launch | Missing dependency or Qt plugin issue | Check requirements.txt; reinstall |

### 5. Enabling Debug Logging for Deep Dive

**Steps:**
1. Edit `src/multicam_editor/main.py`
2. Change `configure_logging()` to `configure_logging(level=logging.DEBUG)`
3. Re-run the app
4. Reproduce the issue
5. Capture console output (copy/paste or redirect to file)

**What DEBUG logs reveal:**
- ffprobe command and output
- Cache hits/misses
- Trim value changes
- Split calculations
- Command redo/undo execution

---

## Summary Checklist for QA

Use this checklist for each QA session:

- [ ] **Launch:** App starts without errors
- [ ] **Add videos:** 2-3 files added successfully
- [ ] **Selection sync:** File List ↔ Timeline selection always matches
- [ ] **Order sync:** File List and Timeline order always matches
- [ ] **Preview:** Video loads or shows fallback; duration always populates
- [ ] **Play/Seek:** Playback and seeking work
- [ ] **Trim:** In/Out sliders work; timeline updates; undo/redo work
- [ ] **Split:** Split at valid position works; undo merges back; redo splits again
- [ ] **Reorder:** Drag-and-drop works; both views update; undo/redo work
- [ ] **Remove:** Delete removes clips; undo restores in correct position
- [ ] **Undo/Redo:** All operations are undoable and redoable
- [ ] **Edge cases:** Invalid splits/trims show non-blocking errors
- [ ] **Logs:** No unexpected errors in console (except expected codec warnings)

---

## Contact / Bug Reporting

- For issues, use the project's issue tracker or `/reportbug` command (if available)
- Include:
  - Steps to reproduce
  - Expected vs actual behavior
  - Console logs (especially with DEBUG logging enabled)
  - OS version and Python version
  - ffprobe/ffmpeg version (`ffprobe -version`)
