# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MulticamEditor.

Build command:
    pyinstaller multicam_editor.spec

Output:
    dist/MulticamEditor/MulticamEditor.exe
"""

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
    'tqdm',
]

# Add all cv2 submodules
hiddenimports += collect_submodules('cv2')

# FFmpeg binaries to bundle
ffmpeg_binaries = [
    (r'C:\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe', 'tools/ffmpeg'),
    (r'C:\ffmpeg-7.1.1-full_build\bin\ffprobe.exe', 'tools/ffmpeg'),
]

a = Analysis(
    ['src/multicam_editor/main.py'],
    pathex=[],
    binaries=[],
    datas=ffmpeg_binaries,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused large packages
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'notebook',
        'jupyter',
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
    # icon='assets/icon.ico',  # Uncomment if icon is added later
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
