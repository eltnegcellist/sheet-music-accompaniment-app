"""Replace the solo part in a full score with notes from a solo-only score.

When a player uploads two PDFs — the full score (solo + piano on two staves)
and the solo-only score — Audiveris recognises the solo line far more
accurately on the solo-only PDF, where the notes are printed at full size.
This module takes the MusicXML from each pass and overlays the solo-only
notes on top of the matching `<part>` in the merged score.

Strategy
--------
* Pick the source `<part>` from the solo-only MusicXML — usually the only
  part, but we still defer to the highest-density part if there are several.
* For every measure in the target solo part of the full score, swap its
  contents (notes / rests / direction / barline elements) with the matching
  measure from the solo-only score, keyed on the `number` attribute.
* Measures present only in one side are kept as-is. The merged result is
  returned as text; the caller is responsible for picking it up via the
  existing scoring pipeline.

We deliberately do not attempt to fix part-id / staff conflicts here;
mismatches are surfaced as warnings so the operator can investigate.
"""

from __future__ import annotations

import logging
from copy import deepcopy

from lxml import etree

logger = logging.getLogger(__name__)


def merge_solo_into_full(
    full_xml: str,
    solo_only_xml: str,
    *,
    solo_part_id_in_full: str | None,
    warnings: list[str] | None = None,
) -> str:
    """Return `full_xml` with its solo part overwritten from `solo_only_xml`.

    `solo_part_id_in_full` is the part-id within the full score that should
    receive the solo-only notes. When None we pick the part with the highest
    pitched-note count that isn't piano-shaped (two-staff).
    """
    if not full_xml or not solo_only_xml:
        return full_xml

    full_root = _parse(full_xml)
    solo_root = _parse(solo_only_xml)
    if full_root is None or solo_root is None:
        return full_xml

    target_part = _pick_target_part(full_root, solo_part_id_in_full)
    if target_part is None:
        if warnings is not None:
            warnings.append("ソロパートを特定できなかったため、ソロ専用譜の統合をスキップしました。")
        return full_xml

    source_part = _pick_solo_source_part(solo_root)
    if source_part is None:
        if warnings is not None:
            warnings.append("ソロ専用譜から有効な<part>が見つかりませんでした。")
        return full_xml

    source_by_number: dict[str, etree._Element] = {}
    for measure in source_part.findall("measure"):
        num = measure.get("number")
        if num:
            source_by_number.setdefault(num, measure)

    replaced = 0
    for measure in list(target_part.findall("measure")):
        num = measure.get("number")
        if num is None:
            continue
        replacement = source_by_number.get(num)
        if replacement is None:
            continue
        new_measure = deepcopy(replacement)
        # Preserve the target's `number` and `width` (Audiveris layout) so the
        # PDF overlay still lines up after the swap.
        new_measure.set("number", num)
        original_width = measure.get("width")
        if original_width:
            new_measure.set("width", original_width)
        target_part.replace(measure, new_measure)
        replaced += 1

    if warnings is not None:
        if replaced == 0:
            warnings.append("ソロ専用譜と本譜面で一致する小節が見つからず、統合は適用されませんでした。")
        else:
            warnings.append(f"ソロ専用譜から {replaced} 小節を統合しました。")

    return etree.tostring(
        full_root,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")


def _parse(xml: str) -> etree._Element | None:
    try:
        return etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        logger.warning("solo_merger could not parse XML: %s", exc)
        return None


def _pick_target_part(
    root: etree._Element,
    explicit_id: str | None,
) -> etree._Element | None:
    parts = root.findall(".//part")
    if not parts:
        return None
    if explicit_id:
        for part in parts:
            if part.get("id") == explicit_id:
                return part
    # Best-effort fallback: prefer the part with the most pitched notes that
    # is not the two-staff piano (`<staves>2</staves>`).
    best: tuple[int, etree._Element] | None = None
    for part in parts:
        if _has_two_staves(part):
            continue
        count = _pitched_note_count(part)
        if best is None or count > best[0]:
            best = (count, part)
    if best is None:
        return parts[0]
    return best[1]


def _pick_solo_source_part(root: etree._Element) -> etree._Element | None:
    parts = root.findall(".//part")
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    # Pick the part with the most pitched notes — Audiveris occasionally
    # emits an empty 'lyric'-only auxiliary part on solo scores.
    best: tuple[int, etree._Element] | None = None
    for part in parts:
        count = _pitched_note_count(part)
        if best is None or count > best[0]:
            best = (count, part)
    return best[1] if best else parts[0]


def _has_two_staves(part: etree._Element) -> bool:
    staves_el = part.find(".//attributes/staves")
    if staves_el is None or not staves_el.text:
        return False
    try:
        return int(staves_el.text) >= 2
    except ValueError:
        return False


def _pitched_note_count(part: etree._Element) -> int:
    count = 0
    for note in part.findall(".//note"):
        if note.find("rest") is not None:
            continue
        if note.find("pitch") is None:
            continue
        count += 1
    return count
