"""Tesseract-based tempo extraction, used as a fallback when Audiveris fails
to surface a tempo marking in the MusicXML.

Audiveris often ignores italicized tempo words (Andantino, Allegro, …) that
sit above the first system, particularly when engraved in small italic type.
Running Tesseract over a cropped top strip of the first page recovers most of
those cases.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ..music.parser import TempoInfo, match_tempo_word_bpm

logger = logging.getLogger(__name__)


@dataclass
class _OcrLine:
    text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int


def _load_top_strip_image(pdf_path: Path):
    try:
        from pdf2image import convert_from_path  # type: ignore[import-not-found]
    except ImportError as exc:
        logger.info("OCR unavailable (missing dep): %s", exc)
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
    return image.crop((0, 0, width, int(height * 0.15)))


def _ocr_top_strip_lines(pdf_path: Path) -> list[str]:
    """OCR the top strip of page 1 and return non-empty text lines."""
    top_strip = _load_top_strip_image(pdf_path)
    if top_strip is None:
        return []
    try:
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as exc:
        logger.info("OCR unavailable (missing dep): %s", exc)
        return []

    try:
        raw_text = pytesseract.image_to_string(top_strip, lang="ita+eng")
    except Exception as exc:
        logger.warning("Tesseract failed: %s", exc)
        return []

    candidates = [line.strip() for line in raw_text.splitlines() if line.strip()]
    logger.info("Tesseract top-strip text: %r", candidates)
    return candidates


def _ocr_top_strip_line_boxes(pdf_path: Path) -> tuple[list[_OcrLine], int]:
    top_strip = _load_top_strip_image(pdf_path)
    if top_strip is None:
        return [], 0
    try:
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as exc:
        logger.info("OCR unavailable (missing dep): %s", exc)
        return [], 0

    try:
        data = pytesseract.image_to_data(
            top_strip,
            lang="ita+eng",
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:
        logger.warning("Tesseract image_to_data failed: %s", exc)
        return [], 0

    lines: dict[tuple[int, int, int], list[tuple[str, float, int, int, int, int]]] = {}
    n = len(data.get("text", []))
    for i in range(n):
        raw = (data["text"][i] or "").strip()
        if not raw:
            continue
        conf_raw = (data["conf"][i] or "").strip()
        try:
            conf = float(conf_raw)
        except ValueError:
            conf = -1.0
        if conf < 0:
            continue
        key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        lines.setdefault(key, []).append(
            (
                raw,
                conf,
                int(data["left"][i]),
                int(data["top"][i]),
                int(data["width"][i]),
                int(data["height"][i]),
            )
        )

    out: list[_OcrLine] = []
    for words in lines.values():
        text = " ".join(w[0] for w in words).strip()
        if not text:
            continue
        conf = sum(w[1] for w in words) / len(words)
        x = min(w[2] for w in words)
        y = min(w[3] for w in words)
        x2 = max(w[2] + w[4] for w in words)
        y2 = max(w[3] + w[5] for w in words)
        out.append(
            _OcrLine(
                text=text,
                confidence=conf,
                x=x,
                y=y,
                width=max(1, x2 - x),
                height=max(1, y2 - y),
            )
        )
    return out, top_strip.size[0]


def _pick_title_from_ocr_lines(lines: list[_OcrLine], image_width: int) -> str | None:
    best: tuple[float, str] | None = None
    deny_words = {"solo", "piano", "violin", "cello", "viola", "flute"}
    for line in lines:
        text = line.text.strip()
        if len(text) < 3:
            continue
        if match_tempo_word_bpm(text) is not None:
            continue
        lowered = text.lower()
        if lowered in deny_words:
            continue
        if re.search(r"\b(composer|composed|arranged|arr\.)\b", lowered):
            continue
        if re.fullmatch(r"[0-9IVXLCM.\- ]+", text):
            continue

        width_ratio = line.width / max(1, image_width)
        center = line.x + line.width / 2
        center_penalty = abs(center - image_width / 2) / max(1, image_width / 2)
        size_score = line.height * 0.6 + line.width * 0.02
        score = (
            line.confidence
            + width_ratio * 40
            + size_score
            - center_penalty * 20
            - (line.y / 10)
        )
        if best is None or score > best[0]:
            best = (score, text)
    return best[1] if best else None


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
    boxed_lines, width = _ocr_top_strip_line_boxes(pdf_path)
    picked = _pick_title_from_ocr_lines(boxed_lines, width)
    if picked:
        logger.info("Picked OCR title line: %r", picked)
        return picked
    # Fallback to plain line OCR if box data is unavailable.
    plain = _ocr_top_strip_lines(pdf_path)
    for line in plain:
        if len(line.strip()) >= 3 and match_tempo_word_bpm(line) is None:
            return line.strip()
    return None
