"""Tests for the Phase 4-1 metric functions."""

import pytest

from app.pipeline.evaluate.metrics import (
    compute_density,
    compute_in_range,
    compute_key_consistency,
    compute_measure_duration_match,
    compute_structure_consistency,
    score_musicxml,
)
from app.pipeline.stages.postprocess import parse_musicxml


_GOOD_C_MAJOR = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


# --- per-metric ---------------------------------------------------------


def test_measure_duration_match_full_when_balanced():
    score = parse_musicxml(_GOOD_C_MAJOR)
    assert compute_measure_duration_match(score) == 1.0


def test_in_range_is_one_for_in_range_pitches():
    score = parse_musicxml(_GOOD_C_MAJOR)
    assert compute_in_range(score) == 1.0


def test_in_range_drops_with_out_of_range_pitches():
    out_of_range_xml = _GOOD_C_MAJOR.replace(
        "<octave>4</octave>", "<octave>9</octave>", 1
    )
    score = parse_musicxml(out_of_range_xml)
    # 1 of 8 notes is out of range -> 7/8.
    assert pytest.approx(compute_in_range(score), abs=1e-6) == 7 / 8


def test_density_full_for_uniform_counts():
    score = parse_musicxml(_GOOD_C_MAJOR)
    # Two measures, both 4 notes — IQR is 0 but still in-band.
    assert compute_density(score) == 1.0


def test_key_consistency_high_for_clean_C_major():
    score = parse_musicxml(_GOOD_C_MAJOR)
    # Pure C major scale tones — K-S correlation should be strong.
    assert compute_key_consistency(score) > 0.7


def test_key_consistency_zero_for_no_notes():
    empty = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1"/></part></score-partwise>"""
    score = parse_musicxml(empty)
    assert compute_key_consistency(score) == 0.0


def test_structure_consistency_full_for_single_part():
    score = parse_musicxml(_GOOD_C_MAJOR)
    assert compute_structure_consistency(score) == 1.0


def test_structure_consistency_drops_when_part_counts_diverge():
    # Two parts, one has 1 measure, the other 2.
    diverging = """<score-partwise><part-list>
<score-part id="P1"/><score-part id="P2"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part>
<part id="P2">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>3</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>3</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>3</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>3</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2"><note><pitch><step>G</step><octave>3</octave></pitch><duration>16</duration><type>whole</type></note></measure>
</part></score-partwise>"""
    score = parse_musicxml(diverging)
    s = compute_structure_consistency(score)
    assert s < 1.0


# --- aggregator ---------------------------------------------------------


def test_score_card_aggregates_all_six_indicators():
    score = parse_musicxml(_GOOD_C_MAJOR)
    card = score_musicxml(score, edits_count=0)
    assert 0.0 <= card.measure_duration_match <= 1.0
    assert 0.0 <= card.in_range <= 1.0
    assert 0.0 <= card.density <= 1.0
    assert 0.0 <= card.key_consistency <= 1.0
    assert 0.0 <= card.structure_consistency <= 1.0
    assert card.edits_penalty == 0.0


def test_edits_penalty_is_edits_per_note():
    score = parse_musicxml(_GOOD_C_MAJOR)
    card = score_musicxml(score, edits_count=2)
    # 2 edits / 8 notes = 0.25
    assert pytest.approx(card.edits_penalty, abs=1e-6) == 0.25


def test_edits_penalty_handles_zero_notes():
    empty = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1"/></part></score-partwise>"""
    score = parse_musicxml(empty)
    # No notes — edits count flows through unmodified so report.md still
    # shows the raw edit volume.
    card = score_musicxml(score, edits_count=3)
    assert card.edits_penalty == 3.0
