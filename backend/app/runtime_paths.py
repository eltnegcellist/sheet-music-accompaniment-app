"""Path resolution helpers that work in both source checkouts and PyInstaller bundles.

When the backend is frozen with PyInstaller (`--onedir` / `--onefile`), the
runtime layout differs from a normal `pip install -e .` checkout:

* Bundled data files (YAML params, schema, tessdata, music21 corpus) live
  under `sys._MEIPASS` rather than next to the source tree.
* Writable state (analyze cache, logs) must go to an OS-specific user data
  directory chosen by the Tauri host, not the CWD.

`resource_root()` returns the directory that contains read-only bundled
assets. `app_data_root()` returns the directory for writable state.

Both helpers are pure and have no dependency on FastAPI / Tauri so they
can be imported from any module that resolves a path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    """Return the root directory for read-only bundled resources.

    * Frozen (PyInstaller): `sys._MEIPASS`.
    * Source checkout:      the `backend/` directory (parent of `app/`).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[1]


def app_data_root() -> Path:
    """Return the root directory for writable application state.

    Resolution order:
        1. `APP_DATA_DIR` env var (set by the Tauri host at sidecar spawn).
        2. The current working directory (legacy Docker/dev behaviour).

    The returned directory is created if it does not already exist so callers
    can immediately write into subpaths.
    """
    env = os.environ.get("APP_DATA_DIR")
    root = Path(env) if env else Path.cwd()
    root.mkdir(parents=True, exist_ok=True)
    return root
