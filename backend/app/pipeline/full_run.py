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


def run_postprocess_and_evaluate(
    music_xml: str,
    *,
    rhythm_fix_enabled: bool = True,
    voice_rebuild_enabled: bool = True,
    pitch_fix_enabled: bool = False,
    snap_durations: list[int] | None = None,
    max_edits_per_measure: int = 4,
    weights: Mapping[str, float] = _DEFAULT_WEIGHTS,
) -> PipelineRun | None:
    """Apply rhythm_fix + voice_rebuild + pitch_fix, then score the result.

    `pitch_fix_enabled` opts in the Phase 3-3 sub-passes (scale-outlier,
    octave-error, n-gram). Defaults to False so existing call sites get
    the same behaviour as before this knob existed.

    Returns None when the input is unparseable so the caller can fall
    back to raw scoring.
    """
    if not music_xml or not music_xml.strip():
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
        # Order: octave first (catches Audiveris ledger-line confusion),
        # then scale (uses key estimate), then n-gram (catches whatever's
        # left). Each sub-pass mutates `score` in place.
        fix_octave_errors(score, log=log)
        key = estimate_key(score)
        if key is not None:
            fix_scale_outliers(score, key, log=log)
        fix_ngram_outliers(score, log=log)

    try:
        out_xml = write_musicxml(score)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "run_postprocess_and_evaluate: write failed — %s: %s",
            type(exc).__name__, exc,
        )
        return None

    edits = len(log)
    try:
        validate_weights(weights)
    except ValueError as exc:
        logger.warning("bad weights — %s", exc)
        return None
    card = score_musicxml(score, edits_count=edits)
    fscore = final_score(card, weights)

    return PipelineRun(
        music_xml=out_xml,
        card=card,
        final_score=fscore,
        edits_count=edits,
    )
