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
from ..validators import validate_musicxml_shape

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

    # Run the broken-XML detector even when the driver returned ok — the
    # whole point is to catch the cases where Audiveris swallowed a failure
    # and emitted a structurally-empty document.
    report = validate_musicxml_shape(result.music_xml)

    metrics = StageMetrics(
        fields={
            "omr.audiveris.valid_xml": (not report.is_broken) and bool(result.music_xml),
            "omr.audiveris.measure_count": report.measure_count or len(result.measures),
            "omr.audiveris.note_count": report.note_count,
            "omr.audiveris.avg_notes_per_measure": round(
                report.avg_notes_per_measure, 3
            ),
            "omr.audiveris.part_count": report.part_count,
            "omr.audiveris.empty_parts": report.empty_parts,
            "omr.audiveris.page_count": len(result.page_sizes),
            "omr.audiveris.warnings": len(result.warnings),
        }
    )

    # Surface the validator's first-issue code for log aggregation. Only
    # one code is recorded per stage run — additional codes go into warnings.
    if report.issues:
        metrics.fields["omr.audiveris.failure_class"] = f"omr.{report.issues[0].code}"

    if not result.music_xml:
        # Same boundary as the legacy code, mapped to Pipeline vocabulary.
        return StageOutput(
            status="failed",
            metrics=metrics,
            warnings=list(result.warnings),
            error="Audiveris produced no MusicXML",
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
    return _run_with(inp, driver=run_audiveris)


def make_test_stage(driver: AudiverisDriver) -> Callable[[StageInput], StageOutput]:
    """Test helper: build a stage callable wired to a fake driver."""

    def _stage(inp: StageInput) -> StageOutput:
        return _run_with(inp, driver=driver)

    return _stage
