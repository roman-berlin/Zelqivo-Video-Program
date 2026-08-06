# Zelqivo Roadmap

This is an honest roadmap. Items are ordered, not dated — things ship when they are ready.

A note on honesty: some features already exist in the codebase as hidden UI or partial
backends (see [FEATURE_REALITY.md](FEATURE_REALITY.md)). We do not count those as shipped.
A feature is "done" only when it is visible, working, and tested. Until then, it lives here.

Items marked **🙋 help wanted** are good places to contribute —
see [GOOD_FIRST_ISSUES.md](GOOD_FIRST_ISSUES.md).

---

## Now (in progress)

- **LGPL FFmpeg + hardware encoder selection.** Switch bundled FFmpeg to an LGPL build
  and pick the best H.264 encoder at runtime (NVIDIA, Intel, AMD, Apple VideoToolbox,
  with software fallback). Includes a "use my own FFmpeg" setting.
- **CI on Linux, Windows, and macOS.** Automated tests on every pull request, on all
  three platforms.
- **Error-handling hardening.** Clearer failure messages when FFmpeg is missing, inputs
  are bad, or a render step fails — instead of silent errors or crashes.

## Next

- **macOS as a first-class platform.** Today macOS mostly works but feels like a port.
  Planned: native title bar and menu bar (instead of the custom frameless window),
  FFmpeg discovery for Homebrew installs, Apple Silicon GPU detection, and a signed
  `.dmg` download.
- **Test coverage 48% → 60%.** Focused on the riskiest code paths first
  (pipeline, rendering, file handling). 🙋 help wanted
- **Clip-identity fixes.** A known bug where clips are tracked by fragile identity,
  which can confuse preflight checks and project state. Real, documented, unfixed —
  and next in line.

## Later

- **Timeline editing.** A timeline view exists in the code but is hidden — it is not
  ready for users yet. Wiring it up properly is a bigger job than it looks.
- **Trim panel.** Same story: hidden UI, partial backend, not yet connected end to end.
- **Multiview preview.** A grid view of all cameras at once. An early version caused
  system freezes and was removed — it needs a rebuild, not a re-enable. 🙋 help wanted
- **Highlights detection.** Automatic teaser/highlight clips. Today this is only a stub
  that returns an empty list, so we call it what it is: not implemented yet. 🙋 help wanted
- **`winget` package.** Easy install and updates on Windows. 🙋 help wanted

## Not planned (for the free app)

- **Cloud rendering.** The free desktop app will not get cloud rendering. Cloud and
  batch-processing features are the planned paid **Pro** tier — that is how the project
  stays funded.

The core desktop app stays free and Apache-2.0 forever.
