"""End-to-end tests for the evaluate pipeline stage."""

import json
from pathlib import Path

from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import ArtifactRef, StageInput
from app.pipeline.stages.evaluate import evaluate_stage


_PERFECT = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
<measure number="2">
<note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


_WEIGHTS = {
    "measure_duration_match": 0.35,
    "in_range": 0.15,
    "density": 0.10,
    "key_consistency": 0.15,
    "structure_consistency": 0.25,
}


def _scoring_params(threshold: float = 0.7, on_low: str = "skip") -> dict:
    return {
        "scoring": {
            "weights": _WEIGHTS,
            "page_threshold": threshold,
            "on_low_score": on_low,
        }
    }


def _make(tmp_path, params, xml: str | None = _PERFECT) -> StageInput:
    store = FileArtifactStore(root=tmp_path / "art", job_id="job1")
    if xml is not None:
        p = store.path_for("omr", "score.musicxml")
        p.write_text(xml, encoding="utf-8")
        store.put(ArtifactRef(kind="musicxml", path=str(p)))
    return StageInput(
        job_id="job1", image_id="page_0", params=params, artifacts=store, trace={}
    )


# --- happy path ---------------------------------------------------------


def test_passes_when_score_above_threshold(tmp_path):
    inp = _make(tmp_path, _scoring_params(threshold=0.5))
    out = evaluate_stage(inp)
    assert out.status == "ok"
    assert out.metrics.fields["evaluate.passed"] is True
    assert out.metrics.fields["evaluate.final_score"] >= 0.5
    # All 6 sub-scores surface for the API response.
    for key in (
        "measure_duration_match",
        "in_range",
        "density",
        "key_consistency",
        "structure_consistency",
        "edits_penalty",
    ):
        assert f"evaluate.{key}" in out.metrics.fields


def test_chosen_json_persisted(tmp_path):
    inp = _make(tmp_path, _scoring_params(threshold=0.5))
    evaluate_stage(inp)
    ref = inp.artifacts.get("chosen")
    assert ref is not None
    data = json.loads(Path(ref.path).read_text(encoding="utf-8"))
    assert data["job_id"] == "job1"
    assert "final_score" in data
    assert "score_card" in data
    assert data["passed"] is True


# --- low-score branches -------------------------------------------------


def test_low_score_skips_when_on_low_skip(tmp_path):
    inp = _make(tmp_path, _scoring_params(threshold=0.99))
    out = evaluate_stage(inp)
    assert out.status == "skipped"
    assert out.metrics.fields["evaluate.failure_class"] == "evaluate.low_score_below_threshold"


def test_low_score_retries_when_on_low_retry(tmp_path):
    inp = _make(tmp_path, _scoring_params(threshold=0.99, on_low="retry"))
    out = evaluate_stage(inp)
    assert out.status == "retryable"


def test_low_score_fails_job_when_on_low_fail_job(tmp_path):
    inp = _make(tmp_path, _scoring_params(threshold=0.99, on_low="fail_job"))
    out = evaluate_stage(inp)
    assert out.status == "failed"


# --- preference for postprocess artifact -------------------------------


def test_prefers_postprocess_musicxml_when_present(tmp_path):
    """When postprocess wrote its own MusicXML, evaluate must read that."""
    store = FileArtifactStore(root=tmp_path / "art", job_id="job1")
    omr_p = store.path_for("omr", "raw.musicxml")
    omr_p.write_text("<score-partwise/>", encoding="utf-8")  # broken
    store.put(ArtifactRef(kind="musicxml", path=str(omr_p)))
    pp_p = store.path_for("postprocess", "fixed.musicxml")
    pp_p.write_text(_PERFECT, encoding="utf-8")
    store.put(ArtifactRef(kind="postprocess_musicxml", path=str(pp_p)))
    inp = StageInput(
        job_id="job1", image_id="page_0",
        params=_scoring_params(threshold=0.5),
        artifacts=store, trace={},
    )
    out = evaluate_stage(inp)
    # If we'd accidentally read the broken OMR XML music21 would fail to
    # parse and the stage would return failed. ok proves we read the fixed one.
    assert out.status == "ok"


# --- error paths --------------------------------------------------------


def test_failed_when_weights_missing(tmp_path):
    inp = _make(tmp_path, params={"scoring": {}})
    out = evaluate_stage(inp)
    assert out.status == "failed"


def test_failed_when_weights_invalid(tmp_path):
    bad = dict(_WEIGHTS); bad["density"] = 0.5  # sum != 1
    inp = _make(tmp_path, {"scoring": {"weights": bad, "page_threshold": 0.5}})
    out = evaluate_stage(inp)
    assert out.status == "failed"


def test_failed_when_no_xml(tmp_path):
    inp = _make(tmp_path, _scoring_params(), xml=None)
    out = evaluate_stage(inp)
    assert out.status == "failed"
    assert "no MusicXML upstream" in (out.error or "")


# --- edits counted via log artifacts -----------------------------------


def test_counts_edits_from_postprocess_logs(tmp_path):
    store = FileArtifactStore(root=tmp_path / "art", job_id="job1")
    p = store.path_for("omr", "score.musicxml")
    p.write_text(_PERFECT, encoding="utf-8")
    store.put(ArtifactRef(kind="musicxml", path=str(p)))
    log_p = store.path_for("postprocess", "edits.jsonl")
    log_p.write_text(
        "\n".join(['{"op":"snap"}', '{"op":"rest_insert"}', '{"op":"snap"}']),
        encoding="utf-8",
    )
    store.put(ArtifactRef(kind="postprocess_edits", path=str(log_p)))

    inp = StageInput(
        job_id="job1", image_id="page_0",
        params=_scoring_params(threshold=0.5),
        artifacts=store, trace={},
    )
    out = evaluate_stage(inp)
    assert out.metrics.fields["evaluate.edits_total"] == 3


# --- registered name ----------------------------------------------------


def test_registered_under_canonical_name():
    from app.pipeline.registry import default_registry
    assert default_registry.resolve("evaluate") is evaluate_stage
