"""Tests for `rebuild_voices` (voice rebuild + rollback guard)."""

from app.pipeline.postprocess.edits import EditLog
from app.pipeline.postprocess.voice_rebuild import rebuild_voices
from app.pipeline.stages.postprocess import parse_musicxml


_PIANO_SCORE = """<score-partwise><part-list>
<score-part id="P1"><part-name>Piano</part-name></score-part>
</part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves></attributes>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type><staff>1</staff></note>
<note><pitch><step>C</step><octave>3</octave></pitch><duration>4</duration><type>quarter</type><staff>2</staff></note>
<note><pitch><step>E</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type><staff>1</staff></note>
<note><pitch><step>E</step><octave>3</octave></pitch><duration>4</duration><type>quarter</type><staff>2</staff></note>
</measure>
</part></score-partwise>"""


_NON_PIANO_SCORE = """<score-partwise><part-list>
<score-part id="P1"><part-name>Violin</part-name></score-part>
</part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


def test_non_piano_part_is_skipped():
    score = parse_musicxml(_NON_PIANO_SCORE)
    log = EditLog()
    report = rebuild_voices(score, log=log)
    assert report.parts_processed == []
    assert len(log) == 0


def test_clean_piano_score_produces_no_edits():
    score = parse_musicxml(_PIANO_SCORE)
    log = EditLog()
    report = rebuild_voices(score, log=log)
    # Music21 split the part into RH/LH already; pitches and parts agree
    # so no reassignment is needed.
    assert report.notes_reassigned == 0
    assert report.rollback is False
    assert report.reassignment_rate == 0.0


def test_rollback_when_reassignment_rate_high():
    # Multi-staff piano where every "RH" note is mis-assigned to a low
    # pitch. The pitch policy says they should all move to voice 2 —
    # 100% reassignment of the RH part exceeds the 30% threshold.
    bad_xml = """<score-partwise><part-list>
<score-part id="P1"><part-name>Piano</part-name></score-part>
</part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves></attributes>
<note><pitch><step>C</step><octave>2</octave></pitch><duration>4</duration><type>quarter</type><staff>1</staff></note>
<note><pitch><step>D</step><octave>2</octave></pitch><duration>4</duration><type>quarter</type><staff>1</staff></note>
<note><pitch><step>E</step><octave>2</octave></pitch><duration>4</duration><type>quarter</type><staff>1</staff></note>
<note><pitch><step>F</step><octave>2</octave></pitch><duration>4</duration><type>quarter</type><staff>1</staff></note>
</measure>
</part></score-partwise>"""
    score = parse_musicxml(bad_xml)
    log = EditLog()
    report = rebuild_voices(score, log=log, rollback_rate_threshold=0.30)
    # All 4 RH notes' staff hint says voice=1 but the pitch policy says
    # voice=2 (everything below middle C). 100% reassignment > 30% → rollback.
    assert report.rollback is True
    assert log.by_op() == {"voice_rebuild_rollback": 1}


def test_zero_threshold_always_rolls_back():
    score = parse_musicxml(_PIANO_SCORE)
    log = EditLog()
    # Threshold 0 means any reassignment is too many.
    report = rebuild_voices(score, log=log, rollback_rate_threshold=0.0)
    # Clean score has 0% reassignment so the rollback guard does NOT fire here.
    assert report.rollback is False


def test_score_without_piano_returns_empty_report():
    score = parse_musicxml(_NON_PIANO_SCORE)
    report = rebuild_voices(score, log=EditLog())
    assert report.notes_total == 0
    assert report.notes_reassigned == 0
