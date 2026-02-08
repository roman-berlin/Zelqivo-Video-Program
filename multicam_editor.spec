# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MulticamEditor (Zelqivo).

Build command:
    pyinstaller multicam_editor.spec --clean

Output:
    dist/MulticamEditor/MulticamEditor.exe

Bundled:
    - FFmpeg binaries (tools/ffmpeg/)
    - Qt Multimedia plugins
    - All required Python packages
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all PyQt6 submodules to ensure complete Qt functionality
hiddenimports = [
    # Core Qt modules
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    # Multimedia modules (required for video preview)
    'PyQt6.QtMultimedia',
    'PyQt6.QtMultimediaWidgets',
    # SIP bindings
    'PyQt6.sip',
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

# Collect data files for imageio_ffmpeg (contains bundled ffmpeg as fallback)
datas = []
try:
    datas += collect_data_files('imageio_ffmpeg')
except Exception:
    pass  # imageio_ffmpeg not installed or no data files

# FFmpeg binaries to bundle - check if they exist
ffmpeg_path = r'C:\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe'
ffprobe_path = r'C:\ffmpeg-7.1.1-full_build\bin\ffprobe.exe'

if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
    datas += [
        (ffmpeg_path, 'tools/ffmpeg'),
        (ffprobe_path, 'tools/ffmpeg'),
    ]
else:
    print("WARNING: FFmpeg binaries not found at expected paths.")
    print(f"  Expected: {ffmpeg_path}")
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
    # icon='assets/icon.ico',  # Uncomment when icon is added
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

