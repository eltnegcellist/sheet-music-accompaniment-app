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


def _ocr_top_strip_lines(pdf_path: Path) -> list[str]:
    """OCR the top strip of page 1 and return non-empty text lines."""
    try:
        from pdf2image import convert_from_path  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as exc:
        logger.info("OCR unavailable (missing dep): %s", exc)
        return []

    try:
        # 300 dpi is non-negotiable here — italic tempo markings get crushed
        # at anything lower and Tesseract misreads the result entirely.
        pages = convert_from_path(
            str(pdf_path), dpi=300, first_page=1, last_page=1
        )
    except Exception as exc:  # pdf2image raises a variety of errors
        logger.warning("pdf2image failed: %s", exc)
        return []

    if not pages:
        return []

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
        return []

    candidates = [line.strip() for line in raw_text.splitlines() if line.strip()]
    logger.info("Tesseract top-strip text: %r", candidates)
    return candidates


def extract_tempo_from_pdf(pdf_path: Path) -> TempoInfo | None:
    """Run Tesseract on the top strip of page 1 and return a tempo if matched."""
    candidates = _ocr_top_strip_lines(pdf_path)
    if not candidates:
        return None

    for line in candidates:
        match = match_tempo_word_bpm(line)
        if match is not None:
            bpm, word = match
            logger.info("OCR matched tempo word in %r -> %s BPM (%s)", line, bpm, word)
            return TempoInfo(
                bpm=bpm,
                source="ocr-word",
                candidates=candidates,
                matched_word=word,
            )

    return None


def extract_title_from_pdf(pdf_path: Path) -> str | None:
    """Best-effort title OCR from the first page heading."""
    lines = _ocr_top_strip_lines(pdf_path)
    if not lines:
        return None

    for line in lines:
        # Skip pure tempo lines and tiny noise.
        if match_tempo_word_bpm(line) is not None:
            continue
        if len(line) < 3:
            continue
        lowered = line.lower()
        if lowered in {"solo", "piano", "violin", "cello", "viola", "flute"}:
            continue
        return line
    return None
