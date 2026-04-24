"""OMR stage — wraps the existing Audiveris driver in the Pipeline contract.

Phase 2 plan: keep the CLI exactly as the legacy `audiveris_runner` had it
(`-batch -export -output ...`). We do not introduce `-transcribe` / `-save`
here because both have been observed to trigger NPEs in production.

This wrapper's job is:
  1. Locate the input PDF (from a known artifact kind or `params`).
  2. Hand a per-trial output directory to the Audiveris driver.
  3. Surface the resulting MusicXML / .omr / warnings as artifacts.
  4. Translate Audiveris errors into `StageOutput.status`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ...omr.audiveris_runner import (
    AudiverisError,
    OmrResult,
    run_audiveris,
)
from ..contracts import (
    ArtifactRef,
    StageInput,
    StageMetrics,
    StageOutput,
)
from ..registry import register

# Tests inject a fake driver instead of the real Audiveris CLI. Production
# stays on `run_audiveris`; CI never touches the JVM.
AudiverisDriver = Callable[[Path, Path], OmrResult]


def _input_pdf_path(inp: StageInput) -> Path:
    """Resolve the source PDF for this stage run.

    Order of precedence:
      1. An artifact with kind ``input_pdf`` (preferred — set by /analyze).
      2. ``params.omr.input_pdf`` (escape hatch for tests / replays).
    """
    ref = inp.artifacts.get("input_pdf")
    if ref is not None:
        return Path(ref.path)
    pdf_path = inp.params.get("omr", {}).get("input_pdf")
    if pdf_path:
        return Path(pdf_path)
    raise FileNotFoundError(
        "OMR stage requires an `input_pdf` artifact or "
        "`params.omr.input_pdf` to be set."
    )


def _run_with(
    inp: StageInput,
    driver: AudiverisDriver,
) -> StageOutput:
    try:
        pdf_path = _input_pdf_path(inp)
    except FileNotFoundError as exc:
        return StageOutput(status="failed", error=f"FileNotFoundError: {exc}")

    output_dir = Path(inp.artifacts.path_for("omr", "audiveris_out"))
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = driver(pdf_path, output_dir)
    except AudiverisError as exc:
        # Audiveris produced no usable output. We surface the failure as
        # `failed` (not `retryable`): retrying with the same params would
        # waste 30 minutes of wall clock.
        return StageOutput(status="failed", error=f"AudiverisError: {exc}")
    except FileNotFoundError as exc:
        return StageOutput(status="failed", error=f"FileNotFoundError: {exc}")

    refs: list[ArtifactRef] = []
    if result.music_xml:
        xml_path = inp.artifacts.path_for("omr", "score.musicxml")
        xml_path.write_text(result.music_xml, encoding="utf-8")
        refs.append(inp.artifacts.put(ArtifactRef(kind="musicxml", path=str(xml_path))))

    measure_count = len(result.measures)
    metrics = StageMetrics(
        fields={
            "omr.audiveris.valid_xml": bool(result.music_xml),
            "omr.audiveris.measure_count": measure_count,
            "omr.audiveris.page_count": len(result.page_sizes),
            "omr.audiveris.warnings": len(result.warnings),
        }
    )

    # We treat "no MusicXML emitted" as failed. This is the same boundary
    # the legacy code raised AudiverisError for, just translated to the
    # Pipeline status vocabulary.
    if not result.music_xml:
        return StageOutput(
            status="failed",
            metrics=metrics,
            warnings=list(result.warnings),
            error="Audiveris produced no MusicXML",
        )

    return StageOutput(
        status="ok",
        artifact_refs=refs,
        metrics=metrics,
        warnings=list(result.warnings),
    )


@register("omr.audiveris")
def audiveris_stage(inp: StageInput) -> StageOutput:
    """Default OMR stage entry — uses the real Audiveris CLI."""
    return _run_with(inp, driver=run_audiveris)


def make_test_stage(driver: AudiverisDriver) -> Callable[[StageInput], StageOutput]:
    """Test helper: build a stage callable wired to a fake driver."""

    def _stage(inp: StageInput) -> StageOutput:
        return _run_with(inp, driver=driver)

    return _stage
