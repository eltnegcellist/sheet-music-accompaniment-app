"""PDF utilities: page-count probing and chunk splitting for OMR."""

from .splitter import PdfChunk, count_pages, slice_pdf, split_pdf

__all__ = [
    "PdfChunk",
    "count_pages",
    "slice_pdf",
    "split_pdf",
]
