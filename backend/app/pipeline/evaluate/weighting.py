"""Final-score aggregation (Phase 4-1-b/c/d)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from .metrics import ScoreCard

# Required weight keys — must match the YAML schema.
_WEIGHT_KEYS = (
    "measure_duration_match",
    "in_range",
    "density",
    "key_consistency",
    "structure_consistency",
)


def validate_weights(weights: Mapping[str, float], *, tolerance: float = 1e-6) -> None:
    """Phase 4-1-b: weights must sum to 1.0 within tolerance.

    The CI test (`test_scoring_weights.py`) calls this on every params
    YAML so a typo doesn't ship silently.
    """
    missing = [k for k in _WEIGHT_KEYS if k not in weights]
    if missing:
        raise ValueError(f"weights missing keys: {missing}")
    extra = [k for k in weights if k not in _WEIGHT_KEYS]
    if extra:
        raise ValueError(f"weights has unexpected keys: {extra}")
    total = sum(weights[k] for k in _WEIGHT_KEYS)
    if abs(total - 1.0) > tolerance:
        raise ValueError(f"weights sum to {total}, expected 1.0")


def final_score(
    card: ScoreCard,
    weights: Mapping[str, float],
    *,
    edits_penalty_weight: float = 0.15,
) -> float:
    """Compute the weighted final score with the edits penalty subtracted.

    `edits_penalty` is unbounded so we squash it through tanh per
    Phase 4-1-d before applying the weight. Result is clipped to [0, 1]
    so callers can compare against `page_threshold` directly.
    """
    validate_weights(weights)
    base = sum(weights[k] * getattr(card, k) for k in _WEIGHT_KEYS)
    penalty = edits_penalty_weight * math.tanh(card.edits_penalty)
    return max(0.0, min(1.0, base - penalty))


@dataclass
class TrialScored:
    """A trial after Phase 4 evaluation."""

    trial_id: str
    card: ScoreCard
    final_score: float


def disqualified(card: ScoreCard) -> bool:
    """Phase 4-1-c hard failures (returned final_score == 0)."""
    if card.measure_duration_match == 0.0 and card.in_range == 0.0:
        # No notes / no measures — both sub-scores collapsed to 0 alongside.
        return True
    return False


def pick_best(
    trials: list[TrialScored],
) -> TrialScored | None:
    """Phase 4-2-c: return the highest-scoring trial; tie-break per spec.

    Tie-break order:
      1. measure_duration_match (descending)
      2. edits_penalty (ascending)
      3. trial_id (lexicographic, deterministic)
    """
    if not trials:
        return None

    def _rank(t: TrialScored):
        return (
            -t.final_score,
            -t.card.measure_duration_match,
            t.card.edits_penalty,
            t.trial_id,
        )

    return sorted(trials, key=_rank)[0]
