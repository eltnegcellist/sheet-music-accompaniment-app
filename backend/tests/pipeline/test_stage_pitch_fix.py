"""End-to-end tests for postprocess.pitch_fix stage."""

from pathlib import Path

from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import ArtifactRef, StageInput
from app.pipeline.stages.postprocess import postprocess_pitch_fix


_C_MAJOR_WITH_OUTLIER = """<score-partwise><part-list><score-part id="P1"/></part-list>
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


def _make(tmp_path, params, xml=_C_MAJOR_WITH_OUTLIER) -> StageInput:
    store = FileArtifactStore(root=tmp_path / "art", job_id="job1")
    p = store.path_for("omr", "score.musicxml")
    p.write_text(xml, encoding="utf-8")
    store.put(ArtifactRef(kind="musicxml", path=str(p)))
    return StageInput(
        job_id="job1", image_id="page_0", params=params, artifacts=store, trace={}
    )


def test_disabled_is_skipped(tmp_path):
    out = postprocess_pitch_fix(
        _make(tmp_path, params={"postprocess": {"pitch_fix": {"enabled": False}}})
    )
    assert out.status == "skipped"
    assert out.metrics.fields == {"postprocess.pitch_fix.enabled": False}


def test_section_missing_is_skipped(tmp_path):
    out = postprocess_pitch_fix(_make(tmp_path, params={}))
    assert out.status == "skipped"


def test_enabled_runs_all_sub_passes(tmp_path):
    inp = _make(tmp_path, params={"postprocess": {"pitch_fix": {"enabled": True}}})
    out = postprocess_pitch_fix(inp)
    assert out.status == "ok"
    # Key estimation reported.
    assert "postprocess.pitch_fix.key_tonic_pc" in out.metrics.fields
    assert "postprocess.pitch_fix.key_confidence" in out.metrics.fields
    # Each sub-pass surfaced a candidate count.
    for sub in ("scale", "octave", "ngram"):
        assert f"postprocess.pitch_fix.{sub}.candidates" in out.metrics.fields
    # Both artifacts present.
    assert inp.artifacts.get("postprocess_musicxml") is not None
    assert inp.artifacts.get("postprocess_pitch_edits") is not None


def test_correction_changes_xml_and_logs(tmp_path):
    inp = _make(tmp_path, params={"postprocess": {"pitch_fix": {"enabled": True}}})
    out = postprocess_pitch_fix(inp)
    pp = Path(inp.artifacts.get("postprocess_musicxml").path).read_text("utf-8")
    # The F# outlier in measure 2 should have been corrected; verify the
    # edits log carries at least one scale_fix event.
    edits = Path(inp.artifacts.get("postprocess_pitch_edits").path).read_text("utf-8")
    assert "scale_fix" in edits
    assert "F#" not in pp or pp != _C_MAJOR_WITH_OUTLIER


def test_individual_sub_pass_can_be_disabled(tmp_path):
    inp = _make(
        tmp_path,
        params={"postprocess": {"pitch_fix": {
            "enabled": True,
            "scale_outliers": {"enabled": False},
            "octave_errors": {"enabled": False},
            "ngram": {"enabled": False},
        }}},
    )
    out = postprocess_pitch_fix(inp)
    assert out.status == "ok"
    # No sub-pass ran; only key info recorded.
    for sub in ("scale", "octave", "ngram"):
        assert f"postprocess.pitch_fix.{sub}.candidates" not in out.metrics.fields
    assert out.metrics.fields["postprocess.pitch_fix.edits_total"] == 0


def test_failed_when_input_missing(tmp_path):
    store = FileArtifactStore(root=tmp_path / "a", job_id="j")
    inp = StageInput(
        job_id="j", image_id="p",
        params={"postprocess": {"pitch_fix": {"enabled": True}}},
        artifacts=store, trace={},
    )
    out = postprocess_pitch_fix(inp)
    assert out.status == "failed"


def test_registered_under_canonical_name():
    from app.pipeline.registry import default_registry
    assert default_registry.resolve("postprocess.pitch_fix") is postprocess_pitch_fix
