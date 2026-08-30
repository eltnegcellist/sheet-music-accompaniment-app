"""OMR stage — wraps an OMR driver in the Pipeline contract.

Phase 2 plan: keep the CLI exactly as the legacy `audiveris_runner` had it
(`-batch -export -output ...`). We do not introduce `-transcribe` / `-save`
here because both have been observed to trigger NPEs in production.

This wrapper's job is:
  1. Locate the input PDF (from a known artifact kind or `params`).
  2. Hand a per-trial output directory to the configured OMR driver.
  3. Surface the resulting MusicXML / .omr / warnings as artifacts.
  4. Translate OMR errors into `StageOutput.status`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...omr.audiveris_runner import run_audiveris
from ...omr.homr_runner import run_homr
from ...omr.result import OmrError, OmrResult
from ..contracts import (
    ArtifactRef,
    StageInput,
    StageMetrics,
    StageOutput,
)
from ..registry import register
from ..validators import validate_musicxml_shape

# Tests inject a fake driver instead of a real OMR CLI.
OmrDriver = Callable[[Path, Path], OmrResult]


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
    driver: OmrDriver,
    *,
    engine: str,
) -> StageOutput:
    try:
        pdf_path = _input_pdf_path(inp)
    except FileNotFoundError as exc:
        return StageOutput(status="failed", error=f"FileNotFoundError: {exc}")

    output_dir = Path(inp.artifacts.path_for("omr", f"{engine}_out"))
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = driver(pdf_path, output_dir)
    except OmrError as exc:
        # The engine produced no usable output. We surface the failure as
        # `failed` (not `retryable`): retrying with the same params would
        # waste substantial wall clock time.
        return StageOutput(status="failed", error=f"{type(exc).__name__}: {exc}")
    except FileNotFoundError as exc:
        return StageOutput(status="failed", error=f"FileNotFoundError: {exc}")

    refs: list[ArtifactRef] = []
    if result.music_xml:
        xml_path = inp.artifacts.path_for("omr", "score.musicxml")
        xml_path.write_text(result.music_xml, encoding="utf-8")
        refs.append(inp.artifacts.put(ArtifactRef(kind="musicxml", path=str(xml_path))))

    # Run the broken-XML detector even when the driver returned ok — the
    # whole point is to catch the cases where Audiveris swallowed a failure
    # and emitted a structurally-empty document.
    report = validate_musicxml_shape(result.music_xml)

    metric_prefix = f"omr.{engine}"
    metrics = StageMetrics(
        fields={
            f"{metric_prefix}.valid_xml": (not report.is_broken)
            and bool(result.music_xml),
            f"{metric_prefix}.measure_count": report.measure_count
            or len(result.measures),
            f"{metric_prefix}.note_count": report.note_count,
            f"{metric_prefix}.avg_notes_per_measure": round(
                report.avg_notes_per_measure, 3
            ),
            f"{metric_prefix}.part_count": report.part_count,
            f"{metric_prefix}.empty_parts": report.empty_parts,
            f"{metric_prefix}.page_count": len(result.page_sizes),
            f"{metric_prefix}.warnings": len(result.warnings),
        }
    )

    # Surface the validator's first-issue code for log aggregation. Only
    # one code is recorded per stage run — additional codes go into warnings.
    if report.issues:
        metrics.fields[f"{metric_prefix}.failure_class"] = (
            f"omr.{report.issues[0].code}"
        )

    if not result.music_xml:
        # Same boundary as the legacy code, mapped to Pipeline vocabulary.
        return StageOutput(
            status="failed",
            metrics=metrics,
            warnings=list(result.warnings),
            error=f"{engine} produced no MusicXML",
        )

    if report.is_broken:
        codes = ", ".join(i.code for i in report.issues)
        return StageOutput(
            status="failed",
            artifact_refs=refs,
            metrics=metrics,
            warnings=[*result.warnings, *(i.detail for i in report.issues)],
            error=f"MusicXML shape invalid: {codes}",
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
    return _run_with(inp, driver=run_audiveris, engine="audiveris")


@register("omr.homr")
def homr_stage(inp: StageInput) -> StageOutput:
    """Experimental OMR stage entry — uses homr with resolved defaults."""
    config = inp.params.get("omr", {}).get("homr", {})

    def driver(pdf: Path, output_dir: Path) -> OmrResult:
        return run_homr(
            pdf,
            output_dir,
            dpi=int(config.get("dpi", 300)),
            timeout_sec=int(config.get("timeout_sec", 3600)),
            coreml_encoder=config.get("coreml_encoder"),
        )

    return _run_with(inp, driver=driver, engine="homr")


def make_test_stage(
    driver: OmrDriver,
    *,
    engine: str = "audiveris",
) -> Callable[[StageInput], StageOutput]:
    """Test helper: build a stage callable wired to a fake driver."""

    def _stage(inp: StageInput) -> StageOutput:
        return _run_with(inp, driver=driver, engine=engine)

    return _stage
