# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MulticamEditor (Zelqivo).

Build command:
    pyinstaller multicam_editor.spec --clean

Output:
    dist/MulticamEditor/MulticamEditor.exe

Bundled:
    - FFmpeg binaries (tools/ffmpeg/, taken from the ZELQIVO_FFMPEG_DIR folder)
    - Qt Multimedia plugins
    - All required Python packages
"""

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Collect all PySide6 submodules to ensure complete Qt functionality
hiddenimports = [
    # Core Qt modules
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    # Multimedia modules (required for video preview)
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    # Standard library modules that may be dynamically imported
    'json',
    'logging.handlers',
    'tempfile',
    'subprocess',
    'pathlib',
    # Third-party modules
    'numpy',
    'cv2',
    'ffmpeg',
    'moviepy',
    'moviepy.editor',
    'moviepy.video',
    'moviepy.video.io',
    'moviepy.video.io.ffmpeg_reader',
    'moviepy.video.io.ffmpeg_writer',
    'moviepy.audio',
    'moviepy.audio.io',
    'moviepy.audio.io.readers',
    'tqdm',
    # imageio for moviepy compatibility
    'imageio',
    'imageio_ffmpeg',
    'imageio_ffmpeg.binaries',
    # AI/Audio processing
    'librosa',
    'soundfile',
]

# Add all cv2 submodules
hiddenimports += collect_submodules('cv2')

# Add moviepy submodules
hiddenimports += collect_submodules('moviepy')

# NOTE: imageio_ffmpeg data files are deliberately NOT collected — the wheel
# bundles a GPL ffmpeg binary we must not ship (see docs/THIRD_PARTY.md note 4).
# The Python module itself stays in hiddenimports; only its binary data goes.
datas = []

# FFmpeg binaries to bundle - directory comes from ZELQIVO_FFMPEG_DIR
# (use an LGPL build, e.g. BtbN *-lgpl: https://github.com/BtbN/FFmpeg-Builds/releases)
ffmpeg_dir = os.environ.get('ZELQIVO_FFMPEG_DIR', '')
ffmpeg_path = os.path.join(ffmpeg_dir, 'ffmpeg.exe')
ffprobe_path = os.path.join(ffmpeg_dir, 'ffprobe.exe')

if ffmpeg_dir and os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
    datas += [
        (ffmpeg_path, 'tools/ffmpeg'),
        (ffprobe_path, 'tools/ffmpeg'),
    ]
else:
    print("WARNING: FFmpeg binaries not found.")
    print("  Set ZELQIVO_FFMPEG_DIR to a folder containing ffmpeg.exe and ffprobe.exe")
    print("  from an LGPL build (BtbN *-lgpl: https://github.com/BtbN/FFmpeg-Builds/releases).")
    print("  The EXE may not work without FFmpeg in PATH.")

a = Analysis(
    ['src/multicam_editor/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused large packages to reduce size
        'tkinter',
        'matplotlib',
        'IPython',
        'notebook',
        'jupyter',
        # AI packages (optional, not bundled in core build)
        'torch',
        'pyannote',
        'speechbrain',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MulticamEditor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed mode - no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='Installer/assets/icons/Zelqivo.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MulticamEditor',
)

