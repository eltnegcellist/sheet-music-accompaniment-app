"""Identify which `<score-part>` is the piano accompaniment.

For an instrumental-solo + piano arrangement, the piano part is almost always
the part with two staves. We use that as the primary heuristic and fall back
to a name match ("Piano" / "Pianoforte" / "Klavier" / "ピアノ") then to the
last part in the score.
"""

from __future__ import annotations

import re

from lxml import etree

_PIANO_NAME_RE = re.compile(
    r"piano|pianoforte|klavier|ピアノ|pf\.?", re.IGNORECASE
)


def find_accompaniment_part(music_xml: str) -> str | None:
    root = etree.fromstring(music_xml.encode("utf-8"))

    parts = root.findall(".//score-part")
    if not parts:
        return None

    # 1) Two-staff parts (almost always piano in this repertoire).
    for part_el in parts:
        part_id = part_el.get("id")
        if part_id and _part_has_two_staves(root, part_id):
            return part_id

    # 2) Name-based fallback.
    for part_el in parts:
        for tag in ("part-name", "part-abbreviation", "instrument-name"):
            name_el = part_el.find(f".//{tag}")
            if name_el is not None and name_el.text and _PIANO_NAME_RE.search(
                name_el.text
            ):
                return part_el.get("id")

    # 3) Last part — in solo+accompaniment scores the accompaniment is
    # conventionally listed below the soloist.
    return parts[-1].get("id")


def find_solo_part(music_xml: str, accompaniment_part_id: str | None) -> str | None:
    """Pick the most likely solo part among non-accompaniment parts.

    Historically we picked the first non-piano part, but OMR often emits
    auxiliary/garbage parts ahead of the real solo line. We now rank by note
    density (pitched notes with duration) and prefer single-staff parts.
    """
    if accompaniment_part_id is None:
        return None
    root = etree.fromstring(music_xml.encode("utf-8"))
    parts = root.findall(".//score-part")
    candidates: list[tuple[int, int, int, str]] = []
    order = 0
    for part_el in parts:
        part_id = part_el.get("id")
        if not part_id or part_id == accompaniment_part_id:
            order += 1
            continue
        pitched_notes = _part_pitched_note_count(root, part_id)
        single_staff_bonus = 1 if not _part_has_two_staves(root, part_id) else 0
        # Sort key priority: more notes, single-staff preference, earlier order.
        candidates.append((-pitched_notes, -single_staff_bonus, order, part_id))
        order += 1
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def _part_has_two_staves(root: etree._Element, part_id: str) -> bool:
    part = root.find(f".//part[@id='{part_id}']")
    if part is None:
        return False
    staves_el = part.find(".//attributes/staves")
    if staves_el is None or not staves_el.text:
        return False
    try:
        return int(staves_el.text) >= 2
    except ValueError:
        return False


def _part_pitched_note_count(root: etree._Element, part_id: str) -> int:
    part = root.find(f".//part[@id='{part_id}']")
    if part is None:
        return 0
    count = 0
    for note in part.findall(".//note"):
        if note.find("rest") is not None:
            continue
        pitch = note.find("pitch")
        duration = note.find("duration")
        if pitch is None or duration is None or not (duration.text or "").strip():
            continue
        count += 1
    return count
