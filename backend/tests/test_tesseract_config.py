"""Tests for the bundled-Tesseract configuration helper.

The Tauri sidecar exports TESSERACT_CMD pointing at the bundled
Tesseract binary. _configure_tesseract() applies that to pytesseract
on first call. Outside Tauri (no env var, or env points at nothing),
the helper must stay a no-op so the system Tesseract on PATH wins.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def tesseract_module(monkeypatch: pytest.MonkeyPatch):
    # Reload tempo_ocr so its module-level _TESSERACT_CONFIGURED flag is
    # reset for each test; otherwise the first test's `True` leaks.
    import app.ocr.tempo_ocr as mod

    mod = importlib.reload(mod)
    yield mod


def test_configure_does_nothing_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, tesseract_module
) -> None:
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    pytesseract = pytest.importorskip("pytesseract")
    before = pytesseract.pytesseract.tesseract_cmd
    tesseract_module._configure_tesseract()
    assert pytesseract.pytesseract.tesseract_cmd == before


def test_configure_uses_env_when_target_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path, tesseract_module
) -> None:
    pytesseract = pytest.importorskip("pytesseract")
    fake = tmp_path / "tesseract"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("TESSERACT_CMD", str(fake))

    tesseract_module._configure_tesseract()
    assert pytesseract.pytesseract.tesseract_cmd == str(fake)


def test_configure_ignores_env_pointing_at_missing_file(
    monkeypatch: pytest.MonkeyPatch, tesseract_module
) -> None:
    pytesseract = pytest.importorskip("pytesseract")
    monkeypatch.setenv("TESSERACT_CMD", "/does/not/exist")
    before = pytesseract.pytesseract.tesseract_cmd
    tesseract_module._configure_tesseract()
    # Bad env => we keep whatever pytesseract already had (system PATH copy).
    assert pytesseract.pytesseract.tesseract_cmd == before


def test_configure_only_applies_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path, tesseract_module
) -> None:
    pytesseract = pytest.importorskip("pytesseract")
    first = tmp_path / "first" / "tesseract"
    second = tmp_path / "second" / "tesseract"
    for f in (first, second):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("#!/bin/sh\nexit 0\n")
        f.chmod(0o755)

    monkeypatch.setenv("TESSERACT_CMD", str(first))
    tesseract_module._configure_tesseract()
    assert pytesseract.pytesseract.tesseract_cmd == str(first)

    # Second call should be a no-op even though the env now points elsewhere.
    monkeypatch.setenv("TESSERACT_CMD", str(second))
    tesseract_module._configure_tesseract()
    assert pytesseract.pytesseract.tesseract_cmd == str(first)
