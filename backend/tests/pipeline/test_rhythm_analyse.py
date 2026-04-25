"""Tests for `analyse_measures` — the rhythm analyser used by 3-1 and Phase 4."""

import pytest

from app.pipeline.postprocess.rhythm import (
    MeasureRhythm,
    analyse_measures,
    measure_duration_match_rate,
)
from app.pipeline.stages.postprocess import parse_musicxml


# 4/4: m1 = 3 quarters (short by 1), m2 = 5 quarters (long by 1).
_SHORT_AND_LONG = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


def test_analyse_reports_delta_per_measure():
    score = parse_musicxml(_SHORT_AND_LONG)
    records = analyse_measures(score)
    assert len(records) == 2
    by_measure = {r.measure: r for r in records}
    assert by_measure[1].expected_ql == 4.0
    assert by_measure[1].actual_ql == 3.0
    assert by_measure[1].delta_ql == -1.0
    assert by_measure[1].matches is False
    assert by_measure[2].delta_ql == 1.0
    assert by_measure[2].matches is False


def test_match_rate_zero_when_all_off():
    score = parse_musicxml(_SHORT_AND_LONG)
    rate = measure_duration_match_rate(analyse_measures(score))
    assert rate == 0.0


_PERFECT = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>G</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""


def test_match_rate_one_when_all_match():
    score = parse_musicxml(_PERFECT)
    records = analyse_measures(score)
    assert all(r.matches for r in records)
    assert measure_duration_match_rate(records) == 1.0


def test_empty_records_produce_zero_rate():
    assert measure_duration_match_rate([]) == 0.0


def test_inherited_time_signature_reused_across_measures():
    score = parse_musicxml(_PERFECT)
    records = analyse_measures(score)
    # m2 has no <time> element but inherits 4/4 from m1.
    assert all(r.expected_ql == 4.0 for r in records)


def test_handles_score_with_no_parts():
    # Fabricate an empty Score directly.
    from music21 import stream
    empty = stream.Score()
    assert analyse_measures(empty) == []
