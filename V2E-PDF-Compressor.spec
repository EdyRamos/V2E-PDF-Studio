# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH)
pyside_datas, pyside_binaries, pyside_hidden = collect_all("PySide6")
pymupdf_datas, pymupdf_binaries, pymupdf_hidden = collect_all("pymupdf")

datas = [
    (str(project_root / "vendor" / "ghostscript" / "win64"), "vendor/ghostscript/win64"),
    (str(project_root / "docs"), "docs"),
    (str(project_root / "LICENSE"), "."),
    (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project_root / "build" / "update-config.json"), "."),
] + pyside_datas + pymupdf_datas

a = Analysis(
    [str(project_root / "app.py")],
    pathex=[str(project_root / "src")],
    binaries=pyside_binaries + pymupdf_binaries,
    datas=datas,
    hiddenimports=pyside_hidden + pymupdf_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="V2E-PDF-Compressor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    codesign_identity=None,
    entitlements_file=None,
    version=str(project_root / "build" / "version_info.txt"),
)
