"""Pipeline controller — runs a stage list end-to-end for a job.

This first cut keeps the controller deliberately simple:
  * stages run sequentially in the given order
  * each stage gets a fresh `StageInput` referencing the same store
  * `retryable` triggers a single retry with `params.retry_overrides`
  * `failed` short-circuits the rest of the run

Trial-level fan-out (multi-trial) is added in a later commit (S1-05) on
top of this foundation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .artifacts import FileArtifactStore
from .contracts import StageInput, StageOutput
from .debug import EventLogger, StructuredEvent, now_iso
from .registry import StageFn, StageRegistry, default_registry


@dataclass
class StageStep:
    """One entry in the pipeline plan: which stage to run, with what name."""

    name: str
    fn: StageFn


@dataclass
class PipelineResult:
    job_id: str
    outputs: list[tuple[str, StageOutput]] = field(default_factory=list)
    aborted: bool = False

    def status_for(self, stage: str) -> str | None:
        for name, out in self.outputs:
            if name == stage:
                return out.status
        return None


@dataclass
class Pipeline:
    """Sequential stage runner with retry-on-retryable.

    The controller is the only object that knows about wall-clock timing
    and structured logging — stages stay focused on their domain.
    """

    job_id: str
    store: FileArtifactStore
    logger: EventLogger
    registry: StageRegistry = field(default_factory=lambda: default_registry)
    param_set_id: str | None = None

    def plan(self, stage_names: Iterable[str]) -> list[StageStep]:
        return [StageStep(name=n, fn=self.registry.resolve(n)) for n in stage_names]

    def run(
        self,
        stage_names: Iterable[str],
        params: Mapping[str, Any],
        image_id: str = "page_0",
        page_no: int | None = None,
    ) -> PipelineResult:
        steps = self.plan(stage_names)
        result = PipelineResult(job_id=self.job_id)

        for step in steps:
            out = self._run_step(step, params, image_id, page_no, retry=False)
            if out.status == "retryable":
                # One retry only — controller-level. Stages can request more
                # via their own internal logic if needed.
                out = self._run_step(step, params, image_id, page_no, retry=True)
            result.outputs.append((step.name, out))
            if out.status == "failed":
                result.aborted = True
                return result
        return result

    def _run_step(
        self,
        step: StageStep,
        params: Mapping[str, Any],
        image_id: str,
        page_no: int | None,
        retry: bool,
    ) -> StageOutput:
        trace = {
            "job_id": self.job_id,
            "stage": step.name,
            "image_id": image_id,
            "retry": "1" if retry else "0",
        }
        stage_input = StageInput(
            job_id=self.job_id,
            image_id=image_id,
            page_no=page_no,
            params=params,
            artifacts=self.store,
            trace=trace,
        )
        self._emit("stage.start", step.name, "ok", duration_ms=None, retry=retry)
        t0 = time.monotonic()
        try:
            out = step.fn(stage_input)
        except Exception as exc:  # noqa: BLE001 — stages are user code; isolate failures.
            duration_ms = int((time.monotonic() - t0) * 1000)
            self._emit(
                "stage.failed",
                step.name,
                "failed",
                duration_ms=duration_ms,
                error=f"{type(exc).__name__}: {exc}",
                retry=retry,
            )
            return StageOutput(status="failed", error=f"{type(exc).__name__}: {exc}")

        duration_ms = int((time.monotonic() - t0) * 1000)
        # Stages can omit the duration; fill it in centrally so reports are uniform.
        if out.metrics.duration_ms == 0:
            out.metrics.duration_ms = duration_ms

        event = "stage.end" if out.status != "retryable" else "stage.retry"
        self._emit(
            event,
            step.name,
            out.status,
            duration_ms=duration_ms,
            metrics=out.metrics.fields or None,
            warnings=out.warnings or None,
            error=out.error,
            retry=retry,
        )
        return out

    def _emit(
        self,
        event: str,
        stage: str,
        status: str,
        *,
        duration_ms: int | None,
        retry: bool,
        metrics: Mapping[str, Any] | None = None,
        warnings: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        self.logger.emit(
            StructuredEvent(
                ts=now_iso(),
                event=event,
                job_id=self.job_id,
                stage=stage,
                status=status,
                param_set_id=self.param_set_id,
                duration_ms=duration_ms,
                metrics=dict(metrics) if metrics else None,
                warnings=warnings,
                error=error,
            )
        )
