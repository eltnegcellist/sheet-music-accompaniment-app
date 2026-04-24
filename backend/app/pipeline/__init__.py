"""Pipeline framework for the OMR accuracy improvements.

This package is intentionally thin: it provides stage contracts and the
controller that runs them. Concrete stages live in `app.pipeline.stages.*`.
"""

from .contracts import (
    ArtifactRef,
    ArtifactStore,
    StageInput,
    StageMetrics,
    StageOutput,
    StageStatus,
    TraceContext,
)

__all__ = [
    "ArtifactRef",
    "ArtifactStore",
    "StageInput",
    "StageMetrics",
    "StageOutput",
    "StageStatus",
    "TraceContext",
]
