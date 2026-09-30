"""Select an OMR engine from resolved pipeline parameters."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path
from typing import Any

from .audiveris_runner import run_audiveris_chunked
from .homr_runner import run_homr
from .hybrid_runner import run_hybrid
from .result import OmrResult

OmrDriver = Callable[[Path, Path], OmrResult]


def configured_engine(params: Mapping[str, Any] | None) -> str:
    """Return the configured OMR engine; OMR_ENGINE overrides YAML."""
    configured = os.environ.get("OMR_ENGINE")
    if configured is None and isinstance(params, Mapping):
        omr = params.get("omr") or {}
        if isinstance(omr, Mapping):
            configured = str(omr.get("engine") or "audiveris")
    engine = (configured or "audiveris").strip().lower()
    if engine not in {"audiveris", "homr", "hybrid"}:
        raise ValueError(f"Unsupported OMR engine: {engine}")
    return engine


def configured_driver(params: Mapping[str, Any] | None) -> OmrDriver:
    """Build the driver for the selected engine and its resolved options."""
    engine = configured_engine(params)
    if engine == "audiveris":
        return run_audiveris_chunked

    homr_config: Mapping[str, Any] = {}
    if isinstance(params, Mapping):
        omr = params.get("omr") or {}
        if isinstance(omr, Mapping) and isinstance(omr.get("homr"), Mapping):
            homr_config = omr["homr"]

    if engine == "homr":
        return partial(
            run_homr,
            dpi=int(homr_config.get("dpi", 300)),
            timeout_sec=int(homr_config.get("timeout_sec", 3600)),
            coreml_encoder=homr_config.get("coreml_encoder"),
        )

    hybrid_config: Mapping[str, Any] = {}
    if isinstance(params, Mapping):
        omr = params.get("omr") or {}
        if isinstance(omr, Mapping) and isinstance(omr.get("hybrid"), Mapping):
            hybrid_config = omr["hybrid"]

    return partial(
        run_hybrid,
        homr_dpi=int(homr_config.get("dpi", 300)),
        homr_timeout_sec=int(homr_config.get("timeout_sec", 3600)),
        homr_coreml_encoder=homr_config.get("coreml_encoder"),
        duration_floor=float(hybrid_config.get("duration_floor", 0.75)),
        strong_duration_gain=float(
            hybrid_config.get("strong_duration_gain", 0.12)
        ),
        minimum_score_gain=float(hybrid_config.get("minimum_score_gain", 0.03)),
        fragmentation_part_limit=int(
            hybrid_config.get("fragmentation_part_limit", 3)
        ),
        minimum_safe_pitch_rate=float(
            hybrid_config.get("minimum_safe_pitch_rate", 0.50)
        ),
        minimum_safe_pitch_notes=int(
            hybrid_config.get("minimum_safe_pitch_notes", 8)
        ),
    )
