"""Tests for scale-outlier correction (Phase 3-3-b)."""

import pytest

from app.pipeline.postprocess.edits import EditLog
from app.pipeline.postprocess.key_estimation import KeyEstimate, estimate_key
from app.pipeline.postprocess.pitch_fix import fix_scale_outliers
from app.pipeline.stages.postprocess import parse_musicxml


# Long C-major-anchored melody with one isolated F# in the middle. The
# heavy C-major bias is intentional so K-S picks tonic_pc=0 even with
# the lone outlier present (otherwise the estimator gets dragged toward
# G major where F# is in-scale).
_ONE_OUTLIER = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="3">
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="4">
<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""


# Strong C-major anchoring everywhere. Measure 2 has TWO isolated
# outliers (F# at beat 2 and A# at beat 4) each surrounded by in-scale
# notes — both qualify as candidates individually. The pass should
# refuse to fix either because the measure carries > max_per_measure
# accidentals (signal: the bar uses chromatic colour intentionally).
_TWO_OUTLIERS_ONE_MEASURE = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><alter>1</alter><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="3">
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="4">
<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""


def test_isolated_outlier_is_corrected():
    score = parse_musicxml(_ONE_OUTLIER)
    key = estimate_key(score)
    assert key is not None
    log = EditLog()
    report = fix_scale_outliers(score, key, log=log)
    assert report.candidates == 1
    assert report.corrected == 1
    # The F# (midi 66) should now be a scale tone (F=65 or G=67).
    midis = [int(n.pitch.midi) for n in score.flatten().notes]
    assert 66 not in midis
    assert any("scale_fix" == e.op for e in log)


def test_low_confidence_disables_correction():
    score = parse_musicxml(_ONE_OUTLIER)
    weak_key = KeyEstimate(tonic_pc=0, mode="major", confidence=0.2)
    log = EditLog()
    report = fix_scale_outliers(score, weak_key, log=log, confidence_floor=0.6)
    # No correction when confidence below floor.
    assert report.corrected == 0
    assert len(log) == 0


def test_per_measure_cap_skips_busy_bars():
    score = parse_musicxml(_TWO_OUTLIERS_ONE_MEASURE)
    key = estimate_key(score)
    assert key is not None
    log = EditLog()
    report = fix_scale_outliers(score, key, log=log, max_per_measure=1)
    # 2 candidates, both skipped because they share a measure.
    assert report.candidates == 2
    assert report.skipped_by_per_measure_cap == 2
    assert report.corrected == 0


def test_no_corrections_when_score_already_in_key():
    clean = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(clean)
    key = estimate_key(score)
    assert key is not None
    log = EditLog()
    report = fix_scale_outliers(score, key, log=log)
    assert report.candidates == 0
    assert report.corrected == 0


def test_chord_constituents_are_skipped():
    """Chords aren't decomposed by the scale fixer — flipping one note in a
    chord would change the harmony in surprising ways."""
    chord_xml = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><chord/><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(chord_xml)
    key = estimate_key(score)
    assert key is not None
    log = EditLog()
    report = fix_scale_outliers(score, key, log=log)
    # The F# is a chord member, not a single Note → skipped.
    assert report.candidates == 0


def test_explicit_accidental_is_skipped():
    """Visible accidentals are treated as intentional notation and not auto-fixed."""
    score = parse_musicxml(_ONE_OUTLIER)
    key = estimate_key(score)
    assert key is not None

    # Mark the outlier F# as explicitly shown in notation.
    outlier = [n for n in score.flatten().notes if int(n.pitch.midi) == 66][0]
    assert outlier.pitch.accidental is not None
    outlier.pitch.accidental.displayStatus = True

    log = EditLog()
    report = fix_scale_outliers(score, key, log=log)

    assert report.candidates == 1
    assert report.skipped_explicit_accidental == 1
    assert report.corrected == 0
    assert int(outlier.pitch.midi) == 66
    assert len(log) == 0
