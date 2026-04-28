"""Unit tests for the AnalyzeCache disk cache."""

from __future__ import annotations

from pathlib import Path

from app.cache import AnalyzeCache, hash_pdf_bytes


def test_hash_is_stable_and_order_sensitive() -> None:
    a = hash_pdf_bytes(b"abc", b"|", b"def")
    b = hash_pdf_bytes(b"abc", b"|", b"def")
    c = hash_pdf_bytes(b"def", b"|", b"abc")
    assert a == b
    assert a != c


def test_put_then_get_roundtrip(tmp_path: Path) -> None:
    cache = AnalyzeCache(root=tmp_path)
    payload = {"music_xml": "<x/>", "warnings": ["a"], "tempo_bpm": 100.0}
    cache.put("KEY1", "v5_real_pdf", payload)
    got = cache.get("KEY1", "v5_real_pdf")
    assert got is not None
    assert got["music_xml"] == "<x/>"
    assert got["warnings"] == ["a"]


def test_miss_returns_none(tmp_path: Path) -> None:
    cache = AnalyzeCache(root=tmp_path)
    assert cache.get("missing", "v1") is None


def test_param_set_namespacing(tmp_path: Path) -> None:
    cache = AnalyzeCache(root=tmp_path)
    cache.put("K", "v1", {"music_xml": "v1"})
    cache.put("K", "v2", {"music_xml": "v2"})
    assert cache.get("K", "v1") == {"music_xml": "v1"}
    assert cache.get("K", "v2") == {"music_xml": "v2"}


def test_invalidate_specific_param_set(tmp_path: Path) -> None:
    cache = AnalyzeCache(root=tmp_path)
    cache.put("K", "v1", {"music_xml": "v1"})
    cache.put("K", "v2", {"music_xml": "v2"})
    cache.invalidate("K", "v1")
    assert cache.get("K", "v1") is None
    assert cache.get("K", "v2") is not None


def test_invalidate_all_param_sets_for_key(tmp_path: Path) -> None:
    cache = AnalyzeCache(root=tmp_path)
    cache.put("K", "v1", {"music_xml": "v1"})
    cache.put("K", "v2", {"music_xml": "v2"})
    cache.invalidate("K", None)
    assert cache.get("K", "v1") is None
    assert cache.get("K", "v2") is None


def test_corrupt_cache_file_returns_miss(tmp_path: Path) -> None:
    cache = AnalyzeCache(root=tmp_path)
    cache.root.mkdir(parents=True, exist_ok=True)
    cache.path_for("BAD", "v1").write_text("not json", encoding="utf-8")
    assert cache.get("BAD", "v1") is None
