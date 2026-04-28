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
