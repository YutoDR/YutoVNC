# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for YutoVNC.

Creates a clean, windowed Windows desktop executable in dist/YutoVNC/
with multi-size icon, bundled assets, and hidden imports.
"""

import sys
import os

block_cipher = None

BASE_DIR = os.path.abspath(SPECPATH)

# Collect data assets
datas = [
    (os.path.join(BASE_DIR, 'assets'), 'assets'),
]

# If bundled bin directory exists, include it
bin_dir = os.path.join(BASE_DIR, 'bin')
if os.path.exists(bin_dir) and os.listdir(bin_dir):
    datas.append((bin_dir, 'bin'))

hidden_imports = [
    'sqlite3',
    'ctypes',
    'ctypes.wintypes',
    'ipaddress',
    'concurrent.futures',
    'tkinter',
    'tkinter.ttk',
    'tkinter.messagebox',
    'tkinter.filedialog',
    'tkinter.simpledialog',
    'yutovnc',
    'yutovnc.models',
    'yutovnc.database',
    'yutovnc.security',
    'yutovnc.monitor',
    'yutovnc.vnc_launcher',
    'yutovnc.scanner',
    'yutovnc.exporter',
    'yutovnc.theme',
    'yutovnc.paths',
    'yutovnc.ui',
    'yutovnc.ui.main_window',
    'yutovnc.ui.host_dialog',
    'yutovnc.ui.settings_dialog',
    'yutovnc.ui.import_export_dialog',
    'yutovnc.ui.session_tab',
    'yutovnc.ui.scanner_dialog',
]

a = Analysis(
    ['main.py'],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'numpy', 'pandas', 'IPython', 'notebook', 'pytest'],
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
    name='YutoVNC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                  # Mode --windowed / --noconsole
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(BASE_DIR, 'assets', 'icon.ico'),
    version_info=None
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YutoVNC',
)
