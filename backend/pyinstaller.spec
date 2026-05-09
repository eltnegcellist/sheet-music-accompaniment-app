# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the FastAPI sidecar.

Run from the `backend/` directory:

    pyinstaller --clean --noconfirm pyinstaller.spec                    # onedir
    PYINSTALLER_MODE=onefile pyinstaller --clean --noconfirm pyinstaller.spec

Output (PYINSTALLER_MODE=onedir, default):
    dist/accompanist-server/                 (directory bundle, fast cold start)
        accompanist-server[.exe]
        _internal/
            params/                          (YAML param sets)
            ...

Output (PYINSTALLER_MODE=onefile):
    dist/accompanist-server[.exe]            (single self-extracting binary)

The onedir layout is preferred for `tauri dev` — Tauri's externalBin
loader reuses the directory in place and cold start is instantaneous
because nothing is unpacked. For `tauri build`, externalBin only
copies a single file into the bundled .app, leaving the onedir
sibling tree behind. Use onefile mode in that case to ship a binary
that bootstraps itself; cold start jumps to ~3-5s on first launch
while PyInstaller unpacks ~100MB to a temp dir, but subsequent
launches reuse that cache.
"""

import os
from pathlib import Path

PYINSTALLER_MODE = os.environ.get("PYINSTALLER_MODE", "onedir")
if PYINSTALLER_MODE not in ("onedir", "onefile"):
    raise SystemExit(
        f"PYINSTALLER_MODE must be 'onedir' or 'onefile', got {PYINSTALLER_MODE!r}"
    )

block_cipher = None

ROOT = Path(SPECPATH).resolve()
ENTRY = str(ROOT / "app" / "server.py")

# ---------------------------------------------------------------------------
# Bundled read-only resources (resolved at runtime via runtime_paths.resource_root()
# which returns sys._MEIPASS in frozen mode).
# ---------------------------------------------------------------------------
datas = [
    (str(ROOT / "params"), "params"),
]

# ---------------------------------------------------------------------------
# Hidden imports that PyInstaller's static analysis misses.
# ---------------------------------------------------------------------------
hiddenimports = [
    # uvicorn loads protocol/lifespan/loop modules by string at runtime.
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    # FastAPI's optional encoders.
    "email.mime.multipart",
    "email.mime.text",
    # music21 lazily imports its submodules.
    "music21.stream",
    "music21.note",
    "music21.chord",
    "music21.key",
    "music21.meter",
    "music21.tempo",
    "music21.musicxml.archiveTools",
    "music21.musicxml.m21ToXml",
    "music21.musicxml.xmlToM21",
]

# ---------------------------------------------------------------------------
# Excludes — keep the bundle small.
# ---------------------------------------------------------------------------
excludes = [
    # music21 sub-packages cannot be excluded individually: __init__.py
    # imports corpus, test, alpha, audioSearch, demos, figuredBass, etc
    # unconditionally and the package raises ImportError if any are
    # missing. We accept the ~120MB bundle cost; trimming would need a
    # forked music21 or a runtime hook.
    "matplotlib",              # pulled by music21 only for plot helpers.
    "tkinter",
    "IPython",
    "pytest",
    "tests",
]

a = Analysis(
    [ENTRY],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if PYINSTALLER_MODE == "onefile":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="accompanist-server",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,             # UPX trips antivirus heuristics on Windows.
        console=True,          # We need stdout for the READY line.
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="accompanist-server",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="accompanist-server",
    )
