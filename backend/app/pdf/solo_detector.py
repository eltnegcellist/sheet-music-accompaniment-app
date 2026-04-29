"""Detect solo-only sections inside a combined PDF.

The user often uploads a single PDF that bundles the full score (solo +
piano on two-staff grand-staff systems) and a solo-only score (one staff
per system). Audiveris recognises the solo line far better on the solo-only
section because the noteheads are printed at full size, so we want to feed
each section to OMR independently and merge the results.

Approach
--------
A page that prints solo + piano accompaniment carries roughly **three
staves per system**, while a solo-only page carries **one staff per system**
— a 3× difference in horizontal staff-line count. Earlier revisions used
overall ink density as a proxy, but that signal is noisy: solo pages with
many notes can rival the ink count of a sparse piano page, and the
heuristic also missed the "solo first, full score second" layout entirely.

We now count staff lines directly:

1. Render each page to a low-res grayscale thumbnail.
2. Per row, compute the fraction of dark pixels.
3. Rows whose width-fraction exceeds ``line_width_ratio`` (≈ 50%) are staff
   lines; we count one rising edge per line so a thick line still scores
   one count.
4. Search for the page index where the rolling staff-line count drops or
   rises by more than ``min_count_ratio`` of the larger half. The lower
   side is treated as solo-only — this naturally handles both
   "solo-then-full" and "full-then-solo" layouts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SoloSplitResult:
    """Result of the solo-section detector.

    The PDF is divided into two contiguous page ranges. One holds the full
    score (with accompaniment), the other holds the solo-only section. Both
    ranges are 0-based, half-open `[start, end)`.
    """

    full_start_page: int
    full_end_page: int
    solo_start_page: int
    solo_end_page: int
    solo_at_front: bool = False
    staff_counts: list[int] = field(default_factory=list)


def detect_solo_split(
    pdf_path: Path,
    *,
    dpi: int = 75,
    min_pages: int = 4,
    min_count_ratio: float = 0.55,
) -> SoloSplitResult | None:
    """Look for a section boundary between full-score and solo-only pages.

    `min_count_ratio` is the upper bound on (fewer-staff side) /
    (more-staff side). A clean solo/full split typically clocks in at
    0.30–0.40 (1 staff vs 3 staves per system); we leave headroom for noise
    by accepting up to 0.55. Returns None when:

    - pdf rendering fails (e.g. poppler missing in the environment),
    - the document is shorter than `min_pages`, or
    - no candidate split satisfies `min_count_ratio` (i.e. every page has
      a similar staff-line count, so the document is uniform).
    """
    counts = _staff_line_counts_per_page(pdf_path, dpi=dpi)
    if counts is None:
        return None
    n = len(counts)
    if n < min_pages:
        return None

    split = pick_split_point(counts, min_count_ratio=min_count_ratio)
    if split is None:
        return None
    split_index, solo_at_front = split

    if solo_at_front:
        return SoloSplitResult(
            full_start_page=split_index,
            full_end_page=n,
            solo_start_page=0,
            solo_end_page=split_index,
            solo_at_front=True,
            staff_counts=counts,
        )
    return SoloSplitResult(
        full_start_page=0,
        full_end_page=split_index,
        solo_start_page=split_index,
        solo_end_page=n,
        solo_at_front=False,
        staff_counts=counts,
    )


def pick_split_point(
    counts: list[int],
    *,
    min_count_ratio: float = 0.55,
) -> tuple[int, bool] | None:
    """Find the page boundary that maximises the staff-count contrast.

    Returns `(split_index, solo_at_front)` where `split_index` is the
    0-based first page of the *second* segment, or None when no split
    cleanly meets the contrast threshold.

    `solo_at_front` is True when the first segment has fewer staves on
    average than the second — i.e. solo pages come first.
    """
    n = len(counts)
    if n < 2:
        return None

    best_split: int | None = None
    best_solo_at_front = False
    best_contrast = 0.0

    for k in range(1, n):
        before = counts[:k]
        after = counts[k:]
        if not before or not after:
            continue
        avg_before = sum(before) / len(before)
        avg_after = sum(after) / len(after)
        if avg_before <= 0 or avg_after <= 0:
            continue
        smaller = min(avg_before, avg_after)
        larger = max(avg_before, avg_after)
        ratio = smaller / larger
        if ratio > min_count_ratio:
            continue
        # Prefer the split with the largest absolute staff-count gap so a
        # mostly-uniform document with one anomalous page doesn't trigger.
        contrast = larger - smaller
        if contrast > best_contrast:
            best_contrast = contrast
            best_split = k
            best_solo_at_front = avg_before < avg_after

    if best_split is None:
        return None
    logger.info(
        "Solo split candidate: page=%d solo_at_front=%s contrast=%.2f counts=%s",
        best_split,
        best_solo_at_front,
        best_contrast,
        counts,
    )
    return best_split, best_solo_at_front


def count_staff_lines(image, *, line_width_ratio: float = 0.5) -> int:
    """Count horizontal staff lines (or other near-full-width dark rows).

    A staff line is any row whose dark-pixel fraction exceeds
    `line_width_ratio` of the page width. Adjacent dark rows are collapsed
    into a single count so a 2–3 pixel thick line still scores once. We
    intentionally count *any* full-width dark row (not just the 5-line
    grouping) because the ratio between solo-only (1 staff per system) and
    full-score (3 staves per system) holds either way and avoids tunable
    grouping heuristics.
    """
    try:
        import numpy as np
    except ImportError:
        # Fall back to a slow pure-Python loop. Solo detection is
        # best-effort, not a correctness requirement.
        return _count_staff_lines_python(image, line_width_ratio)

    if image.mode != "L":
        image = image.convert("L")
    arr = np.asarray(image)
    if arr.size == 0:
        return 0
    h, w = arr.shape
    if w == 0:
        return 0
    ink = arr < 128
    row_dark_ratio = ink.sum(axis=1) / w
    is_line = row_dark_ratio > line_width_ratio
    if not is_line.any():
        return 0
    # Count rising edges = number of distinct horizontal bands.
    edges = np.diff(is_line.astype(np.int8))
    rising = int((edges == 1).sum())
    # Include a leading edge if the very first row is already a line.
    if bool(is_line[0]):
        rising += 1
    return rising


def _count_staff_lines_python(image, line_width_ratio: float) -> int:
    if image.mode != "L":
        image = image.convert("L")
    w, h = image.size
    if w == 0:
        return 0
    threshold = int(w * line_width_ratio)
    pixels = list(image.getdata())
    count = 0
    prev_is_line = False
    for row in range(h):
        start = row * w
        ink = sum(1 for v in pixels[start : start + w] if v < 128)
        is_line = ink > threshold
        if is_line and not prev_is_line:
            count += 1
        prev_is_line = is_line
    return count


def _staff_line_counts_per_page(
    pdf_path: Path, *, dpi: int
) -> list[int] | None:
    try:
        from pdf2image import convert_from_path
    except ImportError:
        logger.info("pdf2image not available; skipping solo detection")
        return None
    try:
        images = convert_from_path(str(pdf_path), dpi=dpi, grayscale=True)
    except Exception as exc:  # pdf2image surfaces a slew of OSErrors
        logger.warning("pdf2image rendering failed: %s", exc)
        return None
    return [count_staff_lines(img) for img in images]
