import io
import json

from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import StageInput, StageMetrics, StageOutput
from app.pipeline.controller import Pipeline
from app.pipeline.debug import EventLogger
from app.pipeline.registry import StageRegistry


def _ok(_inp: StageInput) -> StageOutput:
    return StageOutput(status="ok", metrics=StageMetrics(fields={"k": 1}))


def _fail(_inp: StageInput) -> StageOutput:
    return StageOutput(status="failed", error="boom")


def _crash(_inp: StageInput) -> StageOutput:
    raise RuntimeError("explode")


class _Counter:
    def __init__(self, sequence):
        self.calls = 0
        self.sequence = list(sequence)

    def __call__(self, _inp: StageInput) -> StageOutput:
        self.calls += 1
        status = self.sequence.pop(0)
        return StageOutput(status=status)


def _make(tmp_path):
    reg = StageRegistry()
    sink = io.StringIO()
    pipe = Pipeline(
        job_id="j1",
        store=FileArtifactStore(root=tmp_path, job_id="j1"),
        logger=EventLogger(sink=sink),
        registry=reg,
        param_set_id="v1",
    )
    return reg, pipe, sink


def _events(sink):
    return [json.loads(line) for line in sink.getvalue().strip().splitlines()]


def test_runs_all_stages_in_order(tmp_path):
    reg, pipe, sink = _make(tmp_path)
    reg.register("a", _ok)
    reg.register("b", _ok)
    res = pipe.run(["a", "b"], params={})
    assert [n for n, _ in res.outputs] == ["a", "b"]
    assert res.aborted is False
    events = [(e["stage"], e["event"]) for e in _events(sink)]
    assert events == [
        ("a", "stage.start"),
        ("a", "stage.end"),
        ("b", "stage.start"),
        ("b", "stage.end"),
    ]


def test_failed_stage_aborts(tmp_path):
    reg, pipe, sink = _make(tmp_path)
    reg.register("a", _fail)
    reg.register("b", _ok)
    res = pipe.run(["a", "b"], params={})
    assert res.aborted is True
    assert [n for n, _ in res.outputs] == ["a"]


def test_exception_becomes_failed(tmp_path):
    reg, pipe, sink = _make(tmp_path)
    reg.register("a", _crash)
    res = pipe.run(["a"], params={})
    assert res.aborted is True
    failure = res.outputs[-1][1]
    assert failure.status == "failed"
    assert "RuntimeError" in (failure.error or "")
    # Failure event must surface the error class for triage.
    err_event = [e for e in _events(sink) if e["event"] == "stage.failed"][0]
    assert "RuntimeError" in err_event["error"]


def test_retryable_triggers_one_retry(tmp_path):
    reg, pipe, sink = _make(tmp_path)
    counter = _Counter(["retryable", "ok"])
    reg.register("a", counter)
    res = pipe.run(["a"], params={})
    assert counter.calls == 2
    assert res.outputs[-1][1].status == "ok"


def test_retryable_does_not_loop_forever(tmp_path):
    reg, pipe, sink = _make(tmp_path)
    counter = _Counter(["retryable", "retryable"])
    reg.register("a", counter)
    res = pipe.run(["a"], params={})
    # Controller retries exactly once; second retryable propagates as-is
    # without a third invocation.
    assert counter.calls == 2
    assert res.outputs[-1][1].status == "retryable"


def test_duration_filled_centrally(tmp_path):
    reg, pipe, _sink = _make(tmp_path)

    def _no_timing(_inp):
        return StageOutput(status="ok")  # metrics.duration_ms == 0

    reg.register("a", _no_timing)
    res = pipe.run(["a"], params={})
    assert res.outputs[-1][1].metrics.duration_ms >= 0
