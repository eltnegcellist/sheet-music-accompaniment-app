"""Unit tests for the PDF chunk splitter."""

from __future__ import annotations

from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")

from app.pdf.splitter import count_pages, split_pdf  # noqa: E402


def _make_pdf(path: Path, num_pages: int) -> None:
    """Create a minimal multi-page PDF using pypdf's blank-page helper."""
    writer = pypdf.PdfWriter()
    for _ in range(num_pages):
        # 612x792 = US letter in PDF points; size doesn't matter for tests.
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)


def test_count_pages(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 5)
    assert count_pages(pdf) == 5


def test_short_pdf_returns_single_chunk_pointing_at_original(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 4)
    chunks = split_pdf(pdf, tmp_path / "out", pages_per_chunk=6)
    assert len(chunks) == 1
    assert chunks[0].path == pdf
    assert chunks[0].page_offset == 0
    assert chunks[0].page_count == 4


def test_long_pdf_split_evenly_with_remainder_chunk(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 13)
    chunks = split_pdf(pdf, tmp_path / "out", pages_per_chunk=6)
    assert [c.page_count for c in chunks] == [6, 6, 1]
    assert [c.page_offset for c in chunks] == [0, 6, 12]
    for c in chunks:
        assert c.path.exists()
        assert count_pages(c.path) == c.page_count


def test_pages_per_chunk_must_be_positive(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 3)
    with pytest.raises(ValueError):
        split_pdf(pdf, tmp_path / "out", pages_per_chunk=0)


def test_count_pages_falls_back_to_pdf2image(tmp_path: Path, monkeypatch) -> None:
    """When pypdf raises, count_pages must try the poppler-backed paths."""
    from app.pdf import splitter

    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 5)

    def boom_pypdf(_path):
        return 0

    monkeypatch.setattr(splitter, "_count_with_pypdf", boom_pypdf)

    def fake_pdf2image(_path):
        return 5

    monkeypatch.setattr(splitter, "_count_with_pdf2image", fake_pdf2image)

    assert splitter.count_pages(pdf) == 5


def test_count_pages_falls_back_to_subprocess_pdfinfo(
    tmp_path: Path, monkeypatch
) -> None:
    """If both pypdf and pdf2image fail we still try the bare CLI."""
    from app.pdf import splitter

    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 7)

    monkeypatch.setattr(splitter, "_count_with_pypdf", lambda _: 0)
    monkeypatch.setattr(splitter, "_count_with_pdf2image", lambda _: 0)
    monkeypatch.setattr(splitter, "_count_with_pdfinfo_subprocess", lambda _: 7)

    assert splitter.count_pages(pdf) == 7


def test_count_pages_returns_zero_when_every_backend_fails(
    tmp_path: Path, monkeypatch
) -> None:
    from app.pdf import splitter

    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 3)

    monkeypatch.setattr(splitter, "_count_with_pypdf", lambda _: 0)
    monkeypatch.setattr(splitter, "_count_with_pdf2image", lambda _: 0)
    monkeypatch.setattr(splitter, "_count_with_pdfinfo_subprocess", lambda _: 0)

    assert splitter.count_pages(pdf) == 0


def test_split_pdf_uses_poppler_when_pypdf_split_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """A pypdf split failure should fall back to poppler split."""
    from app.pdf import splitter

    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 13)

    # Force the pypdf path to raise so the fallback is exercised.
    def raise_split(*_, **__):
        raise RuntimeError("pretend pypdf can't read this PDF")

    monkeypatch.setattr(splitter, "_split_with_pypdf", raise_split)

    poppler_calls: list[tuple] = []

    def fake_poppler_split(pdf_path, output_dir, pages_per_chunk, total):
        poppler_calls.append((pages_per_chunk, total))
        return [splitter.PdfChunk(path=pdf_path, page_offset=0, page_count=total)]

    monkeypatch.setattr(splitter, "_poppler_available", lambda: True)
    monkeypatch.setattr(splitter, "_split_with_poppler", fake_poppler_split)

    chunks = splitter.split_pdf(pdf, tmp_path / "out", pages_per_chunk=6)
    assert len(chunks) == 1
    assert poppler_calls == [(6, 13)]


def test_slice_pdf_uses_poppler_when_pypdf_slice_fails(
    tmp_path: Path, monkeypatch
) -> None:
    from app.pdf import splitter

    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, 8)

    monkeypatch.setattr(
        splitter,
        "_slice_with_pypdf",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("nope")),
    )

    poppler_calls: list[tuple] = []

    def fake_poppler_slice(pdf_path, output_path, *, start_page, end_page):
        poppler_calls.append((start_page, end_page))
        output_path.write_bytes(b"%PDF-1.0\n%placeholder\n")
        return output_path

    monkeypatch.setattr(splitter, "_poppler_available", lambda: True)
    monkeypatch.setattr(splitter, "_slice_with_poppler", fake_poppler_slice)

    out = tmp_path / "out.pdf"
    splitter.slice_pdf(pdf, out, start_page=2, end_page=5)
    assert poppler_calls == [(2, 5)]
    assert out.exists()
