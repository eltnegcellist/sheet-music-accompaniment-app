"""Tests for solo_merger.merge_solo_into_full."""

from __future__ import annotations

from lxml import etree

from app.music.solo_merger import merge_solo_into_full


def _full_score() -> str:
    return (
        '<?xml version="1.0"?>'
        '<score-partwise version="3.1">'
        '<part-list>'
        '<score-part id="P1"><part-name>Violin</part-name></score-part>'
        '<score-part id="P2"><part-name>Piano</part-name></score-part>'
        '</part-list>'
        # Solo part — small/imprecise notes per the spec scenario.
        '<part id="P1">'
        '<measure number="1">'
        '<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration></note>'
        '</measure>'
        '<measure number="2">'
        '<note><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration></note>'
        '</measure>'
        '</part>'
        # Piano part with two staves to identify it as the accompaniment.
        '<part id="P2">'
        '<measure number="1">'
        '<attributes><staves>2</staves></attributes>'
        '<note><pitch><step>C</step><octave>3</octave></pitch><duration>4</duration></note>'
        '</measure>'
        '<measure number="2">'
        '<note><pitch><step>D</step><octave>3</octave></pitch><duration>4</duration></note>'
        '</measure>'
        '</part>'
        '</score-partwise>'
    )


def _solo_only_score() -> str:
    return (
        '<?xml version="1.0"?>'
        '<score-partwise version="3.1">'
        '<part-list>'
        '<score-part id="S1"><part-name>Violin</part-name></score-part>'
        '</part-list>'
        '<part id="S1">'
        '<measure number="1">'
        '<note><pitch><step>E</step><octave>5</octave></pitch><duration>8</duration></note>'
        '</measure>'
        '<measure number="2">'
        '<note><pitch><step>F</step><octave>5</octave></pitch><duration>8</duration></note>'
        '</measure>'
        '</part>'
        '</score-partwise>'
    )


def _measure_pitches(xml: str, part_id: str) -> dict[str, list[tuple[str, int]]]:
    root = etree.fromstring(xml.encode("utf-8"))
    out: dict[str, list[tuple[str, int]]] = {}
    part = root.find(f".//part[@id='{part_id}']")
    if part is None:
        return out
    for m in part.findall("measure"):
        notes = []
        for n in m.findall(".//note"):
            step = n.findtext("pitch/step") or "?"
            octave = int(n.findtext("pitch/octave") or 0)
            notes.append((step, octave))
        out[m.get("number") or ""] = notes
    return out


def test_solo_part_replaced_with_solo_only_notes() -> None:
    full = _full_score()
    solo = _solo_only_score()
    warnings: list[str] = []
    merged = merge_solo_into_full(
        full,
        solo,
        solo_part_id_in_full="P1",
        warnings=warnings,
    )
    pitches = _measure_pitches(merged, "P1")
    assert pitches == {"1": [("E", 5)], "2": [("F", 5)]}
    # Piano part untouched.
    piano = _measure_pitches(merged, "P2")
    assert piano["1"][0][0] == "C"
    assert any("2 小節を統合" in w for w in warnings)


def test_returns_input_when_solo_xml_empty() -> None:
    full = _full_score()
    assert merge_solo_into_full(full, "", solo_part_id_in_full="P1") == full
    assert merge_solo_into_full("", "<x/>", solo_part_id_in_full=None) == ""


def test_returns_input_when_solo_xml_unparseable() -> None:
    full = _full_score()
    assert merge_solo_into_full(
        full,
        "<<<not xml",
        solo_part_id_in_full="P1",
    ) == full


def test_part_id_auto_pick_when_hint_missing() -> None:
    """When solo_part_id_in_full is None, pick the part with most pitched notes
    that isn't a two-staff piano."""
    full = _full_score()
    solo = _solo_only_score()
    merged = merge_solo_into_full(full, solo, solo_part_id_in_full=None)
    pitches = _measure_pitches(merged, "P1")
    assert pitches["1"][0] == ("E", 5)


def test_no_matching_measures_records_warning() -> None:
    full = _full_score()
    # Solo XML has measure number 99 — no match in full score.
    solo = (
        '<?xml version="1.0"?>'
        '<score-partwise version="3.1">'
        '<part-list><score-part id="X"><part-name>X</part-name></score-part></part-list>'
        '<part id="X"><measure number="99"><note><rest/><duration>4</duration></note></measure></part>'
        '</score-partwise>'
    )
    warnings: list[str] = []
    merged = merge_solo_into_full(
        full, solo, solo_part_id_in_full="P1", warnings=warnings,
    )
    pitches = _measure_pitches(merged, "P1")
    # Original notes preserved, no replacement.
    assert pitches == {"1": [("C", 5)], "2": [("D", 5)]}
    assert any("一致する小節が見つからず" in w for w in warnings)
