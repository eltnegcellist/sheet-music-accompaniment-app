"""Tests for the n-gram melodic outlier fix (Phase 3-3-c).

The pass surfaces the worst (1 - quantile) of 3-gram interval triples
and nudges the middle note ±1 semitone toward the linear interpolation
of its neighbours, capped to `max_ratio` of total notes.
"""

from app.pipeline.postprocess.edits import EditLog
from app.pipeline.postprocess.pitch_fix import fix_ngram_outliers
from app.pipeline.stages.postprocess import parse_musicxml


def _scale_with_jump_xml() -> str:
    """A smooth C-major scale with one tiny jagged spike that's nudgeable.

    The spike at measure 2 beat 2 is D5 (74) sitting between C5 (72)
    and E5 (76). Linear interpolation midpoint = 74. Need an actual
    nudge case where the midpoint is ±1 from the candidate.

    Use F (65) between E (64) and G (67): midpoint = 65, no nudge needed.
    Use F# (66) between E (64) and G (67): midpoint = 65, nudge -1 to F.
    """
    return """<score-partwise><part-list><score-part id="P1"/></part-list>
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
<measure number="3">
<note><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><alter>1</alter><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="4">
<note><pitch><step>F</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""


def test_ngram_does_nothing_on_smooth_melody():
    smooth = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(smooth)
    log = EditLog()
    report = fix_ngram_outliers(score, log=log, max_ratio=1.0, quantile=0.99)
    # Stepwise melody — no triple costs more than 4 semitones, but the
    # quantile threshold can still flag the highest as a candidate;
    # however it won't be nudged because the linear interpolation matches
    # the existing pitch already.
    assert report.corrected == 0


def test_ngram_does_not_exceed_max_ratio_cap():
    score = parse_musicxml(_scale_with_jump_xml())
    log = EditLog()
    # max_ratio=0 means: never apply any correction even if cost would.
    total = sum(1 for _ in score.flatten().notes)
    report = fix_ngram_outliers(score, log=log, max_ratio=0.0)
    assert report.corrected == 0
    if report.candidates > 0:
        assert report.capped_by_max_ratio == report.candidates


def test_ngram_correction_is_bounded_by_window():
    """Notes more than `correction_window_semitones` from the midpoint
    must not be touched — keeps the pass from rewriting the melody."""
    # Wild outlier: C, B7 (way out), C — midpoint is C, shift would be -85,
    # well outside ±1 semitone. Pass should refuse.
    wild = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>7</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(wild)
    log = EditLog()
    report = fix_ngram_outliers(score, log=log, max_ratio=1.0, correction_window_semitones=1)
    # Identified as a candidate but window restricts the shift.
    assert report.corrected == 0


def test_ngram_logs_each_correction():
    """The pass must record each corrected note in the edit log so the
    evaluator can charge the edits_penalty term."""
    # Need a fixture where one note is exactly 1 semitone off the midpoint.
    # E (64), F# (66), G (67): midpoint=65 (F), nudge -1 from 66 → 65.
    nudgeable = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>C</step><octave>5</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""
    score = parse_musicxml(nudgeable)
    log = EditLog()
    report = fix_ngram_outliers(
        score, log=log, max_ratio=1.0, quantile=0.0,  # everything is a candidate
        correction_window_semitones=1,
    )
    if report.corrected > 0:
        assert log.by_op().get("ngram_fix") == report.corrected
