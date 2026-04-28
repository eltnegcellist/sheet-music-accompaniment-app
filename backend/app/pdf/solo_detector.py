"""Detect a solo-only section inside a combined PDF.

When the user uploads a single PDF that contains both the full score and a
solo-only score (a common IMSLP layout), we'd like to feed each section to
Audiveris separately so the solo recognition benefits from the larger note
heads on the solo-only pages. The detector below uses a coarse, fast
heuristic — pixel density per page — to find a likely cut point.

Heuristic
---------
* Render each page to a low-resolution greyscale thumbnail (default 75 DPI,
  small enough to keep this <100ms even on a 60-page sonata).
* Compute the fraction of dark pixels per page.
* The full score (two-staff piano + solo) has roughly 1.5–2x the ink
  density of a solo-only page. If the second half of the document is
  significantly lighter than the first half *and* there's a clear step at
  the boundary, treat the lighter section as solo-only.

This is intentionally conservative: false positives would split a normal
score in half and corrupt the solo merge. When the heuristic is unsure we
return ``None`` and let the caller fall through to the single-PDF flow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass
class SoloSplitResult:
    """Outcome of the heuristic.

    `solo_start_page` is the 0-based first page of the solo-only section.
    The full-score section is `pages[:solo_start_page]`.
    """

    solo_start_page: int
    page_densities: list[float]


def detect_solo_split(
    pdf_path: Path,
    *,
    dpi: int = 75,
    min_pages: int = 4,
    density_drop_ratio: float = 0.65,
) -> SoloSplitResult | None:
    """Return a split point if the second half looks solo-only.

    `density_drop_ratio` is the upper bound on (solo-section density) /
    (full-score density). Solo-only pages typically clock in around 0.5–0.6
    of the full-score density on this repertoire; setting the threshold at
    0.65 leaves room for noise without flagging normal scores.

    Returns None on:
    - pdf rendering failures (e.g. missing poppler in the environment)
    - documents shorter than `min_pages`
    - density profiles that don't show a clean step between halves
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        logger.info("pdf2image not available; skipping solo detection")
        return None

    densities = _page_densities(pdf_path, dpi=dpi)
    if densities is None:
        return None
    n = len(densities)
    if n < min_pages:
        return None

    # Walk possible split points from the middle outward; the cleanest cut is
    # usually somewhere between 40% and 80% of the document. We score each
    # candidate by `mean(after) / mean(before)` and pick the lowest.
    best_split = None
    best_ratio = 1.0
    lo = max(1, int(n * 0.4))
    hi = max(lo + 1, int(n * 0.85))
    for k in range(lo, hi + 1):
        before = densities[:k]
        after = densities[k:]
        if not before or not after:
            continue
        avg_before = sum(before) / len(before)
        avg_after = sum(after) / len(after)
        if avg_before <= 0:
            continue
        ratio = avg_after / avg_before
        if ratio < best_ratio:
            best_ratio = ratio
            best_split = k

    if best_split is None or best_ratio > density_drop_ratio:
        logger.info(
            "Solo split not detected (best ratio %.2f, threshold %.2f)",
            best_ratio,
            density_drop_ratio,
        )
        return None

    logger.info(
        "Solo split candidate at page %d (ratio %.2f)", best_split, best_ratio
    )
    return SoloSplitResult(
        solo_start_page=best_split,
        page_densities=densities,
    )


def _page_densities(pdf_path: Path, *, dpi: int) -> list[float] | None:
    try:
        from pdf2image import convert_from_path
    except ImportError:
        return None
    try:
        images = convert_from_path(str(pdf_path), dpi=dpi, grayscale=True)
    except Exception as exc:  # pdf2image surfaces a slew of OSErrors
        logger.warning("pdf2image rendering failed: %s", exc)
        return None
    return [_dark_pixel_fraction(img) for img in images]


def _dark_pixel_fraction(image) -> float:
    """Return the fraction of dark pixels (intensity < 128) in `image`."""
    # PIL's getextrema/histogram are pure-C and avoid forcing numpy.
    if image.mode != "L":
        image = image.convert("L")
    histogram: Iterable[int] = image.histogram()
    total = 0
    dark = 0
    for level, count in enumerate(histogram):
        total += count
        if level < 128:
            dark += count
    if total == 0:
        return 0.0
    return dark / total
