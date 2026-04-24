"""End-to-end skeleton test: a 3-stage pipeline runs from start to finish.

This is the smallest test that exercises every public surface of the
Phase 0 skeleton (contracts, registry, controller, artifacts, logging).
If this test breaks the rest of S1 cannot proceed — keep it tight.
"""

import io
import json

from app.pipeline import (
    EventLogger,
    FileArtifactStore,
    Pipeline,
    StageInput,
    StageMetrics,
    StageOutput,
    StageRegistry,
)
from app.pipeline.contracts import ArtifactRef


def test_three_stage_pipeline_with_artifact_handoff(tmp_path):
    reg = StageRegistry()

    def stage_a(inp: StageInput) -> StageOutput:
        # Simulate writing a preprocessed image.
        p = inp.artifacts.path_for("preprocess", "binary.png")
        p.write_bytes(b"FAKE_PNG")
        ref = inp.artifacts.put(ArtifactRef(kind="binary_image", path=str(p)))
        return StageOutput(
            status="ok",
            artifact_refs=[ref],
            metrics=StageMetrics(fields={"preprocess.ok": True}),
        )

    def stage_b(inp: StageInput) -> StageOutput:
        ref = inp.artifacts.get("binary_image")
        assert ref is not None, "stage A should have produced a binary_image"
        # "OMR" output references the upstream artifact's bytes.
        size = len(open(ref.path, "rb").read())
        out_path = inp.artifacts.path_for("omr", "score.musicxml")
        out_path.write_text("<score-partwise/>")
        inp.artifacts.put(ArtifactRef(kind="musicxml", path=str(out_path)))
        return StageOutput(
            status="ok",
            metrics=StageMetrics(fields={"omr.input_bytes": size}),
        )

    def stage_c(inp: StageInput) -> StageOutput:
        # Final stage just confirms both upstream artifacts exist.
        assert inp.artifacts.get("binary_image") is not None
        assert inp.artifacts.get("musicxml") is not None
        return StageOutput(status="ok")

    reg.register("preprocess", stage_a)
    reg.register("omr", stage_b)
    reg.register("evaluate", stage_c)

    sink = io.StringIO()
    pipe = Pipeline(
        job_id="job-skeleton",
        store=FileArtifactStore(root=tmp_path, job_id="job-skeleton"),
        logger=EventLogger(sink=sink),
        registry=reg,
        param_set_id="v1_baseline",
    )

    res = pipe.run(["preprocess", "omr", "evaluate"], params={"foo": "bar"})

    assert res.aborted is False
    assert [name for name, _ in res.outputs] == ["preprocess", "omr", "evaluate"]
    assert all(out.status == "ok" for _, out in res.outputs)

    events = [json.loads(line) for line in sink.getvalue().strip().splitlines()]
    # 3 stages * (start + end) = 6 events.
    assert len(events) == 6
    # All events carry the job_id and param_set_id for triage.
    assert all(e["job_id"] == "job-skeleton" for e in events)
    assert all(e.get("param_set_id") == "v1_baseline" for e in events)

    # Files were laid out under <root>/<job_id>/<kind>/<name>.
    assert (tmp_path / "job-skeleton" / "preprocess" / "binary.png").exists()
    assert (tmp_path / "job-skeleton" / "omr" / "score.musicxml").exists()
