# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_tracker.py'],
    pathex=[],
    binaries=[],
    datas=[('kh2rt/milestones.json', 'kh2rt'), ('kh2rt/icons', 'kh2rt/icons'), ('kh2rt/fonts', 'kh2rt/fonts')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RE-Trace',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['kh2rt/icons/app.ico'],
)
