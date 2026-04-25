"""End-to-end tests for the postprocess.voice_rebuild stage."""

from pathlib import Path

from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import ArtifactRef, StageInput
from app.pipeline.stages.postprocess import postprocess_voice_rebuild


_PIANO = """<score-partwise><part-list>
<score-part id="P1"><part-name>Piano</part-name></score-part>
</part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves></attributes>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type><staff>1</staff></note>
<note><pitch><step>C</step><octave>3</octave></pitch><duration>4</duration><type>quarter</type><staff>2</staff></note>
</measure></part></score-partwise>"""


def _make(tmp_path, params, xml=_PIANO):
    store = FileArtifactStore(root=tmp_path / "art", job_id="job1")
    p = store.path_for("omr", "score.musicxml")
    p.write_text(xml, encoding="utf-8")
    store.put(ArtifactRef(kind="musicxml", path=str(p)))
    return StageInput(
        job_id="job1", image_id="page_0", params=params, artifacts=store, trace={}
    )


def _enabled():
    return {
        "postprocess": {
            "voice_rebuild": {"enabled": True, "rollback_rate_threshold": 0.30}
        }
    }


def test_disabled_is_skipped(tmp_path):
    out = postprocess_voice_rebuild(
        _make(tmp_path, {"postprocess": {"voice_rebuild": {"enabled": False}}})
    )
    assert out.status == "skipped"


def test_clean_piano_score_records_no_rollback(tmp_path):
    inp = _make(tmp_path, _enabled())
    out = postprocess_voice_rebuild(inp)
    assert out.status == "ok"
    assert out.metrics.fields["postprocess.voice_rebuild.rollback"] is False
    assert out.metrics.fields["postprocess.voice_rebuild.notes_reassigned"] == 0
    # Both artifacts recorded.
    assert inp.artifacts.get("postprocess_musicxml") is not None
    assert inp.artifacts.get("postprocess_voice_edits") is not None


def test_rollback_triggers_when_assignments_disagree_strongly(tmp_path):
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
</measure></part></score-partwise>"""
    inp = _make(tmp_path, _enabled(), xml=bad_xml)
    out = postprocess_voice_rebuild(inp)
    assert out.status == "ok"
    assert out.metrics.fields["postprocess.voice_rebuild.rollback"] is True
    # The voice edit log carries one rollback event.
    edits_path = Path(inp.artifacts.get("postprocess_voice_edits").path)
    assert "voice_rebuild_rollback" in edits_path.read_text(encoding="utf-8")


def test_failed_when_no_input(tmp_path):
    store = FileArtifactStore(root=tmp_path / "a", job_id="j")
    inp = StageInput(
        job_id="j", image_id="p", params=_enabled(), artifacts=store, trace={}
    )
    out = postprocess_voice_rebuild(inp)
    assert out.status == "failed"


def test_registered_under_canonical_name():
    from app.pipeline.registry import default_registry
    assert default_registry.resolve("postprocess.voice_rebuild") is postprocess_voice_rebuild
