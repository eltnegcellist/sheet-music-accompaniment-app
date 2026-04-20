"""Tesseract-based tempo extraction, used as a fallback when Audiveris fails
to surface a tempo marking in the MusicXML.

Audiveris often ignores italicized tempo words (Andantino, Allegro, …) that
sit above the first system, particularly when engraved in small italic type.
Running Tesseract over a cropped top strip of the first page recovers most of
those cases.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..music.parser import TempoInfo, match_tempo_word_bpm

logger = logging.getLogger(__name__)


def extract_tempo_from_pdf(pdf_path: Path) -> TempoInfo | None:
    """Run Tesseract on the top strip of page 1 and return a tempo if matched.

    Returns None when the OCR dependencies aren't installed, when the PDF can't
    be rasterized, or when no known tempo word is recognized. The caller should
    fall back to its existing default behaviour in those cases.
    """
    try:
        from pdf2image import convert_from_path  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as exc:
        logger.info("Tempo OCR unavailable (missing dep): %s", exc)
        return None

    try:
        # 300 dpi is non-negotiable here — italic tempo markings get crushed
        # at anything lower and Tesseract misreads the result entirely.
        pages = convert_from_path(
            str(pdf_path), dpi=300, first_page=1, last_page=1
        )
    except Exception as exc:  # pdf2image raises a variety of errors
        logger.warning("pdf2image failed: %s", exc)
        return None

    if not pages:
        return None

    image = pages[0]
    width, height = image.size
    # Tempo markings live above the top system; 15% of page height captures
    # the title block and the first line of engraving without bleeding into
    # the notes themselves (which confuse Tesseract).
    top_strip = image.crop((0, 0, width, int(height * 0.15)))

    try:
        raw_text = pytesseract.image_to_string(top_strip, lang="ita+eng")
    except Exception as exc:
        logger.warning("Tesseract failed: %s", exc)
        return None

    candidates = [line.strip() for line in raw_text.splitlines() if line.strip()]
    logger.info("Tesseract top-strip text: %r", candidates)
    if not candidates:
        return None

    for line in candidates:
        bpm = match_tempo_word_bpm(line)
        if bpm is not None:
            logger.info("OCR matched tempo word in %r -> %s BPM", line, bpm)
            return TempoInfo(bpm=bpm, source="ocr-word", candidates=candidates)

    return None
