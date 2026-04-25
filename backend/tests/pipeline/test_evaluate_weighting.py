"""Tests for final_score, validate_weights, pick_best (Phase 4-1-b/c/d, 4-2-c)."""

from pathlib import Path

import pytest
import yaml

from app.pipeline.evaluate.metrics import ScoreCard
from app.pipeline.evaluate.weighting import (
    TrialScored,
    disqualified,
    final_score,
    pick_best,
    validate_weights,
)

REPO = Path(__file__).resolve().parents[2]
PARAMS_DIR = REPO / "params"


# --- validate_weights ---------------------------------------------------


def _good_weights():
    return {
        "measure_duration_match": 0.35,
        "in_range": 0.15,
        "density": 0.10,
        "key_consistency": 0.15,
        "structure_consistency": 0.25,
    }


def test_good_weights_validate():
    validate_weights(_good_weights())


def test_missing_weight_rejected():
    w = _good_weights()
    del w["density"]
    with pytest.raises(ValueError, match="missing"):
        validate_weights(w)


def test_extra_weight_rejected():
    w = _good_weights()
    w["foo"] = 0.0
    with pytest.raises(ValueError, match="unexpected"):
        validate_weights(w)


def test_sum_must_be_one():
    w = _good_weights()
    w["in_range"] = 0.5  # blows the sum to 1.5
    with pytest.raises(ValueError, match="sum to"):
        validate_weights(w)


def test_shipped_yaml_weights_validate():
    """v1_baseline.yaml weights must satisfy the validator (CI guard)."""
    raw = yaml.safe_load((PARAMS_DIR / "v1_baseline.yaml").read_text(encoding="utf-8"))
    validate_weights(raw["scoring"]["weights"])


# --- final_score --------------------------------------------------------


def test_final_score_perfect_card():
    card = ScoreCard(
        measure_duration_match=1.0,
        in_range=1.0,
        density=1.0,
        key_consistency=1.0,
        structure_consistency=1.0,
        edits_penalty=0.0,
    )
    assert final_score(card, _good_weights()) == 1.0


def test_final_score_clipped_to_zero():
    card = ScoreCard()  # all zeros, but big edit penalty
    card.edits_penalty = 1000
    s = final_score(card, _good_weights())
    assert s == 0.0


def test_final_score_edits_penalty_squashed():
    """tanh(very_large) ≈ 1 — penalty caps so a single huge edit can't make
    the score arbitrarily negative."""
    card = ScoreCard(measure_duration_match=1.0, in_range=1.0, density=1.0,
                     key_consistency=1.0, structure_consistency=1.0,
                     edits_penalty=1e6)
    # Squashed penalty = 0.15 * tanh(1e6) ≈ 0.15. Final ≈ 0.85.
    s = final_score(card, _good_weights())
    assert pytest.approx(s, abs=1e-3) == 0.85


# --- pick_best ----------------------------------------------------------


def _trial(tid: str, score: float, mdm: float = 0.0, ep: float = 0.0) -> TrialScored:
    return TrialScored(
        trial_id=tid,
        card=ScoreCard(measure_duration_match=mdm, edits_penalty=ep),
        final_score=score,
    )


def test_pick_best_returns_highest_score():
    best = pick_best([_trial("a", 0.5), _trial("b", 0.9), _trial("c", 0.7)])
    assert best is not None and best.trial_id == "b"


def test_pick_best_breaks_ties_on_measure_duration_match():
    a = _trial("a", 0.7, mdm=0.5)
    b = _trial("b", 0.7, mdm=0.9)
    assert pick_best([a, b]).trial_id == "b"


def test_pick_best_breaks_ties_on_edits_penalty():
    a = _trial("a", 0.7, mdm=0.9, ep=0.1)
    b = _trial("b", 0.7, mdm=0.9, ep=0.05)
    assert pick_best([a, b]).trial_id == "b"


def test_pick_best_deterministic_on_full_tie():
    a = _trial("z", 0.7, mdm=0.9, ep=0.05)
    b = _trial("a", 0.7, mdm=0.9, ep=0.05)
    # Lexicographic on trial_id breaks the final tie.
    assert pick_best([a, b]).trial_id == "a"


def test_pick_best_empty_returns_none():
    assert pick_best([]) is None


# --- disqualified -------------------------------------------------------


def test_disqualified_for_empty_score():
    assert disqualified(ScoreCard()) is True


def test_not_disqualified_for_real_score():
    assert disqualified(
        ScoreCard(measure_duration_match=1.0, in_range=1.0)
    ) is False
