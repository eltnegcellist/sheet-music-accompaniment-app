"""PDF utilities: page-count probing, chunk splitting, solo detection."""

from .solo_detector import SoloSplitResult, detect_solo_split
from .splitter import PdfChunk, count_pages, slice_pdf, split_pdf

__all__ = [
    "PdfChunk",
    "SoloSplitResult",
    "count_pages",
    "detect_solo_split",
    "slice_pdf",
    "split_pdf",
]
