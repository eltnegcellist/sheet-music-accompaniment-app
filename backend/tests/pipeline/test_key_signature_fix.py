"""Tests for fix_dropped_key_accidentals — Phase 3-3 corollary.

The pass restores accidentals that the key signature implies but the
OMR forgot to write into the MusicXML.
"""

from app.pipeline.postprocess.edits import EditLog
from app.pipeline.postprocess.key_signature import fix_dropped_key_accidentals
from app.pipeline.stages.postprocess import parse_musicxml


# G major: F should be F#. Audiveris emitted F (no alter, no accidental
# tag) for one note. The pass should restore F# (midi 65 → 66).
_G_MAJOR_MISSING_SHARP = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><key><fifths>1</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


# F major: B should be Bb. Same pattern but in flat-land.
_F_MAJOR_MISSING_FLAT = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><key><fifths>-1</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


# C major (no key signature) — pass should be a no-op.
_C_MAJOR = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


# G major with explicit natural: composer intended F-natural (a chromatic
# shift). The pass must NOT touch it.
_G_MAJOR_WITH_EXPLICIT_NATURAL = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><key><fifths>1</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><alter>0</alter><octave>4</octave></pitch>
  <duration>4</duration><type>quarter</type><accidental>natural</accidental></note>
<note><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch>
  <duration>4</duration><type>quarter</type><accidental>sharp</accidental></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


def test_dropped_sharp_restored_in_G_major():
    score = parse_musicxml(_G_MAJOR_MISSING_SHARP)
    log = EditLog()
    report = fix_dropped_key_accidentals(score, log=log)
    assert report.candidates_checked == 1  # only the F qualifies
    assert report.accidentals_restored == 1
    midis = [int(n.pitch.midi) for n in score.flatten().notes]
    assert 66 in midis  # F# now present
    assert 65 not in midis  # natural F gone
    assert log.by_op() == {"key_accidental_restore": 1}


def test_dropped_flat_restored_in_F_major():
    score = parse_musicxml(_F_MAJOR_MISSING_FLAT)
    log = EditLog()
    report = fix_dropped_key_accidentals(score, log=log)
    assert report.accidentals_restored == 1
    midis = [int(n.pitch.midi) for n in score.flatten().notes]
    assert 70 in midis  # Bb (= 70)
    assert 71 not in midis  # natural B (71) gone


def test_no_key_signature_is_a_noop():
    score = parse_musicxml(_C_MAJOR)
    log = EditLog()
    report = fix_dropped_key_accidentals(score, log=log)
    assert report.candidates_checked == 0
    assert report.accidentals_restored == 0
    assert len(log) == 0


def test_explicit_natural_is_respected():
    """If Audiveris emitted an explicit natural, the composer overrode the
    key signature on purpose — leave that note alone."""
    score = parse_musicxml(_G_MAJOR_WITH_EXPLICIT_NATURAL)
    log = EditLog()
    report = fix_dropped_key_accidentals(score, log=log)
    # The F-natural (with explicit accidental) must NOT be flipped to F#.
    midis = [int(n.pitch.midi) for n in score.flatten().notes]
    assert 65 in midis  # F-natural still there
    assert report.accidentals_restored == 0


def test_handles_score_with_no_parts():
    from music21 import stream
    empty = stream.Score()
    log = EditLog()
    report = fix_dropped_key_accidentals(empty, log=log)
    assert report.candidates_checked == 0
    assert report.accidentals_restored == 0


def test_chord_constituents_are_skipped():
    """The pass must not crack open chord pitches — they share metadata."""
    chord_xml = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><key><fifths>1</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><chord/><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""
    score = parse_musicxml(chord_xml)
    log = EditLog()
    report = fix_dropped_key_accidentals(score, log=log)
    # The F is part of a chord (the next <note> has <chord/>); skip both.
    assert report.accidentals_restored == 0


def test_key_change_mid_piece_uses_active_signature():
    """When the key changes from G major to F major mid-piece, each
    measure's pass must use the correct signature."""
    xml = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><key><fifths>1</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<attributes><key><fifths>-1</fifths></key></attributes>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""
    score = parse_musicxml(xml)
    log = EditLog()
    report = fix_dropped_key_accidentals(score, log=log)
    # Measure 1: F → F# (1 fix). Measure 2: B → Bb (1 fix). Total 2.
    assert report.accidentals_restored == 2
