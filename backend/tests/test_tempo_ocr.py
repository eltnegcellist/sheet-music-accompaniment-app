"""Tests for the Tesseract tempo fallback.

These tests exercise the module's public entry point with pytesseract and
pdf2image mocked out — actually running Tesseract here would make the test
suite depend on system packages we don't want to require in CI.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from app.ocr import tempo_ocr


@pytest.fixture(autouse=True)
def _reset_cached_modules(monkeypatch):
    """Ensure each test can substitute its own pdf2image / pytesseract stubs."""
    for name in ("pdf2image", "pytesseract"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    yield


class _FakeImage:
    def __init__(self, size=(1000, 1000)):
        self.size = size

    def crop(self, _box):
        return self


def _install_stubs(monkeypatch, text: str) -> None:
    pdf2image_mod = types.ModuleType("pdf2image")
    pdf2image_mod.convert_from_path = lambda *args, **kwargs: [_FakeImage()]  # type: ignore[attr-defined]

    pytesseract_mod = types.ModuleType("pytesseract")
    pytesseract_mod.image_to_string = lambda *args, **kwargs: text  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "pdf2image", pdf2image_mod)
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract_mod)


def test_matches_andantino(tmp_path: Path, monkeypatch):
    _install_stubs(monkeypatch, "Salut d'Amour\nAndantino\n")
    result = tempo_ocr.extract_tempo_from_pdf(tmp_path / "fake.pdf")
    assert result is not None
    assert result.bpm == 90.0
    assert result.source == "ocr-word"
    assert result.matched_word == "andantino"


def test_matches_allegro_moderato(tmp_path: Path, monkeypatch):
    _install_stubs(monkeypatch, "Prelude\nAllegro moderato\n")
    result = tempo_ocr.extract_tempo_from_pdf(tmp_path / "fake.pdf")
    assert result is not None
    assert result.bpm == 118.0
    assert result.matched_word == "allegro moderato"


def test_no_match_returns_none(tmp_path: Path, monkeypatch):
    _install_stubs(monkeypatch, "Just a title with no tempo marking\n")
    assert tempo_ocr.extract_tempo_from_pdf(tmp_path / "fake.pdf") is None


def test_missing_deps_return_none(tmp_path: Path, monkeypatch):
    # Simulate a host without pytesseract / pdf2image installed.
    import builtins

    original_import = builtins.__import__

    def _raise_on_pdf2image(name, *args, **kwargs):
        if name == "pdf2image":
            raise ImportError("pdf2image not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raise_on_pdf2image)
    assert tempo_ocr.extract_tempo_from_pdf(tmp_path / "fake.pdf") is None
