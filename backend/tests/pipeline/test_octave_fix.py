"""Tests for octave-error correction (Phase 3-3-d)."""

from app.pipeline.postprocess.edits import EditLog
from app.pipeline.postprocess.pitch_fix import fix_octave_errors
from app.pipeline.stages.postprocess import parse_musicxml


def test_lone_octave_jump_is_corrected():
    """C5 surrounded by C4 / D4 — Audiveris classic ledger-line confusion.

    The note's prev jump (60 -> 72 = 12) and next jump (72 -> 62 = 10)
    are both above the 18-semitone threshold? No — they're 12 and 10.
    Need a more dramatic jump to clear the threshold.
    """
    # Use C2 (36) flanked by E5 (76) and D5 (74). Jumps: 76-36=40, 74-36=38.
    # Shifting C2 +24 → C4 (60): jumps 76-60=16, 74-60=14, both < 18.
    # But shift is ±12 only; +12 → C3 (48): jumps 76-48=28, 74-48=26, still > 18.
    # So this won't fix in one step. Use C2 with smaller flanking jumps.
    #
    # Use E5 (76), C2 (36), D5 (74). Shift +12 → C3 (48). Jumps now 28, 26.
    # That's still > 18 so the pass refuses.  Need ±12 to push within 18.
    #
    # Use F4 (65), F5 (77), F4 (65). Jumps 12, 12 → < 18. No correction.
    # Use F4 (65), F6 (89), F4 (65). Jumps 24, 24 > 18. Shift -12 → F5 (77).
    # New jumps 12, 12 < 18. Total 24 < 48. Correction applies.
    fixture = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>6</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(fixture)
    log = EditLog()
    report = fix_octave_errors(score, log=log, jump_threshold_semitones=18)
    assert report.candidates == 1
    assert report.corrected == 1
    midis = [int(n.pitch.midi) for n in score.flatten().notes]
    assert 89 not in midis  # F6 (the spike) was shifted
    assert 77 in midis      # to F5
    assert log.by_op() == {"octave_fix": 1}


def test_genuine_octave_leap_is_left_alone():
    """A real octave leap from low C to high C must NOT be flattened.

    Both flanking jumps are exactly 12 semitones — under the default
    threshold of 18 — so the pass treats it as legitimate.
    """
    fixture = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(fixture)
    log = EditLog()
    report = fix_octave_errors(score, log=log)
    assert report.corrected == 0
    assert len(log) == 0


def test_no_correction_when_both_octave_shifts_still_jump():
    """If neither +12 nor -12 brings the note within threshold, refuse."""
    # F4 (65), C8 (108), F4 (65). Jumps 43, 43. -12 → C7 (96): 31, 31 still > 18.
    # +12 → not allowed (out of range eventually) but try: C9 (120): 55, 55 worse.
    fixture = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>8</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(fixture)
    log = EditLog()
    report = fix_octave_errors(score, log=log)
    assert report.candidates == 1
    assert report.corrected == 0


def test_does_nothing_on_smooth_melody():
    fixture = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(fixture)
    log = EditLog()
    report = fix_octave_errors(score, log=log)
    assert report.candidates == 0
    assert report.corrected == 0


def test_handles_score_with_too_few_notes():
    """Only 2 notes → no triples → pass returns empty report cleanly."""
    fixture = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1"><measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>8</duration><type>half</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>8</duration><type>half</type></note>
</measure></part></score-partwise>"""
    score = parse_musicxml(fixture)
    log = EditLog()
    report = fix_octave_errors(score, log=log)
    assert report.candidates == 0
    assert report.corrected == 0
