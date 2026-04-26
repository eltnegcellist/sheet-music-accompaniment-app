"""High-level helpers that compose the pipeline for callers like /analyze.

This module owns the bridge between FastAPI handlers and the Pipeline so
`main.py` doesn't have to know about stage names, registries, or
artifact layout. It exposes one entry point per supported flow.
"""

from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from ..omr.audiveris_runner import OmrResult, run_audiveris
from .artifacts import FileArtifactStore
from .contracts import ArtifactRef
from .controller import Pipeline
from .debug import EventLogger
from .full_run import run_postprocess_and_evaluate
from .registry import default_registry
from .stages.omr import make_test_stage  # noqa: F401 — re-exported for tests
from . import stages as _stages  # noqa: F401 — populates default_registry

logger = logging.getLogger("pipeline")

AudiverisDriver = Callable[[Path, Path], OmrResult]


def run_omr_via_pipeline(
    pdf_path: Path,
    output_dir: Path,
    *,
    job_id: str | None = None,
    param_set_id: str = "v1_baseline",
    driver: AudiverisDriver = run_audiveris,
    params: Mapping[str, Any] | None = None,
) -> OmrResult:
    """Run the OMR stage end-to-end and return the legacy `OmrResult`.

    `output_dir` is honoured for backwards compatibility — Audiveris drops
    its working files there. The Pipeline's own artifacts live under it
    as a sub-tree so we don't grow yet another temp directory.

    When `params.postprocess.{rhythm_fix|voice_rebuild}.enabled` is set,
    the OMR's MusicXML is fed through the postprocess chain and the
    corrected version is returned in `OmrResult.music_xml`. Measure
    layouts and page sizes from the OMR remain untouched (the corrected
    XML reuses the same measure numbering so layout overlay still works).
    """
    job_id = job_id or f"job-{uuid.uuid4().hex[:12]}"
    artifacts_root = output_dir / "_pipeline"
    store = FileArtifactStore(root=artifacts_root, job_id=job_id)

    # Make the input PDF discoverable to the OMR stage via the standard
    # `input_pdf` artifact kind.
    store.put(ArtifactRef(kind="input_pdf", path=str(pdf_path)))

    # Capture the underlying OmrResult so we can return measure layouts /
    # page sizes too — those are used by the API response and aren't
    # serialised through the artifact store yet (separate ticket).
    captured: dict[str, OmrResult] = {}

    def _capturing_driver(pdf: Path, out_dir: Path) -> OmrResult:
        result = driver(pdf, out_dir)
        captured["last"] = result
        return result

    # Test-friendly: re-register the stage under a unique name so two
    # parallel calls don't fight over the global registry. This still
    # exercises the Pipeline path end-to-end.
    stage_name = f"omr.audiveris._call_{job_id}"
    default_registry.register(stage_name, make_test_stage(_capturing_driver))
    try:
        pipeline = Pipeline(
            job_id=job_id,
            store=store,
            logger=EventLogger(sink=io.StringIO(), logger=logger),
            param_set_id=param_set_id,
        )
        result = pipeline.run([stage_name], params={})
    finally:
        default_registry._stages.pop(stage_name, None)

    if result.aborted or "last" not in captured:
        # Surface the captured stage error verbatim — callers translate to HTTP.
        last_output = result.outputs[-1][1] if result.outputs else None
        msg = (last_output.error if last_output else None) or "Pipeline aborted"
        raise RuntimeError(msg)

    omr_result = captured["last"]
    if params is not None:
        omr_result = _apply_postprocess(omr_result, params)
    return omr_result


def _apply_postprocess(
    omr_result: OmrResult,
    params: Mapping[str, Any],
) -> OmrResult:
    """Run postprocess on `omr_result.music_xml` if params opt in.

    Returns a fresh `OmrResult` so the caller's reference to the OMR
    output stays intact for diffing/debug. Failures degrade silently:
    we keep the OMR XML and append a warning so the user knows
    postprocess didn't fire.
    """
    pp = (params.get("postprocess") or {}) if isinstance(params, Mapping) else {}
    fill = bool((pp.get("fill_measures") or {}).get("enabled"))
    rhythm = bool((pp.get("rhythm_fix") or {}).get("enabled"))
    voice = bool((pp.get("voice_rebuild") or {}).get("enabled"))
    pitch = bool((pp.get("pitch_fix") or {}).get("enabled"))
    if not (fill or rhythm or voice or pitch):
        return omr_result
    if not omr_result.music_xml:
        return omr_result

    rhythm_cfg = pp.get("rhythm_fix") or {}
    snap = rhythm_cfg.get("snap_durations") or [1, 2, 4, 8, 16]
    max_edits = int(rhythm_cfg.get("max_edits_per_measure", 4))

    run = run_postprocess_and_evaluate(
        omr_result.music_xml,
        fill_measures_enabled=fill,
        rhythm_fix_enabled=rhythm,
        voice_rebuild_enabled=voice,
        pitch_fix_enabled=pitch,
        snap_durations=list(snap),
        max_edits_per_measure=max_edits,
    )
    if run is None:
        # Postprocess couldn't parse — surface so the operator knows.
        return OmrResult(
            music_xml=omr_result.music_xml,
            measures=omr_result.measures,
            page_sizes=omr_result.page_sizes,
            warnings=[
                *omr_result.warnings,
                "postprocess could not be applied (parse failure); "
                "raw OMR output returned.",
            ],
        )

    extra_warnings: list[str] = []
    if run.edits_count > 0:
        extra_warnings.append(
            f"postprocess applied {run.edits_count} edit(s); "
            f"final_score={run.final_score:.3f}."
        )
    return OmrResult(
        music_xml=run.music_xml,
        measures=omr_result.measures,
        page_sizes=omr_result.page_sizes,
        warnings=[*omr_result.warnings, *extra_warnings],
    )
