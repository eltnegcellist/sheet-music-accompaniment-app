"""Evaluation primitives — scoring, selection, warm-start (Phase 4)."""

from .metrics import (
    ScoreCard,
    compute_density,
    compute_in_range,
    compute_key_consistency,
    compute_measure_duration_match,
    compute_structure_consistency,
    score_musicxml,
)
from .weighting import (
    TrialScored,
    disqualified,
    final_score,
    pick_best,
    validate_weights,
)

__all__ = [
    "ScoreCard",
    "TrialScored",
    "compute_density",
    "compute_in_range",
    "compute_key_consistency",
    "compute_measure_duration_match",
    "compute_structure_consistency",
    "disqualified",
    "final_score",
    "pick_best",
    "score_musicxml",
    "validate_weights",
]
