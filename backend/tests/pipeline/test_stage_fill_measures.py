"""End-to-end tests for postprocess.fill_measures stage."""

from pathlib import Path

from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import ArtifactRef, StageInput
from app.pipeline.stages.postprocess import postprocess_fill_measures


_GAP_AT_3 = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="2">
<note><pitch><step>D</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
<measure number="4">
<note><pitch><step>F</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note>
</measure>
</part></score-partwise>"""


def _make(tmp_path, params, xml=_GAP_AT_3) -> StageInput:
    store = FileArtifactStore(root=tmp_path / "art", job_id="job1")
    p = store.path_for("omr", "score.musicxml")
    p.write_text(xml, encoding="utf-8")
    store.put(ArtifactRef(kind="musicxml", path=str(p)))
    return StageInput(
        job_id="job1", image_id="page_0", params=params, artifacts=store, trace={}
    )


def test_disabled_is_skipped(tmp_path):
    out = postprocess_fill_measures(
        _make(tmp_path, params={"postprocess": {"fill_measures": {"enabled": False}}})
    )
    assert out.status == "skipped"


def test_section_missing_is_skipped(tmp_path):
    out = postprocess_fill_measures(_make(tmp_path, params={}))
    assert out.status == "skipped"


def test_enabled_inserts_placeholder(tmp_path):
    inp = _make(tmp_path, params={"postprocess": {"fill_measures": {"enabled": True}}})
    out = postprocess_fill_measures(inp)
    assert out.status == "ok"
    assert out.metrics.fields["postprocess.fill_measures.gaps_found"] == 1
    assert out.metrics.fields["postprocess.fill_measures.measures_inserted"] == 1
    # The output XML must include measure 3 now.
    pp = Path(inp.artifacts.get("postprocess_musicxml").path).read_text("utf-8")
    assert 'number="3"' in pp


def test_writes_edit_log(tmp_path):
    inp = _make(tmp_path, params={"postprocess": {"fill_measures": {"enabled": True}}})
    postprocess_fill_measures(inp)
    log_ref = inp.artifacts.get("postprocess_missing_measure_edits")
    assert log_ref is not None
    contents = Path(log_ref.path).read_text("utf-8")
    assert "measure_insert" in contents


def test_failed_when_input_missing(tmp_path):
    store = FileArtifactStore(root=tmp_path / "a", job_id="j")
    inp = StageInput(
        job_id="j", image_id="p",
        params={"postprocess": {"fill_measures": {"enabled": True}}},
        artifacts=store, trace={},
    )
    out = postprocess_fill_measures(inp)
    assert out.status == "failed"


def test_registered_under_canonical_name():
    from app.pipeline.registry import default_registry
    assert default_registry.resolve("postprocess.fill_measures") is postprocess_fill_measures


def test_v4_param_set_loads_with_fill_measures(tmp_path):
    """v4_with_pitch.yaml must validate against the schema with the new section."""
    from app.pipeline.params_loader import load_params
    PARAMS_DIR = Path(__file__).resolve().parents[2] / "params"
    SCHEMA = PARAMS_DIR / "schema.json"
    r = load_params("v4_with_pitch", PARAMS_DIR, schema_path=SCHEMA)
    assert r.data["postprocess"]["fill_measures"]["enabled"] is True
