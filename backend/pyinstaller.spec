# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the FastAPI sidecar.

Run from the `backend/` directory:

    pyinstaller --clean --noconfirm pyinstaller.spec

Output:
    dist/accompanist-server/                 (onedir bundle, fast cold start)
        accompanist-server[.exe]
        _internal/
            params/                          (YAML param sets)
            ...

The onedir layout matters for sidecar startup latency: onefile would
extract ~100MB of Python + lxml + music21 to a temp dir on every spawn,
which adds 3-5s on cold boots. Tauri ships the directory as-is.
"""

from pathlib import Path

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
    "music21.corpus",          # ~50MB of bundled scores, unused.
    "music21.audioSearch",
    "music21.demos",
    "music21.alpha",
    "music21.figuredBass",
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="accompanist-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX trips antivirus heuristics on Windows.
    console=True,              # We need stdout for the READY line.
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
