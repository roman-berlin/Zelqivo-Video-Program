# Third-Party Licenses

Zelqivo itself is licensed under Apache-2.0. This file lists the third-party
packages we depend on, their licenses, and what each license asks from us when
we distribute the app to users.

Versions below were read from the development virtual environment on 2026-08-06
(`pip-licenses`, see [Regenerating this file](#regenerating-this-file)).

**License obligations in short:**

- **MIT / BSD / ISC / Apache-2.0 / MPL-2.0 (unmodified)** — keep the copyright
  notice and license text in the shipped app. Nothing else.
- **LGPL (2.1 or 3.0)** — the library must stay **replaceable**: ship it as a
  separate, dynamically-linked file the user can swap out, include the LGPL
  text, and say where the source can be found. Never compile it statically
  into our own code.
- **GPL** — not compatible with shipping a closed Pro tier next to it. We must
  not distribute any GPL-licensed binary. See the warnings below.

---

## Runtime dependencies (shipped to users)

| Package | Version | License | What it's for | Obligation when distributing |
|---|---|---|---|---|
| PySide6 | 6.11.1 | LGPL-3.0 | Qt GUI framework (Python bindings) | Keep replaceable / dynamically linked, ship LGPL text — see note 1 |
| PySide6_Essentials | 6.11.1 | LGPL-3.0 | Core Qt modules (Widgets, Gui, Core) | Same as PySide6 — note 1 |
| PySide6_Addons | 6.11.1 | LGPL-3.0 | Qt Multimedia (video preview) | Same as PySide6 — notes 1 and 3 |
| shiboken6 | 6.11.1 | LGPL-3.0 | Binding generator runtime for PySide6 | Same as PySide6 — note 1 |
| numpy | 2.4.6 | BSD-3-Clause (plus other permissive parts) | Array math everywhere | Keep notice |
| opencv-python | 5.0.0.93 | Apache-2.0 | Video frame analysis | Keep notice |
| ffmpeg-python | 0.2.0 | Apache-2.0 | Builds FFmpeg command lines (does not contain FFmpeg) | Keep notice |
| moviepy | 2.2.1 | MIT | Video editing / rendering | Keep notice |
| imageio | 2.37.4 | BSD-2-Clause | Image I/O (moviepy dependency) | Keep notice |
| imageio-ffmpeg | 0.6.0 | BSD-2-Clause (wheel only) | FFmpeg wrapper for moviepy | **Warning — bundles a GPL ffmpeg binary, see note 4** |
| pillow | 11.3.0 | MIT-CMU | Image handling (moviepy dependency) | Keep notice |
| proglog | 0.1.12 | MIT | Progress logging (moviepy dependency) | Keep notice |
| decorator | 5.3.1 | BSD-2-Clause | Helper (moviepy dependency) | Keep notice |
| tqdm | 4.70.0 | MPL-2.0 and MIT | Progress bars | Keep notice (we do not modify MPL files) |
| librosa | 0.11.0 | ISC | Audio analysis (speaker detection) | Keep notice |
| audioread | 3.1.0 | MIT | Audio decoding (librosa dependency) | Keep notice |
| numba | 0.66.0 | BSD-2-Clause | JIT compiler (librosa dependency) | Keep notice |
| llvmlite | 0.48.0 | BSD-2-Clause and Apache-2.0 with LLVM exception | LLVM bindings (numba dependency) | Keep notice |
| joblib | 1.5.3 | BSD-3-Clause | Parallelism (librosa/scikit-learn dependency) | Keep notice |
| scipy | 1.18.0 | BSD-3-Clause | Scientific computing (librosa dependency) | Keep notice |
| scikit-learn | 1.9.0 | BSD-3-Clause | Machine learning (librosa dependency) | Keep notice |
| soxr | 1.1.0 | LGPL-2.1-or-later | Audio resampling (librosa dependency, wraps libsoxr) | Keep replaceable / dynamically linked, ship LGPL text — note 2 |
| lazy-loader | 0.5 | BSD-3-Clause | Import helper (librosa dependency) | Keep notice |
| msgpack | 1.2.1 | Apache-2.0 | Serialization (librosa dependency) | Keep notice |
| pooch | 1.9.0 | BSD-3-Clause | Data fetching (librosa dependency) | Keep notice |
| soundfile | 0.14.0 | BSD-3-Clause (wheel) | Audio file reading/writing | **Bundles libsndfile, which is LGPL-2.1 — note 2** |
| cffi | 2.1.1 | MIT-0 | C bindings (soundfile dependency) | None required (we keep the notice anyway) |
| pycparser | 3.0 | BSD-3-Clause | C parser (cffi dependency) | Keep notice |

A few small transitive packages also end up in the shipped tree (the `requests`
chain pulled in by pooch — requests, urllib3, certifi, idna, charset-normalizer —
plus threadpoolctl, packaging, platformdirs, typing_extensions). All are
permissive or notice-only (MIT / BSD / Apache-2.0 / MPL-2.0 / PSF-2.0): keep
their notices. The full list appears when you regenerate this file.

## Development-only tools (not distributed)

pytest, pytest-cov, pytest-qt, coverage, black, ruff, mypy, pip-licenses, and
PyInstaller are development tools only — they are never shipped to users, so
their licenses put no obligations on the distributed app (PyInstaller is GPLv2
but with a special exception that explicitly allows distributing the apps it
builds under any license).

---

## Hand-verified special cases

**Note 1 — PySide6 / Qt is LGPLv3.** pip reports it as "LGPL-3.0 OR GPL-2.0 OR
GPL-3.0"; we use it under the **LGPL-3.0** option. Compliance plan: PyInstaller
**onedir** builds (Qt libraries stay separate `.dll`/`.so` files, so a user can
replace them) plus written relinking instructions. The relinking docs are
**Phase 0.4, still pending**.

**Note 2 — LGPL native libraries hidden inside wheels.** `soundfile` bundles
**libsndfile** (LGPL-2.1) and `soxr` wraps **libsoxr** (LGPL-2.1-or-later).
Both ship as separate shared-library files inside the wheels, which satisfies
the "replaceable" requirement — keep it that way (never merge or statically
link them), and include the LGPL-2.1 text in the distribution.

**Note 3 — Qt Multimedia ships its own FFmpeg.** PySide6_Addons contains Qt
Multimedia, which carries its **own private FFmpeg** for video playback. At
runtime the app log shows: `FFmpeg version 7.1.3 LGPL`. This is an LGPL build,
so it is fine to ship — but it is a third FFmpeg copy in our tree (see the
FFmpeg section below) and must stay a separate, replaceable library.

**Note 4 — imageio-ffmpeg: GPL contamination risk.** The `imageio-ffmpeg`
Python wheel is BSD-2-Clause, but the **ffmpeg binary it bundles as a data
file is a GPL build**. Our PyInstaller spec currently copies that binary into
the installer: `multicam_editor.spec` lines 66–71 call
`collect_data_files('imageio_ffmpeg')` as a "fallback" FFmpeg. **Shipping that
binary would make the distributed app carry GPL code**, which conflicts with
our Apache-2.0 + closed Pro-tier plan.
**Recommendation: exclude the imageio_ffmpeg data files from the spec.**
Tracked for Phase 0.2 — see `docs/planning/PHASE_0_2_PLAN.md`.

---

## FFmpeg copies in the shipped tree

There are currently **three** FFmpeg copies to keep track of:

1. **Our bundled `ffmpeg.exe` / `ffprobe.exe`** (`tools/ffmpeg/`, added by
   `multicam_editor.spec` lines 73–81). Currently taken from a
   `ffmpeg-7.1.1-full_build`, which is a **GPL** build. Being replaced in
   **Phase 0.2** by a BtbN **LGPL** build
   (`TODO: exact download URL + SHA-256 checksum once Roman downloads it on
   the Windows build machine`).
2. **Qt Multimedia's private FFmpeg** (inside PySide6_Addons) — version 7.1.3,
   **LGPL** build, used only for in-app video preview. Fine to ship as-is.
3. **imageio-ffmpeg's bundled ffmpeg** — **GPL** build, currently pulled into
   the installer as a fallback by spec lines 66–71. **To be removed**
   (Phase 0.2, see Note 4 above).

Target end state after Phase 0.2: exactly two FFmpeg copies, both LGPL
(ours from BtbN, plus Qt Multimedia's).

---

## Regenerating this file

Raw license data comes from the project virtual environment:

```
.venv/bin/pip-licenses --format=markdown --with-urls
```

(On Windows: `.venv\Scripts\pip-licenses --format=markdown --with-urls`.)

The output mixes runtime and development packages — keep the runtime /
dev-only split and the hand-verified notes above when updating.
