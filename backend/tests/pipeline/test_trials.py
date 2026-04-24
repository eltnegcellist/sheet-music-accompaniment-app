"""Tests for trial expansion + concurrent runner.

We verify three concerns:
  1. Matrix expansion produces deterministic plans with sane ids.
  2. Concurrent execution respects the parallelism cap.
  3. Stray exceptions become `failed` results, not propagated tracebacks.
"""

import threading
import time

import pytest

from app.pipeline.contracts import StageOutput
from app.pipeline.trials import (
    TrialPlan,
    expand_matrix,
    run_trials,
    _set_dotted,
)


# --- expand_matrix -------------------------------------------------------


def test_no_matrix_yields_single_baseline_trial():
    plans = expand_matrix({"preprocess": {"binarize": {"k": 0.20}}}, matrix=None)
    assert len(plans) == 1
    assert plans[0].trial_id == "t0"
    assert plans[0].params == {"preprocess": {"binarize": {"k": 0.20}}}


def test_empty_matrix_treated_as_no_matrix():
    plans = expand_matrix({"a": 1}, matrix={})
    assert len(plans) == 1


def test_matrix_cartesian_product():
    plans = expand_matrix(
        {"preprocess": {"binarize": {"method": "sauvola", "k": 0.2}}},
        matrix={
            "preprocess.binarize.method": ["sauvola", "adaptive_mean"],
            "preprocess.binarize.k": [0.15, 0.20, 0.25],
        },
    )
    assert len(plans) == 2 * 3
    # Coordinates are baked into the trial id so logs are self-explanatory.
    assert all("preprocess_binarize_method=" in p.trial_id for p in plans)
    # Children own their values — every plan's k matches one of the matrix entries.
    assert {p.params["preprocess"]["binarize"]["k"] for p in plans} == {0.15, 0.20, 0.25}


def test_matrix_does_not_mutate_base_params():
    base = {"preprocess": {"binarize": {"k": 0.2}}}
    expand_matrix(base, matrix={"preprocess.binarize.k": [0.1, 0.2]})
    assert base == {"preprocess": {"binarize": {"k": 0.2}}}


def test_set_dotted_creates_intermediate_dicts():
    d: dict = {}
    _set_dotted(d, "a.b.c", 42)
    assert d == {"a": {"b": {"c": 42}}}


def test_set_dotted_rejects_non_dict_intermediate():
    d = {"a": 1}
    with pytest.raises(ValueError, match="not a dict"):
        _set_dotted(d, "a.b", 2)


# --- run_trials ----------------------------------------------------------


def test_runs_each_plan_once():
    plans = expand_matrix({}, matrix={"x": [1, 2, 3]})
    seen: list[str] = []
    lock = threading.Lock()

    def invoke(plan: TrialPlan) -> StageOutput:
        with lock:
            seen.append(plan.trial_id)
        return StageOutput(status="ok")

    report = run_trials(plans, invoke, max_concurrent=2)
    assert {r.plan.trial_id for r in report.results} == {p.trial_id for p in plans}
    assert sorted(seen) == sorted(p.trial_id for p in plans)


def test_results_sorted_by_plan_order_for_determinism():
    plans = expand_matrix({}, matrix={"x": [1, 2, 3, 4]})

    def invoke(plan: TrialPlan) -> StageOutput:
        # Make later plans finish first to prove the runner re-sorts.
        time.sleep(0.001 * (4 - int(plan.params["x"])))
        return StageOutput(status="ok")

    report = run_trials(plans, invoke, max_concurrent=4)
    ids = [r.plan.trial_id for r in report.results]
    assert ids == [p.trial_id for p in plans]


def test_concurrency_cap_is_respected():
    cap = 2
    plans = expand_matrix({}, matrix={"x": list(range(6))})
    in_flight = 0
    peak = 0
    lock = threading.Lock()

    def invoke(_plan: TrialPlan) -> StageOutput:
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.02)
        with lock:
            in_flight -= 1
        return StageOutput(status="ok")

    report = run_trials(plans, invoke, max_concurrent=cap)
    assert len(report.results) == 6
    assert peak <= cap, f"Concurrency cap {cap} violated; peak={peak}"


def test_invoke_exception_becomes_failed_result():
    plans = expand_matrix({}, matrix={"x": [1, 2]})

    def invoke(plan: TrialPlan) -> StageOutput:
        if plan.params["x"] == 1:
            raise RuntimeError("boom")
        return StageOutput(status="ok")

    report = run_trials(plans, invoke, max_concurrent=1)
    assert {r.output.status for r in report.results} == {"ok", "failed"}
    failed = next(r for r in report.results if r.output.status == "failed")
    assert "RuntimeError" in (failed.output.error or "")


def test_max_concurrent_must_be_positive():
    with pytest.raises(ValueError):
        run_trials([], invoke=lambda p: StageOutput(status="ok"), max_concurrent=0)


def test_empty_plans_returns_empty_report():
    report = run_trials([], invoke=lambda p: StageOutput(status="ok"), max_concurrent=2)
    assert report.results == []


def test_report_best_picks_highest_score():
    plans = expand_matrix({}, matrix={"x": [1, 2, 3]})

    def invoke(plan: TrialPlan) -> StageOutput:
        # Encode a fake score in the metrics for the test's selection key.
        out = StageOutput(status="ok")
        out.metrics.fields["score"] = float(plan.params["x"])
        return out

    report = run_trials(plans, invoke, max_concurrent=2)
    best = report.best(key=lambda r: r.output.metrics.fields["score"])
    assert best is not None
    assert best.plan.params["x"] == 3
