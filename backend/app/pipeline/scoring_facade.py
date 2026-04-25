"""Convenience helpers used by /analyze to surface Phase 4 metrics.

This module avoids dragging the FastAPI handler into the full Pipeline
machinery: it parses a MusicXML string with music21, computes the 6
indicators, and returns a flat metric dict that fits straight into
`AnalyzeResponse.pipeline_metrics`.
"""

from __future__ import annotations

import logging
from typing import Mapping

from .evaluate import (
    final_score,
    score_musicxml,
    validate_weights,
)
from .stages.postprocess import parse_musicxml

logger = logging.getLogger(__name__)


# v1 weights — kept in sync with backend/params/v1_baseline.yaml.
_DEFAULT_WEIGHTS: Mapping[str, float] = {
    "measure_duration_match": 0.35,
    "in_range": 0.15,
    "density": 0.10,
    "key_consistency": 0.15,
    "structure_consistency": 0.25,
}


def evaluate_musicxml_metrics(
    music_xml: str,
    *,
    edits_count: int = 0,
    weights: Mapping[str, float] = _DEFAULT_WEIGHTS,
) -> dict[str, float] | None:
    """Score a MusicXML string and return a flat metrics dict.

    Returns None when the XML is unparseable — callers treat that as
    "Phase 4 metrics unavailable" rather than a hard error so /analyze
    can still respond with the OMR results.
    """
    if not music_xml or not music_xml.strip():
        return None
    try:
        validate_weights(weights)
    except ValueError as exc:
        logger.warning("evaluate_musicxml_metrics: bad weights — %s", exc)
        return None
    try:
        score = parse_musicxml(music_xml)
    except Exception as exc:  # noqa: BLE001 — music21 failures vary
        logger.warning(
            "evaluate_musicxml_metrics: parse failed — %s: %s",
            type(exc).__name__, exc,
        )
        return None
    card = score_musicxml(score, edits_count=edits_count)
    fscore = final_score(card, weights)
    return {
        "final_score": round(fscore, 4),
        "measure_duration_match": round(card.measure_duration_match, 4),
        "in_range": round(card.in_range, 4),
        "density": round(card.density, 4),
        "key_consistency": round(card.key_consistency, 4),
        "structure_consistency": round(card.structure_consistency, 4),
        "edits_penalty": round(card.edits_penalty, 4),
    }
