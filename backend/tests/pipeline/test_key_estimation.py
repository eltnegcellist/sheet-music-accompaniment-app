"""Tests for K-S key estimation (Phase 3-3-a)."""

import pytest

from app.pipeline.postprocess.key_estimation import (
    KeyEstimate,
    estimate_key,
    pitch_class_histogram,
)
from app.pipeline.stages.postprocess import parse_musicxml


_C_MAJOR_SCALE = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


_A_MINOR_SCALE = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>A</step><octave>3</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>3</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


def test_estimate_c_major_returns_tonic_zero():
    score = parse_musicxml(_C_MAJOR_SCALE)
    key = estimate_key(score)
    assert key is not None
    assert key.tonic_pc == 0
    assert key.mode == "major"
    # Pure scale + repeated tonic — should be a strong match.
    assert key.confidence > 0.7


def test_estimate_returns_none_for_empty_score():
    empty = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1"/></part></score-partwise>"""
    score = parse_musicxml(empty)
    assert estimate_key(score) is None


def test_estimate_a_minor():
    score = parse_musicxml(_A_MINOR_SCALE)
    key = estimate_key(score)
    assert key is not None
    # A-minor and C-major share a key signature; either tonic is plausible
    # for a pure scale. Just check the result is one of the relatives.
    assert (key.tonic_pc, key.mode) in {(0, "major"), (9, "minor")}


def test_scale_pcs_for_c_major():
    key = KeyEstimate(tonic_pc=0, mode="major", confidence=1.0)
    assert key.scale_pcs() == {0, 2, 4, 5, 7, 9, 11}


def test_scale_pcs_for_a_minor():
    key = KeyEstimate(tonic_pc=9, mode="minor", confidence=1.0)
    # A natural minor: A B C D E F G  → pcs 9, 11, 0, 2, 4, 5, 7
    assert key.scale_pcs() == {9, 11, 0, 2, 4, 5, 7}


def test_pitch_class_histogram_weights_by_duration():
    # One whole-note C (duration 16, divisions=4 → qL=4) vs one quarter D.
    xml = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="2">
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(xml)
    bins = pitch_class_histogram(score)
    # C bin == 4 (one whole), D bin == 4 (four quarters).
    assert bins[0] == 4.0
    assert bins[2] == 4.0
    # All other bins zero.
    assert sum(bins[i] for i in range(12) if i not in (0, 2)) == 0.0
