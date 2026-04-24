"""Tests for validate_musicxml_shape — the Phase 2-4 broken-XML detector."""

from app.pipeline.validators import validate_musicxml_shape


GOOD = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
    </measure>
    <measure number="2">
      <note><rest/><duration>4</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""


def test_clean_xml_is_not_broken():
    r = validate_musicxml_shape(GOOD)
    assert r.is_broken is False
    assert r.measure_count == 2
    # MusicXML wraps rests in <note> too — we count both pitched and rest notes.
    assert r.note_count == 3
    assert r.part_count == 1


def test_empty_input_flagged():
    r = validate_musicxml_shape("")
    assert r.is_broken
    assert r.issues[0].code == "empty_input"


def test_malformed_xml_flagged():
    r = validate_musicxml_shape("<not closed")
    assert r.is_broken
    assert r.issues[0].code == "xml_parse_error"


def test_wrong_root_flagged():
    r = validate_musicxml_shape("<note/>")
    assert r.is_broken
    assert r.issues[0].code == "bad_root"


def test_zero_measures_flagged():
    xml = (
        "<score-partwise><part-list><score-part id='P1'/></part-list>"
        "<part id='P1'></part></score-partwise>"
    )
    r = validate_musicxml_shape(xml)
    codes = {i.code for i in r.issues}
    assert "zero_measures" in codes


def test_zero_notes_flagged():
    xml = (
        "<score-partwise><part-list><score-part id='P1'/></part-list>"
        "<part id='P1'><measure number='1'/></part></score-partwise>"
    )
    r = validate_musicxml_shape(xml)
    codes = {i.code for i in r.issues}
    assert "zero_notes" in codes


def test_all_parts_empty_flagged():
    xml = (
        "<score-partwise>"
        "<part-list><score-part id='P1'/><score-part id='P2'/></part-list>"
        "<part id='P1'><measure number='1'/></part>"
        "<part id='P2'><measure number='1'/></part>"
        "</score-partwise>"
    )
    r = validate_musicxml_shape(xml)
    codes = {i.code for i in r.issues}
    assert "all_parts_empty" in codes
    assert r.empty_parts == 2


def test_absurd_density_flagged():
    notes = "".join(
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>"
        for _ in range(60)
    )
    xml = (
        "<score-partwise><part-list><score-part id='P1'/></part-list>"
        f"<part id='P1'><measure number='1'>{notes}</measure></part></score-partwise>"
    )
    r = validate_musicxml_shape(xml, max_avg_notes_per_measure=50)
    codes = {i.code for i in r.issues}
    assert "absurd_density" in codes
    assert r.avg_notes_per_measure == 60


def test_no_parts_flagged():
    xml = "<score-partwise><part-list/></score-partwise>"
    r = validate_musicxml_shape(xml)
    codes = {i.code for i in r.issues}
    assert "no_parts" in codes
