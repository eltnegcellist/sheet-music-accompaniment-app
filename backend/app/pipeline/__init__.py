"""Pipeline framework for the OMR accuracy improvements.

This package is intentionally thin: it provides stage contracts and the
controller that runs them. Concrete stages live in `app.pipeline.stages.*`.
"""

from .artifacts import FileArtifactStore
from .contracts import (
    ArtifactRef,
    ArtifactStore,
    StageInput,
    StageMetrics,
    StageOutput,
    StageStatus,
    TraceContext,
)
from .controller import Pipeline, PipelineResult, StageStep
from .debug import EventLogger, StructuredEvent, is_debug_enabled, now_iso
from .registry import StageFn, StageRegistry, default_registry, register

__all__ = [
    "ArtifactRef",
    "ArtifactStore",
    "EventLogger",
    "FileArtifactStore",
    "Pipeline",
    "PipelineResult",
    "StageFn",
    "StageInput",
    "StageMetrics",
    "StageOutput",
    "StageRegistry",
    "StageStatus",
    "StageStep",
    "StructuredEvent",
    "TraceContext",
    "default_registry",
    "is_debug_enabled",
    "now_iso",
    "register",
]
