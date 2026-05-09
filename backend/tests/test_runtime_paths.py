"""Tests for the path resolution helpers used by the FastAPI app.

resource_root() and app_data_root() are pure helpers that get imported
from many modules at module-load time, so a regression here breaks
imports rather than producing a clean error message. Lock the
behaviour down explicitly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.runtime_paths import app_data_root, resource_root


def test_resource_root_in_source_checkout() -> None:
    # Outside PyInstaller, resource_root() should point at backend/
    # (the directory that contains both `app/` and `params/`).
    root = resource_root()
    assert root.is_dir()
    assert (root / "app").is_dir()
    assert (root / "params").is_dir()


def test_resource_root_honours_meipass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    try:
        assert resource_root() == tmp_path
    finally:
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)


def test_app_data_root_uses_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "app-data"
    assert not target.exists()
    monkeypatch.setenv("APP_DATA_DIR", str(target))
    root = app_data_root()
    assert root == target
    assert root.is_dir()  # mkdir parents=True, exist_ok=True


def test_app_data_root_falls_back_to_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APP_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    root = app_data_root()
    # Path.cwd() may resolve symlinks differently from tmp_path on macOS,
    # so compare resolved paths instead of raw values.
    assert root.resolve() == tmp_path.resolve()
