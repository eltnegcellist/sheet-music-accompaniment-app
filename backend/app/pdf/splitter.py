"""Split long PDFs into page-bounded chunks for OMR.

Audiveris's memory footprint scales with the number of pages it has open at
once; a 60-page violin sonata can OOM the JVM and lose all progress. By
slicing the input into smaller chunks (~6 pages by default) we trade a few
extra Audiveris invocations for resilience: a single bad chunk no longer
takes down the whole run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


@dataclass
class PdfChunk:
    """A page-range slice of the original PDF.

    `page_offset` is 0-based and points at the first source page included in
    this chunk. It's preserved so layout coordinates returned by Audiveris
    (which are per-chunk) can be remapped back to the original PDF when the
    merger stitches results together.
    """

    path: Path
    page_offset: int
    page_count: int


def count_pages(pdf_path: Path) -> int:
    """Return the number of pages in `pdf_path`. 0 on parse failure."""
    try:
        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception as exc:  # pypdf raises a few different types
        logger.warning("count_pages failed for %s: %s", pdf_path, exc)
        return 0


def split_pdf(
    pdf_path: Path,
    output_dir: Path,
    *,
    pages_per_chunk: int = 6,
) -> list[PdfChunk]:
    """Slice `pdf_path` into chunks of at most `pages_per_chunk` pages each.

    Always returns at least one chunk. When the source has `pages_per_chunk`
    pages or fewer, the returned chunk points at the original file and
    `page_count == total`.

    The split is stable: a 13-page PDF with a 6-page chunk size produces
    chunks of (6, 6, 1) pages — never (5, 5, 3). This makes test fixtures
    easier to reason about and keeps Audiveris memory usage predictable.
    """
    if pages_per_chunk <= 0:
        raise ValueError("pages_per_chunk must be >= 1")
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    if total == 0:
        return []
    if total <= pages_per_chunk:
        return [PdfChunk(path=pdf_path, page_offset=0, page_count=total)]

    chunks: list[PdfChunk] = []
    for chunk_idx, start in enumerate(range(0, total, pages_per_chunk)):
        end = min(start + pages_per_chunk, total)
        chunk_path = output_dir / f"chunk_{chunk_idx:03d}_{start:03d}_{end:03d}.pdf"
        writer = PdfWriter()
        for page_idx in range(start, end):
            writer.add_page(reader.pages[page_idx])
        with chunk_path.open("wb") as fh:
            writer.write(fh)
        chunks.append(
            PdfChunk(path=chunk_path, page_offset=start, page_count=end - start)
        )
    return chunks


def iter_chunk_files(chunks: Iterable[PdfChunk]) -> list[Path]:
    """Convenience: list of paths corresponding to each chunk."""
    return [c.path for c in chunks]
