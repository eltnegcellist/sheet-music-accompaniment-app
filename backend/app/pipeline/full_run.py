"""Run a full Phase 3 + Phase 4 pass over a MusicXML string.

This is the bridge that lets us measure "before" vs "after" without
spinning up Audiveris. Tests pass in raw OMR-like MusicXML, get back
the corrected MusicXML + the ScoreCard, and can compare against the
unprocessed result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping

from ..pipeline.evaluate import (
    ScoreCard,
    final_score,
    score_musicxml,
    validate_weights,
)
from ..pipeline.postprocess.edits import EditLog
from ..pipeline.postprocess.key_estimation import estimate_key
from ..pipeline.postprocess.key_signature import fix_dropped_key_accidentals
from ..pipeline.postprocess.missing_measures import fill_missing_measures
from ..pipeline.postprocess.pitch_fix import (
    fix_ngram_outliers,
    fix_octave_errors,
    fix_scale_outliers,
)
from ..pipeline.postprocess.rhythm_fix import fix_rhythm
from ..pipeline.postprocess.voice_rebuild import rebuild_voices
from ..pipeline.stages.postprocess import parse_musicxml, write_musicxml
from .scoring_facade import _DEFAULT_WEIGHTS  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)


@dataclass
class PipelineRun:
    """One full pass through the postprocess + evaluate chain."""

    music_xml: str            # corrected MusicXML
    card: ScoreCard
    final_score: float
    edits_count: int
    warnings: list[str]
    metrics: dict[str, float | int | str | bool]


def run_postprocess_and_evaluate(
    music_xml: str,
    *,
    fill_measures_enabled: bool = False,
    fix_key_accidentals_enabled: bool = False,
    rhythm_fix_enabled: bool = True,
    voice_rebuild_enabled: bool = True,
    pitch_fix_enabled: bool = False,
    snap_durations: list[int] | None = None,
    max_edits_per_measure: int = 4,
    pitch_fix_regression_threshold: float = 0.0,
    weights: Mapping[str, float] = _DEFAULT_WEIGHTS,
) -> PipelineRun | None:
    """Apply postprocess passes (in canonical order) and score the result.

    Pass order is fixed:
      1. fill_measures        — insert placeholders for measure-number gaps
      2. fix_key_accidentals  — restore # / b dropped by OMR (key-signature aware)
      3. rhythm_fix           — minimum-edit DP per measure
      4. voice_rebuild        — RH/LH reassign with rollback
      5. pitch_fix            — octave / scale-outlier / n-gram

    Each is independently togglable; defaults preserve the behaviour
    that existed before each knob was added.

    Returns None when the input is unparseable so the caller can fall
    back to raw scoring.
    """
    if not music_xml or not music_xml.strip():
        return None
    try:
        validate_weights(weights)
    except ValueError as exc:
        logger.warning("bad weights — %s", exc)
        return None
    try:
        score = parse_musicxml(music_xml)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "run_postprocess_and_evaluate: parse failed — %s: %s",
            type(exc).__name__, exc,
        )
        return None

    log = EditLog()
    warnings: list[str] = []
    metrics: dict[str, float | int | str | bool] = {}
    if fill_measures_enabled:
        fill_missing_measures(score, log=log)
    if fix_key_accidentals_enabled:
        fix_dropped_key_accidentals(score, log=log)
    if rhythm_fix_enabled:
        fix_rhythm(
            score,
            snap_durations=snap_durations or [1, 2, 4, 8, 16],
            max_edits_per_measure=max_edits_per_measure,
            log=log,
        )
    if voice_rebuild_enabled:
        rebuild_voices(score, log=log)
    if pitch_fix_enabled:
        can_rollback = True
        flat_notes = []
        pre_pitch_state: list[int] = []
        try:
            flat_notes = [n for n in score.flatten().notes if n.isNote]
            pre_pitch_state = [int(n.pitch.midi) for n in flat_notes]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "pitch_fix state save failed: %s: %s (rollback disabled)",
                type(exc).__name__, exc,
            )
            can_rollback = False
        pre_pitch_edits = len(log)
        pre_pitch_card = score_musicxml(score, edits_count=pre_pitch_edits)
        pre_pitch_score = final_score(pre_pitch_card, weights)

        # Order: octave first (catches Audiveris ledger-line confusion),
        # then scale (uses key estimate), then n-gram (catches whatever's
        # left). Each sub-pass mutates `score` in place.
        fix_octave_errors(score, log=log)
        key = estimate_key(score)
        if key is not None:
            fix_scale_outliers(score, key, log=log)
        fix_ngram_outliers(score, log=log)

        post_pitch_card = score_musicxml(score, edits_count=len(log))
        post_pitch_score = final_score(post_pitch_card, weights)
        regression = pre_pitch_score - post_pitch_score
        metrics.update(
            {
                "postprocess.pitch_fix.pre_final_score": round(pre_pitch_score, 4),
                "postprocess.pitch_fix.post_final_score": round(post_pitch_score, 4),
                "postprocess.pitch_fix.regression": round(regression, 4),
                "postprocess.pitch_fix.rollback_threshold": (
                    pitch_fix_regression_threshold
                ),
            }
        )
        if can_rollback and regression >= pitch_fix_regression_threshold and regression > 0:
            if len(flat_notes) != len(pre_pitch_state):
                logger.warning(
                    "pitch_fix rollback unavailable: snapshot size mismatch "
                    "(notes=%d state=%d)",
                    len(flat_notes), len(pre_pitch_state),
                )
                metrics["postprocess.pitch_fix.rollback"] = False
                card = post_pitch_card
                fscore = post_pitch_score
                edits = len(log)
            else:
                for n, original_midi in zip(flat_notes, pre_pitch_state):
                    n.pitch.midi = original_midi
                metrics["postprocess.pitch_fix.rollback"] = True
                reason = (
                    "pitch_fix rollback: final_score regressed by "
                    f"{regression:.4f} (threshold={pitch_fix_regression_threshold:.4f})"
                )
                warnings.append(reason)
                logger.warning(reason)
                card = pre_pitch_card
                fscore = pre_pitch_score
                edits = pre_pitch_edits
        else:
            if (
                not can_rollback
                and regression >= pitch_fix_regression_threshold
                and regression > 0
            ):
                logger.warning(
                    "pitch_fix regression detected, but rollback unavailable "
                    "due to save failure"
                )
            metrics["postprocess.pitch_fix.rollback"] = False
            card = post_pitch_card
            fscore = post_pitch_score
            edits = len(log)
    else:
        edits = len(log)
        card = score_musicxml(score, edits_count=edits)
        fscore = final_score(card, weights)

    try:
        out_xml = write_musicxml(score)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "run_postprocess_and_evaluate: write failed — %s: %s",
            type(exc).__name__, exc,
        )
        return None

    return PipelineRun(
        music_xml=out_xml,
        card=card,
        final_score=fscore,
        edits_count=edits,
        warnings=warnings,
        metrics=metrics,
    )
