"""Evaluate stage — Phase 4 entry point.

Reads the latest postprocess MusicXML (or the OMR output as a fallback),
computes the 6-indicator ScoreCard, weights it into a final_score, and
records the resulting decision into `chosen.json` for warm-start replay.

A multi-trial Job will run this stage once per trial; aggregation across
trials happens at the Job level (S2-04-d) — the stage itself is single-
trial.
"""

from __future__ import annotations

import json
from pathlib import Path

from music21 import stream

from ..contracts import (
    ArtifactRef,
    StageInput,
    StageMetrics,
    StageOutput,
)
from ..evaluate import (
    ScoreCard,
    final_score,
    score_musicxml,
    validate_weights,
)
from ..registry import register
from .postprocess import parse_musicxml


def _resolve_xml(inp: StageInput) -> str | None:
    """Use the latest postprocess output if present, else the raw OMR XML."""
    for kind in ("postprocess_musicxml", "musicxml"):
        ref = inp.artifacts.get(kind)
        if ref is not None:
            return Path(ref.path).read_text(encoding="utf-8")
    return None


def _count_edits(inp: StageInput) -> int:
    """Sum the line counts of every postprocess edit log."""
    total = 0
    for kind in ("postprocess_edits", "postprocess_voice_edits"):
        ref = inp.artifacts.get(kind)
        if ref is None:
            continue
        try:
            with open(ref.path, "r", encoding="utf-8") as fh:
                total += sum(1 for line in fh if line.strip())
        except OSError:
            # A missing log isn't a hard error — Phase 3 may have skipped.
            pass
    return total


def _scorecard_to_dict(card: ScoreCard) -> dict[str, float]:
    return {
        "measure_duration_match": round(card.measure_duration_match, 4),
        "in_range": round(card.in_range, 4),
        "density": round(card.density, 4),
        "key_consistency": round(card.key_consistency, 4),
        "structure_consistency": round(card.structure_consistency, 4),
        "edits_penalty": round(card.edits_penalty, 4),
    }


def _write_chosen(
    inp: StageInput,
    *,
    trial_id: str,
    param_set_id: str | None,
    fscore: float,
    card: ScoreCard,
    threshold: float,
    on_low_score: str,
) -> Path:
    """Persist the run's decision under `chosen.json` for warm-start replay."""
    target = inp.artifacts.path_for("evaluate", "chosen.json")
    data = {
        "job_id": inp.job_id,
        "trial_id": trial_id,
        "param_set_id": param_set_id,
        "final_score": round(fscore, 4),
        "score_card": _scorecard_to_dict(card),
        "page_threshold": threshold,
        "on_low_score": on_low_score,
        "passed": fscore >= threshold,
    }
    target.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
    return target


@register("evaluate")
def evaluate_stage(inp: StageInput) -> StageOutput:
    """Phase 4 single-trial evaluator.

    `params.scoring` keys:
      * `weights`         - 5-key weight map (must sum to 1.0)
      * `page_threshold`  - minimum final_score to consider this page ok
      * `on_low_score`    - retry / skip / fail_job (Phase 4-2-b)
    """
    cfg = inp.params.get("scoring", {})
    weights = cfg.get("weights")
    if not weights:
        return StageOutput(
            status="failed",
            error="evaluate: params.scoring.weights missing",
        )
    try:
        validate_weights(weights)
    except ValueError as exc:
        return StageOutput(status="failed", error=f"evaluate: {exc}")

    threshold = float(cfg.get("page_threshold", 0.70))
    on_low_score = str(cfg.get("on_low_score", "skip"))

    xml = _resolve_xml(inp)
    if xml is None:
        return StageOutput(
            status="failed",
            error="evaluate: no MusicXML upstream (postprocess or omr)",
        )

    try:
        score = parse_musicxml(xml)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"evaluate: parse failed: {type(exc).__name__}: {exc}",
        )

    edits = _count_edits(inp)
    card = score_musicxml(score, edits_count=edits)
    fscore = final_score(card, weights)
    passed = fscore >= threshold

    trial_id = inp.trace.get("trial_id", "t0")
    chosen_path = _write_chosen(
        inp,
        trial_id=str(trial_id),
        param_set_id=inp.trace.get("param_set_id"),
        fscore=fscore,
        card=card,
        threshold=threshold,
        on_low_score=on_low_score,
    )
    refs = [inp.artifacts.put(ArtifactRef(kind="chosen", path=str(chosen_path)))]

    metrics = StageMetrics(
        fields={
            "evaluate.final_score": round(fscore, 4),
            "evaluate.passed": passed,
            "evaluate.page_threshold": threshold,
            "evaluate.edits_total": edits,
            "evaluate.measure_duration_match": round(card.measure_duration_match, 4),
            "evaluate.in_range": round(card.in_range, 4),
            "evaluate.density": round(card.density, 4),
            "evaluate.key_consistency": round(card.key_consistency, 4),
            "evaluate.structure_consistency": round(card.structure_consistency, 4),
            "evaluate.edits_penalty": round(card.edits_penalty, 4),
        }
    )

    if passed:
        return StageOutput(status="ok", artifact_refs=refs, metrics=metrics)

    if on_low_score == "retry":
        return StageOutput(
            status="retryable",
            artifact_refs=refs,
            metrics=metrics,
            error=f"final_score {fscore:.3f} below threshold {threshold}",
        )
    if on_low_score == "fail_job":
        return StageOutput(
            status="failed",
            artifact_refs=refs,
            metrics=metrics,
            error=f"final_score {fscore:.3f} below threshold {threshold}",
        )
    # skip — keep the run going but flag the trial as not adopted.
    metrics.fields["evaluate.failure_class"] = "evaluate.low_score_below_threshold"
    return StageOutput(
        status="skipped",
        artifact_refs=refs,
        metrics=metrics,
        warnings=[f"final_score {fscore:.3f} below threshold {threshold}"],
    )
