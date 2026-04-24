"""Trial expansion + concurrent execution for the OMR stage.

Phase 2-2 plan: take a parameter matrix and produce one Trial per cell.
This module owns the matrix -> trial id mapping and a thread-pooled
runner so concurrency is bounded (Audiveris is JVM-heavy; we cap how
many can run at once).
"""

from __future__ import annotations

import concurrent.futures
import copy
import itertools
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from .contracts import StageInput, StageOutput


@dataclass(frozen=True)
class TrialPlan:
    """A single trial = one parameter variant + a stable id."""

    trial_id: str
    params: Mapping[str, Any]


def _set_dotted(d: dict, dotted: str, value: Any) -> None:
    """Mutate `d` in place: set the nested key `a.b.c` to `value`.

    Intermediate dicts are created as needed; non-dict intermediates are
    rejected with ValueError so we don't silently overwrite scalars.
    """
    parts = dotted.split(".")
    cursor = d
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if nxt is None:
            cursor[part] = {}
            cursor = cursor[part]
        elif isinstance(nxt, dict):
            cursor = nxt
        else:
            raise ValueError(f"Cannot set {dotted}: {part} is not a dict")
    cursor[parts[-1]] = value


def expand_matrix(
    base_params: Mapping[str, Any],
    matrix: Mapping[str, list[Any]] | None,
) -> list[TrialPlan]:
    """Expand a `{key: [values...]}` matrix into one TrialPlan per cell.

    Empty / missing matrix collapses to a single trial mirroring the base
    params — that's also the right behaviour when multi_trial.enabled is False.
    Trial ids are derived from the matrix coordinate so they're stable
    across runs and meaningful in logs.
    """
    if not matrix:
        return [TrialPlan(trial_id="t0", params=copy.deepcopy(dict(base_params)))]

    keys = sorted(matrix.keys())
    value_lists = [matrix[k] for k in keys]
    plans: list[TrialPlan] = []
    for idx, combo in enumerate(itertools.product(*value_lists)):
        variant = copy.deepcopy(dict(base_params))
        coord_parts: list[str] = []
        for key, value in zip(keys, combo):
            _set_dotted(variant, key, value)
            coord_parts.append(f"{key.replace('.', '_')}={value}")
        plans.append(
            TrialPlan(trial_id=f"t{idx}_" + "_".join(coord_parts), params=variant)
        )
    return plans


@dataclass
class TrialResult:
    plan: TrialPlan
    output: StageOutput
    duration_ms: int = 0
    error: str | None = None


@dataclass
class TrialRunReport:
    results: list[TrialResult] = field(default_factory=list)

    def ok_results(self) -> list[TrialResult]:
        return [r for r in self.results if r.output.status == "ok"]

    def best(self, key: Callable[[TrialResult], Any]) -> TrialResult | None:
        oks = self.ok_results()
        return max(oks, key=key) if oks else None


def run_trials(
    plans: Iterable[TrialPlan],
    invoke: Callable[[TrialPlan], StageOutput],
    *,
    max_concurrent: int,
) -> TrialRunReport:
    """Run trials concurrently with a hard cap on parallelism.

    The cap is enforced with a semaphore that shadows the executor's
    queue, so we never have more than `max_concurrent` JVMs alive even
    if more trials are pending in the executor backlog.
    """
    if max_concurrent < 1:
        raise ValueError("max_concurrent must be >= 1")

    plans = list(plans)
    sem = threading.Semaphore(max_concurrent)
    report = TrialRunReport()

    def _wrapped(plan: TrialPlan) -> TrialResult:
        with sem:
            try:
                out = invoke(plan)
                return TrialResult(plan=plan, output=out)
            except Exception as exc:  # noqa: BLE001
                # Translate stray exceptions into a failed StageOutput so the
                # report has a uniform shape — callers shouldn't have to
                # special-case "the runner threw" vs "the stage returned failed".
                return TrialResult(
                    plan=plan,
                    output=StageOutput(status="failed", error=f"{type(exc).__name__}: {exc}"),
                    error=str(exc),
                )

    if not plans:
        return report

    # We use a thread pool because each invoke() is expected to spawn a
    # subprocess (Audiveris) — threads sit idle waiting on Popen, leaving
    # CPU free for the JVM. Process pool would be wasteful and break
    # the in-memory artifact store.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as ex:
        futures = [ex.submit(_wrapped, p) for p in plans]
        for fut in concurrent.futures.as_completed(futures):
            report.results.append(fut.result())

    # Stable order in the report matters for determinism tests.
    plan_index = {p.trial_id: i for i, p in enumerate(plans)}
    report.results.sort(key=lambda r: plan_index[r.plan.trial_id])
    return report


def make_invoke_via_stage(
    stage_fn: Callable[[StageInput], StageOutput],
    inp_factory: Callable[[TrialPlan], StageInput],
) -> Callable[[TrialPlan], StageOutput]:
    """Adapter: turn a (StageInput) -> StageOutput stage into a (TrialPlan) -> StageOutput callable."""

    def _invoke(plan: TrialPlan) -> StageOutput:
        return stage_fn(inp_factory(plan))

    return _invoke
