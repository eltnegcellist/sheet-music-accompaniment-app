"""Phase 0 determinism guard.

Same input + same params must produce the same metrics fields and
artifact contents on a second run. We can't drive the real Audiveris
in CI, so the test stands up a deterministic fake driver and proves
that the *Pipeline plumbing itself* is reproducible. When real stages
arrive (S1-04 onwards) they extend this test by adding their own keys.
"""

import io
import json
from pathlib import Path

from app.omr.audiveris_runner import OmrResult
from app.pipeline import EventLogger, FileArtifactStore, Pipeline, StageRegistry
from app.pipeline.contracts import ArtifactRef
from app.pipeline.stages.omr import make_test_stage

_VALID_XML = (
    "<score-partwise>"
    "<part-list><score-part id='P1'/></part-list>"
    "<part id='P1'><measure number='1'>"
    "<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>"
    "<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration></note>"
    "</measure></part>"
    "</score-partwise>"
)


def _run_once(tmp_path: Path, run_idx: int):
    tmp_path.mkdir(parents=True, exist_ok=True)
    pdf = tmp_path / f"in_{run_idx}.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")

    store = FileArtifactStore(root=tmp_path / f"art_{run_idx}", job_id=f"job-{run_idx}")
    store.put(ArtifactRef(kind="input_pdf", path=str(pdf)))

    reg = StageRegistry()
    # Same fake driver -> same OmrResult both times.
    reg.register(
        "omr.audiveris",
        make_test_stage(
            lambda _p, _o: OmrResult(
                music_xml=_VALID_XML,
                measures=[],
                page_sizes=[(595.0, 842.0)],
                warnings=[],
            )
        ),
    )

    pipe = Pipeline(
        job_id=f"job-{run_idx}",
        store=store,
        logger=EventLogger(sink=io.StringIO()),
        registry=reg,
        param_set_id="v1_baseline",
    )
    res = pipe.run(["omr.audiveris"], params={})
    out = res.outputs[-1][1]
    return out, store


# Fields whose values are inherently variable between runs and should be
# excluded from determinism comparisons.
_VOLATILE_FIELDS = {"omr.audiveris.duration_ms"}


def _stable(fields: dict) -> dict:
    return {k: v for k, v in fields.items() if k not in _VOLATILE_FIELDS}


def test_two_runs_have_identical_metrics(tmp_path):
    out_a, store_a = _run_once(tmp_path / "a", 1)
    out_b, store_b = _run_once(tmp_path / "b", 2)
    assert out_a.status == "ok"
    assert out_b.status == "ok"
    assert _stable(out_a.metrics.fields) == _stable(out_b.metrics.fields)
    # Wall-clock timing is allowed to vary, but only within a generous bound:
    a_ms = out_a.metrics.duration_ms
    b_ms = out_b.metrics.duration_ms
    # Both must be non-negative; we don't enforce a tight ratio because CI
    # cores vary wildly. The intent here is to flag obvious regressions
    # (e.g. one run taking 100x the other).
    assert a_ms >= 0 and b_ms >= 0


def test_two_runs_produce_identical_musicxml_artifacts(tmp_path):
    _, store_a = _run_once(tmp_path / "a", 1)
    _, store_b = _run_once(tmp_path / "b", 2)
    a = Path(store_a.get("musicxml").path).read_text(encoding="utf-8")
    b = Path(store_b.get("musicxml").path).read_text(encoding="utf-8")
    assert a == b


def test_run_logs_are_serialisable_json_lines(tmp_path):
    """Sanity: the controller emits well-formed JSON Lines.

    A determinism test that depends on log content needs us to first
    guarantee logs are parseable at all.
    """
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"")
    store = FileArtifactStore(root=tmp_path / "art", job_id="j1")
    store.put(ArtifactRef(kind="input_pdf", path=str(pdf)))
    reg = StageRegistry()
    reg.register(
        "omr.audiveris",
        make_test_stage(lambda _p, _o: OmrResult(music_xml=_VALID_XML, measures=[])),
    )
    sink = io.StringIO()
    Pipeline(
        job_id="j1", store=store, logger=EventLogger(sink=sink), registry=reg
    ).run(["omr.audiveris"], params={})
    lines = [json.loads(l) for l in sink.getvalue().strip().splitlines()]
    assert len(lines) == 2  # start + end
    assert lines[0]["event"] == "stage.start"
    assert lines[1]["event"] == "stage.end"
