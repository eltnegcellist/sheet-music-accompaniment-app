"""Concatenate MusicXML documents produced by chunked OMR runs.

When a long PDF is split into several chunks for Audiveris, each chunk
emits its own MusicXML file with measure numbering that resets to 1.
This module stitches those MusicXMLs back together so the player sees
one continuous score.

Strategy
--------
1. Use the first chunk's MusicXML as the scaffold (preserves work-title,
   identification, defaults, part-list). The first chunk's notes go in
   unchanged.
2. For each subsequent chunk, walk its `<part>` elements in document order
   and append every `<measure>` child to the corresponding part in the
   scaffold, renumbering measure@number sequentially across the whole score.
3. Any chunks whose part count differs from the scaffold are still
   appended best-effort by index (Audiveris occasionally drops a part on
   noisy pages); the warnings list records the mismatch.

We do **not** try to dedupe `<sound tempo>` / `<direction>` directives
across chunk boundaries — it's safer to keep them and let the player honor
whichever fires first per measure.
"""

from __future__ import annotations

import logging
from copy import deepcopy

from lxml import etree

logger = logging.getLogger(__name__)


def concat_musicxml(
    chunks_xml: list[str],
    *,
    warnings: list[str] | None = None,
) -> str:
    """Concatenate chunk MusicXMLs into a single score.

    Returns the merged MusicXML text. If only one chunk is supplied (or
    every other chunk is empty) the input is returned unchanged.
    """
    valid = [x for x in chunks_xml if x and x.strip()]
    if not valid:
        return ""
    if len(valid) == 1:
        return valid[0]

    base_root = _parse(valid[0])
    if base_root is None:
        # Find the first chunk that parses; subsequent chunks may still
        # contribute their measures if the first happens to be malformed.
        for candidate in valid[1:]:
            root = _parse(candidate)
            if root is not None:
                base_root = root
                break
    if base_root is None:
        return valid[0]

    # Establish the next measure number to assign. Audiveris numbers most
    # measures from 1, but we honor whatever the scaffold ended on.
    next_measure_number = _max_measure_number(base_root) + 1
    base_parts = base_root.findall(".//part")

    for chunk_xml in valid[1:]:
        root = _parse(chunk_xml)
        if root is None:
            if warnings is not None:
                warnings.append("分割解析の一部チャンクが MusicXML として解釈できず、無視しました。")
            continue
        chunk_parts = root.findall(".//part")
        if not chunk_parts:
            continue
        if len(chunk_parts) != len(base_parts) and warnings is not None:
            warnings.append(
                f"分割チャンクのパート数 ({len(chunk_parts)}) が"
                f" 基準 ({len(base_parts)}) と異なります。インデックス順に結合します。"
            )

        chunk_max = _max_measure_number(root)
        # Determine the renumber offset so that the concatenated score has a
        # single monotonically-increasing measure sequence. We use the
        # scaffold's last + 1 as the new starting point and shift every
        # measure of every part in this chunk by the same delta — measure
        # numbers must stay aligned across parts.
        chunk_min = _min_measure_number(root)
        delta = next_measure_number - max(1, chunk_min)
        for idx, chunk_part in enumerate(chunk_parts):
            target = base_parts[idx] if idx < len(base_parts) else base_parts[-1]
            for measure in chunk_part.findall("measure"):
                cloned = deepcopy(measure)
                _shift_measure_number(cloned, delta)
                target.append(cloned)
        next_measure_number = chunk_max + delta + 1

    return etree.tostring(
        base_root,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")


def _parse(xml: str) -> etree._Element | None:
    try:
        return etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        logger.warning("Could not parse chunk MusicXML: %s", exc)
        return None


def _max_measure_number(root: etree._Element) -> int:
    biggest = 0
    for m in root.iter("measure"):
        try:
            num = int((m.get("number") or "0").lstrip("X"))
        except ValueError:
            continue
        if num > biggest:
            biggest = num
    return biggest


def _min_measure_number(root: etree._Element) -> int:
    smallest: int | None = None
    for m in root.iter("measure"):
        try:
            num = int((m.get("number") or "0").lstrip("X"))
        except ValueError:
            continue
        if num <= 0:
            continue
        if smallest is None or num < smallest:
            smallest = num
    return smallest or 1


def _shift_measure_number(measure: etree._Element, delta: int) -> None:
    if delta == 0:
        return
    raw = measure.get("number") or ""
    # Some scores number pickup measures "X1" or similar — preserve the
    # prefix to avoid breaking implicit-measure semantics.
    prefix = ""
    digits = raw
    while digits and not digits[0].isdigit() and digits[0] != "-":
        prefix += digits[0]
        digits = digits[1:]
    try:
        n = int(digits) if digits else 0
    except ValueError:
        return
    if n <= 0:
        return
    measure.set("number", f"{prefix}{n + delta}")
