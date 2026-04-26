"""Tests for fill_missing_measures (Phase 3-8 gap recovery)."""

from app.pipeline.postprocess.edits import EditLog
from app.pipeline.postprocess.missing_measures import fill_missing_measures
from app.pipeline.stages.postprocess import parse_musicxml


_GAP_AT_3 = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="2">
<note><pitch><step>D</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="4">
<note><pitch><step>E</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="5">
<note><pitch><step>F</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""


_TWO_GAPS = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="3">
<note><pitch><step>D</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="6">
<note><pitch><step>E</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""


_NO_GAPS = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="2">
<note><pitch><step>D</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""


def _measure_numbers(score):
    out = []
    for p in score.parts:
        out.extend(int(m.number) for m in p.getElementsByClass("Measure"))
    return out


# --- happy path ---------------------------------------------------------


def test_single_gap_is_filled():
    score = parse_musicxml(_GAP_AT_3)
    log = EditLog()
    report = fill_missing_measures(score, log=log)
    assert report.gaps_found == 1
    assert report.measures_inserted == 1
    # The placeholder must show up in document order.
    assert _measure_numbers(score) == [1, 2, 3, 4, 5]
    # Edit log carries one measure_insert event.
    assert log.by_op() == {"measure_insert": 1}


def test_multi_measure_gap_fills_all():
    """Gap of 2 (between m3 and m6) → insert m4 and m5."""
    score = parse_musicxml(_TWO_GAPS)
    log = EditLog()
    report = fill_missing_measures(score, log=log)
    # gaps_found counts gap-spans, measures_inserted counts placeholders.
    assert report.gaps_found == 2  # gap between 1↔3 (1 missing) + 3↔6 (2 missing)
    assert report.measures_inserted == 1 + 2
    assert _measure_numbers(score) == [1, 2, 3, 4, 5, 6]


def test_no_gaps_is_a_noop():
    score = parse_musicxml(_NO_GAPS)
    log = EditLog()
    report = fill_missing_measures(score, log=log)
    assert report.gaps_found == 0
    assert report.measures_inserted == 0
    assert len(log) == 0


# --- safety cap --------------------------------------------------------


def test_oversized_gap_is_skipped_and_logged():
    big_gap = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="50">
<note><pitch><step>D</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""
    score = parse_musicxml(big_gap)
    log = EditLog()
    report = fill_missing_measures(score, log=log, max_gap_size=8)
    assert report.gaps_found == 1
    # Oversized gap not filled — only the warning event exists.
    assert report.measures_inserted == 0
    assert log.by_op() == {"unfixable_gap": 1}


# --- placeholder content ----------------------------------------------


def test_placeholder_carries_full_bar_rest():
    score = parse_musicxml(_GAP_AT_3)
    log = EditLog()
    fill_missing_measures(score, log=log)
    # Find measure 3 (the placeholder).
    target = None
    for p in score.parts:
        for m in p.getElementsByClass("Measure"):
            if m.number == 3:
                target = m
                break
    assert target is not None
    # Total duration of inserted measure equals expected bar duration.
    total = sum(e.duration.quarterLength for e in target.notesAndRests)
    assert total == 4.0
    # Contents: exactly one rest, no pitched notes.
    rests = [e for e in target.notesAndRests if hasattr(e, "isRest") and e.isRest]
    notes_pitched = [
        e for e in target.notesAndRests
        if hasattr(e, "isRest") and not e.isRest
    ]
    assert len(rests) == 1
    assert notes_pitched == []


def test_handles_score_with_no_parts():
    from music21 import stream
    empty = stream.Score()
    log = EditLog()
    report = fill_missing_measures(empty, log=log)
    assert report.gaps_found == 0
    assert report.parts_processed == 0
