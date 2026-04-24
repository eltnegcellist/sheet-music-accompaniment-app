"""Stage I/O contracts shared by every pipeline stage.

A stage is a pure function `(StageInput) -> StageOutput`. Inputs carry the
job/page/trial identity, the resolved parameter set, a handle to previously
produced artifacts, and a tracing context. Outputs carry status, references
to new artifacts, structured metrics, and any warnings/errors.

Keeping the contract narrow lets the controller schedule, retry, and
short-circuit stages without knowing their internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

# Status semantics:
#   ok        - stage produced its expected output
#   retryable - failed but the controller may retry with adjusted params
#   failed    - terminal failure for this stage; do not retry
#   skipped   - intentionally not run (e.g. quality gate dropped this input)
StageStatus = Literal["ok", "retryable", "failed", "skipped"]

# A unique location in the job/page/trial hierarchy. Embedded in every
# log line so an operator can trace a single failure end-to-end.
TraceContext = Mapping[str, str]


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to a file produced by a stage.

    `kind` is a stable string (e.g. "musicxml", "binary_image", "omr_project")
    so downstream stages can look up artifacts without knowing the file path.
    """

    kind: str
    path: str
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class StageMetrics:
    """Numeric/categorical observations from a stage run.

    `fields` keys are namespaced by stage (e.g. "preprocess.staff_detection_rate")
    so they stay unique once aggregated into job-level reports.
    """

    duration_ms: int = 0
    cpu_ms: int | None = None
    fields: dict[str, float | int | str | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class StageInput:
    job_id: str
    image_id: str
    params: Mapping[str, Any]
    artifacts: "ArtifactStore"
    trace: TraceContext
    page_no: int | None = None


@dataclass
class StageOutput:
    status: StageStatus
    artifact_refs: list[ArtifactRef] = field(default_factory=list)
    metrics: StageMetrics = field(default_factory=StageMetrics)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


# Forward reference — implemented in `artifacts.py`. We declare the protocol
# shape here so contracts.py has no import-time dependency on the storage
# implementation, keeping the module a leaf in the dependency graph.
class ArtifactStore:  # pragma: no cover - structural typing only
    def put(self, ref: ArtifactRef) -> ArtifactRef: ...
    def get(self, kind: str) -> ArtifactRef | None: ...
    def list(self, kind: str | None = None) -> list[ArtifactRef]: ...
