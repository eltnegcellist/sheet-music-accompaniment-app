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

__all__ = [
    "ScoreCard",
    "compute_density",
    "compute_in_range",
    "compute_key_consistency",
    "compute_measure_duration_match",
    "compute_structure_consistency",
    "score_musicxml",
]
