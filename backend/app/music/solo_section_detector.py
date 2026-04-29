"""Detect a solo-only section by inspecting OMR-produced MusicXML.

After the first Audiveris pass we have a MusicXML score that exposes per-part,
per-measure note information. A "solo-only" section — typically printed at the
end (or beginning) of an IMSLP edition with the solo voice at full size —
shows up as a long contiguous run of measures where the accompaniment part
has no pitched notes (only rests, or no events at all).

Detecting this from the MusicXML is far more reliable than pixel- or
staff-count-based heuristics because the signal is structural: a piano
accompaniment that prints "tacet" for an entire section is rare in this
repertoire, while a printed-as-solo-only section is common.

The detector deliberately only flags a solo section at the **start** or **end**
of the score. A long tacet in the middle is far more likely to be a
genuine compositional pause than a sectioning of the engraving, so we leave
that case alone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Protocol

from lxml import etree

logger = logging.getLogger(__name__)

DEFAULT_MIN_MEASURES = 8
DEFAULT_MIN_RATIO = 0.20


@dataclass
class SoloMeasureRange:
    """A measure range that looks like solo-only content.

    `start_measure` and `end_measure` are 1-based MusicXML measure numbers,
    inclusive on both ends. `solo_at_front` is True when the range starts at
    the score's first measure; otherwise it ends at the last measure.
    """

    start_measure: int
    end_measure: int
    solo_at_front: bool
    accompaniment_empty_count: int


class _MeasureLayoutLike(Protocol):
    index: int
    page: int


def find_solo_only_measure_range(
    music_xml: str,
    accompaniment_part_id: str | None,
    *,
    min_measures: int = DEFAULT_MIN_MEASURES,
    min_ratio: float = DEFAULT_MIN_RATIO,
) -> SoloMeasureRange | None:
    """Return the longest "accompaniment-silent" measure range at start/end.

    The range must be at least `min_measures` measures long *and* cover at
    least `min_ratio` of the total score, whichever is larger. We return the
    longer side (front or back) so a piece with both a solo intro and an
    accompaniment middle still gets the intro flagged.
    """
    if not accompaniment_part_id:
        return None
    try:
        root = etree.fromstring(music_xml.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        logger.warning("solo_section_detector: parse failed: %s", exc)
        return None
    acc_part = root.find(f".//part[@id='{accompaniment_part_id}']")
    if acc_part is None:
        return None

    measures: list[tuple[int, bool]] = []  # (measure_number, is_empty)
    for m in acc_part.findall("measure"):
        num = _measure_number(m)
        if num is None:
            continue
        measures.append((num, _is_measure_empty(m)))

    if not measures:
        return None
    n = len(measures)
    threshold = max(min_measures, int(n * min_ratio))

    front_count = 0
    for _num, empty in measures:
        if empty:
            front_count += 1
        else:
            break

    back_count = 0
    for _num, empty in reversed(measures):
        if empty:
            back_count += 1
        else:
            break

    # When both ends qualify, prefer the longer side. Ties go to the front
    # since front-positioned solo sections are slightly more common in this
    # repertoire (a soloist's "movement-1" engraving).
    if front_count >= threshold and front_count >= back_count:
        end_idx = front_count - 1
        return SoloMeasureRange(
            start_measure=measures[0][0],
            end_measure=measures[end_idx][0],
            solo_at_front=True,
            accompaniment_empty_count=front_count,
        )
    if back_count >= threshold:
        start_idx = n - back_count
        return SoloMeasureRange(
            start_measure=measures[start_idx][0],
            end_measure=measures[-1][0],
            solo_at_front=False,
            accompaniment_empty_count=back_count,
        )
    return None


def measure_range_to_page_range(
    measure_layouts: Iterable[_MeasureLayoutLike],
    start_measure: int,
    end_measure: int,
) -> tuple[int, int] | None:
    """Map a 1-based inclusive measure range to a 0-based half-open page range.

    Returns None when no `MeasureLayout` entry falls within the requested
    range — that happens when Audiveris failed to emit layout data for the
    relevant pages.
    """
    pages: set[int] = set()
    for m in measure_layouts:
        if start_measure <= m.index <= end_measure:
            pages.add(m.page)
    if not pages:
        return None
    return min(pages), max(pages) + 1


def _is_measure_empty(measure: etree._Element) -> bool:
    """True when a measure contains no pitched notes.

    Rest-only measures and empty measures (no <note> children) both count as
    empty. We deliberately ignore <chord> grouping here because a chord
    without pitches isn't a thing — any pitched note disqualifies the
    measure, however many there are.
    """
    for note in measure.findall(".//note"):
        if note.find("rest") is not None:
            continue
        if note.find("pitch") is not None:
            return False
    return True


def _measure_number(measure: etree._Element) -> int | None:
    raw = measure.get("number")
    if raw is None:
        return None
    digits = raw.lstrip("X")
    try:
        n = int(digits)
    except ValueError:
        return None
    if n <= 0:
        return None
    return n
