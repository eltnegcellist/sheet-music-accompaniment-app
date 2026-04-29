"""Split long PDFs into page-bounded chunks for OMR.

Audiveris's memory footprint scales with the number of pages it has open at
once; a 60-page violin sonata can OOM the JVM and lose all progress. By
slicing the input into smaller chunks (~6 pages by default) we trade a few
extra Audiveris invocations for resilience: a single bad chunk no longer
takes down the whole run.

Why we keep two backends
------------------------
pypdf is fast and pure-Python, but it is also strict about PDF structure
and bails out on a non-trivial number of real-world IMSLP PDFs (those
written by older typesetters, mildly damaged, or with restrictive
permission flags). When that happens the chunked OMR previously fell back
to "send the whole 34-page PDF to Audiveris" — which OOMs the JVM and
the user loses all progress.

We now fall back to the poppler-utils CLI (``pdfinfo`` / ``pdfseparate`` /
``pdfunite``) which is shipped as part of the Docker image already (it is
a hard dependency of ``pdf2image``). Poppler is dramatically more permissive
than pypdf; if Audiveris itself opened the PDF, poppler will too.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
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
    """Return the number of pages in `pdf_path`.

    Tries pypdf first, then poppler's ``pdfinfo`` (via pdf2image's helper),
    then a direct ``pdfinfo`` subprocess. Returns 0 only when every backend
    fails — which is genuinely rare because Audiveris itself relies on
    poppler (mediated by Audiveris's own PDF handling) and the JVM has yet
    to ingest a PDF that ``pdfinfo`` could not count.
    """
    pages = _count_with_pypdf(pdf_path)
    if pages > 0:
        return pages
    pages = _count_with_pdf2image(pdf_path)
    if pages > 0:
        return pages
    pages = _count_with_pdfinfo_subprocess(pdf_path)
    if pages > 0:
        return pages
    return 0


def _count_with_pypdf(pdf_path: Path) -> int:
    try:
        reader = PdfReader(str(pdf_path), strict=False)
        return len(reader.pages)
    except Exception as exc:
        logger.warning("count_pages: pypdf failed for %s: %s", pdf_path, exc)
        return 0


def _count_with_pdf2image(pdf_path: Path) -> int:
    try:
        from pdf2image import pdfinfo_from_path  # local import — optional
    except ImportError:
        return 0
    try:
        info = pdfinfo_from_path(str(pdf_path))
        pages = int(info.get("Pages", 0) or 0)
        if pages > 0:
            logger.info(
                "count_pages: pypdf failed; pdf2image (poppler) reports %d pages",
                pages,
            )
        return pages
    except Exception as exc:
        logger.warning("count_pages: pdf2image fallback failed: %s", exc)
        return 0


def _count_with_pdfinfo_subprocess(pdf_path: Path) -> int:
    if shutil.which("pdfinfo") is None:
        return 0
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        logger.warning("count_pages: pdfinfo subprocess failed: %s", exc)
        return 0
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                pages = int(line.split(":", 1)[1].strip())
                logger.info(
                    "count_pages: subprocess pdfinfo reports %d pages",
                    pages,
                )
                return pages
            except ValueError:
                continue
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

    Backend selection: pypdf is preferred. If pypdf fails (refuses to open
    the PDF, can't read a page, etc.) we fall back to ``pdfseparate`` +
    ``pdfunite`` from poppler-utils. The fallback is only attempted when
    the binaries are present on PATH; otherwise the function raises.
    """
    if pages_per_chunk <= 0:
        raise ValueError("pages_per_chunk must be >= 1")
    output_dir.mkdir(parents=True, exist_ok=True)

    total = count_pages(pdf_path)
    if total == 0:
        logger.warning(
            "split_pdf: page count probe returned 0 for %s; "
            "passing the original PDF through",
            pdf_path,
        )
        return [PdfChunk(path=pdf_path, page_offset=0, page_count=0)]
    if total <= pages_per_chunk:
        return [PdfChunk(path=pdf_path, page_offset=0, page_count=total)]

    # First try pypdf — it's fast, pure-Python, and usually succeeds.
    try:
        return _split_with_pypdf(pdf_path, output_dir, pages_per_chunk, total)
    except Exception as exc:
        logger.warning("split_pdf: pypdf split failed: %s; trying poppler", exc)

    if not _poppler_available():
        raise RuntimeError(
            "split_pdf: pypdf failed and poppler-utils (pdfseparate/pdfunite)"
            " are not on PATH; cannot chunk PDF."
        )
    return _split_with_poppler(pdf_path, output_dir, pages_per_chunk, total)


def _split_with_pypdf(
    pdf_path: Path,
    output_dir: Path,
    pages_per_chunk: int,
    total: int,
) -> list[PdfChunk]:
    reader = PdfReader(str(pdf_path), strict=False)
    if len(reader.pages) != total:
        # Mismatch suggests pypdf disagreed with poppler. Use the poppler
        # count and let pypdf raise if a requested page is missing.
        logger.info(
            "split_pdf: pypdf reports %d pages but probe says %d; using probe",
            len(reader.pages),
            total,
        )
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


def _split_with_poppler(
    pdf_path: Path,
    output_dir: Path,
    pages_per_chunk: int,
    total: int,
) -> list[PdfChunk]:
    """Slice using ``pdfseparate`` + ``pdfunite`` from poppler-utils."""
    chunks: list[PdfChunk] = []
    for chunk_idx, start in enumerate(range(0, total, pages_per_chunk)):
        end = min(start + pages_per_chunk, total)
        chunk_path = output_dir / f"chunk_{chunk_idx:03d}_{start:03d}_{end:03d}.pdf"
        _slice_with_poppler(pdf_path, chunk_path, start_page=start, end_page=end)
        chunks.append(
            PdfChunk(path=chunk_path, page_offset=start, page_count=end - start)
        )
    return chunks


def iter_chunk_files(chunks: Iterable[PdfChunk]) -> list[Path]:
    """Convenience: list of paths corresponding to each chunk."""
    return [c.path for c in chunks]


def slice_pdf(
    pdf_path: Path,
    output_path: Path,
    *,
    start_page: int,
    end_page: int | None = None,
) -> Path:
    """Write `pdf_path[start_page:end_page]` to `output_path`.

    Page indices are 0-based. `end_page` is exclusive; ``None`` means "to end".
    Always returns `output_path`. Raises if the requested range is empty.

    Like `split_pdf`, this prefers pypdf and falls back to poppler-utils
    for tolerance against malformed PDFs.
    """
    total = count_pages(pdf_path)
    if total == 0:
        raise ValueError(f"could not determine page count for {pdf_path}")
    if start_page < 0 or start_page >= total:
        raise ValueError(f"start_page {start_page} out of range (0..{total})")
    end = total if end_page is None else min(total, end_page)
    if end <= start_page:
        raise ValueError(
            f"empty page range: start={start_page} end={end_page} total={total}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _slice_with_pypdf(pdf_path, output_path, start_page, end)
    except Exception as exc:
        logger.warning("slice_pdf: pypdf failed: %s; trying poppler", exc)
    if not _poppler_available():
        raise RuntimeError(
            "slice_pdf: pypdf failed and poppler-utils are not on PATH"
        )
    return _slice_with_poppler(pdf_path, output_path, start_page=start_page, end_page=end)


def _slice_with_pypdf(
    pdf_path: Path,
    output_path: Path,
    start_page: int,
    end_page: int,
) -> Path:
    reader = PdfReader(str(pdf_path), strict=False)
    writer = PdfWriter()
    for page_idx in range(start_page, end_page):
        writer.add_page(reader.pages[page_idx])
    with output_path.open("wb") as fh:
        writer.write(fh)
    return output_path


def _slice_with_poppler(
    pdf_path: Path,
    output_path: Path,
    *,
    start_page: int,
    end_page: int,
) -> Path:
    """Use poppler-utils to extract a 1-based page range into one PDF."""
    if shutil.which("pdfseparate") is None or shutil.which("pdfunite") is None:
        raise RuntimeError("pdfseparate / pdfunite not found on PATH")
    # poppler is 1-based, half-closed: -f start -l end means pages start..end inclusive.
    first = start_page + 1
    last = end_page  # end_page is exclusive 0-based -> inclusive 1-based ==
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dir = Path(tmpdir)
        page_pattern = str(tmp_dir / "page_%d.pdf")
        sep = subprocess.run(
            [
                "pdfseparate",
                "-f",
                str(first),
                "-l",
                str(last),
                str(pdf_path),
                page_pattern,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if sep.returncode != 0:
            raise RuntimeError(
                f"pdfseparate failed (rc={sep.returncode}): {sep.stderr.strip() or sep.stdout.strip()}"
            )
        page_files = sorted(tmp_dir.glob("page_*.pdf"), key=_extract_page_index)
        if not page_files:
            raise RuntimeError("pdfseparate produced no output files")
        if len(page_files) == 1:
            shutil.copy(page_files[0], output_path)
            return output_path
        unite = subprocess.run(
            ["pdfunite", *(str(p) for p in page_files), str(output_path)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if unite.returncode != 0:
            raise RuntimeError(
                f"pdfunite failed (rc={unite.returncode}): {unite.stderr.strip() or unite.stdout.strip()}"
            )
    return output_path


def _extract_page_index(path: Path) -> int:
    """Sort key: pull the trailing integer out of "page_N.pdf"."""
    stem = path.stem  # "page_N"
    parts = stem.rsplit("_", 1)
    if len(parts) != 2:
        return 0
    try:
        return int(parts[1])
    except ValueError:
        return 0


def _poppler_available() -> bool:
    return all(shutil.which(b) is not None for b in ("pdfseparate", "pdfunite"))


# `os` is imported for callers that may want to set PDFINFO_BIN etc.; keep
# the module top-level deliberately small so audits stay easy.
__all__ = [
    "PdfChunk",
    "count_pages",
    "iter_chunk_files",
    "slice_pdf",
    "split_pdf",
]


# Silence unused-import warning while keeping `os` available for env vars.
_ = os
