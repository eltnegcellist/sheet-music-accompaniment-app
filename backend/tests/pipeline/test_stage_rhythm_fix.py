"""End-to-end tests for the postprocess.rhythm_fix stage."""

import json
from pathlib import Path

from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import ArtifactRef, StageInput
from app.pipeline.stages.postprocess import postprocess_rhythm_fix


_BAD_RHYTHM = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


_GOOD_RHYTHM = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


def _make_input(tmp_path, xml: str | None, params: dict) -> StageInput:
    store = FileArtifactStore(root=tmp_path / "art", job_id="job1")
    if xml is not None:
        p = store.path_for("omr", "score.musicxml")
        p.write_text(xml, encoding="utf-8")
        store.put(ArtifactRef(kind="musicxml", path=str(p)))
    return StageInput(
        job_id="job1", image_id="page_0", params=params, artifacts=store, trace={}
    )


def _enabled_params() -> dict:
    return {
        "postprocess": {
            "rhythm_fix": {
                "enabled": True,
                "snap_durations": [1, 2, 4, 8, 16],
                "max_edits_per_measure": 4,
            }
        }
    }


# --- skipped path -------------------------------------------------------


def test_skipped_when_disabled(tmp_path):
    inp = _make_input(tmp_path, _GOOD_RHYTHM, params={
        "postprocess": {"rhythm_fix": {"enabled": False}}
    })
    out = postprocess_rhythm_fix(inp)
    assert out.status == "skipped"
    assert out.metrics.fields == {"postprocess.rhythm_fix.enabled": False}


def test_skipped_when_section_missing(tmp_path):
    inp = _make_input(tmp_path, _GOOD_RHYTHM, params={})
    out = postprocess_rhythm_fix(inp)
    assert out.status == "skipped"


# --- happy path ---------------------------------------------------------


def test_already_balanced_score_records_no_edits(tmp_path):
    inp = _make_input(tmp_path, _GOOD_RHYTHM, params=_enabled_params())
    out = postprocess_rhythm_fix(inp)
    assert out.status == "ok"
    assert out.metrics.fields["postprocess.rhythm_fix.edits_total"] == 0
    assert out.metrics.fields["postprocess.rhythm_fix.match_rate_before"] == 1.0
    assert out.metrics.fields["postprocess.rhythm_fix.match_rate_after"] == 1.0


def test_imbalanced_score_is_corrected(tmp_path):
    inp = _make_input(tmp_path, _BAD_RHYTHM, params=_enabled_params())
    out = postprocess_rhythm_fix(inp)
    assert out.status == "ok"
    # m1 short by 1 -> rest_insert; m2 long by 1 -> tail_delete.
    assert out.metrics.fields["postprocess.rhythm_fix.edits_total"] >= 2
    assert out.metrics.fields["postprocess.rhythm_fix.match_rate_after"] == 1.0
    # Both before<after — Phase 4 reads these to compute the metric trend.
    assert (
        out.metrics.fields["postprocess.rhythm_fix.match_rate_before"]
        < out.metrics.fields["postprocess.rhythm_fix.match_rate_after"]
    )


def test_writes_musicxml_artifact(tmp_path):
    inp = _make_input(tmp_path, _BAD_RHYTHM, params=_enabled_params())
    out = postprocess_rhythm_fix(inp)
    ref = inp.artifacts.get("postprocess_musicxml")
    assert ref is not None
    assert Path(ref.path).exists()
    assert out.status == "ok"


def test_writes_edits_jsonl_artifact(tmp_path):
    inp = _make_input(tmp_path, _BAD_RHYTHM, params=_enabled_params())
    postprocess_rhythm_fix(inp)
    ref = inp.artifacts.get("postprocess_edits")
    assert ref is not None
    lines = Path(ref.path).read_text(encoding="utf-8").splitlines()
    assert lines  # non-empty
    parsed = [json.loads(l) for l in lines]
    # Each edit event carries op + reason at minimum.
    assert all("op" in p and "reason" in p for p in parsed)


# --- failure paths ------------------------------------------------------


def test_failed_on_missing_input(tmp_path):
    inp = _make_input(tmp_path, xml=None, params=_enabled_params())
    out = postprocess_rhythm_fix(inp)
    assert out.status == "failed"
    assert "no MusicXML upstream" in (out.error or "")


def test_failed_on_malformed_xml(tmp_path):
    inp = _make_input(tmp_path, "<not>", params=_enabled_params())
    out = postprocess_rhythm_fix(inp)
    assert out.status == "failed"


def test_registered_under_canonical_name():
    from app.pipeline.registry import default_registry
    assert default_registry.resolve("postprocess.rhythm_fix") is postprocess_rhythm_fix
