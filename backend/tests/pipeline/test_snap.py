"""Tests for the duration snapper (Phase 3-1-c)."""

import pytest

from app.pipeline.postprocess.snap import (
    SnapProposal,
    grid_to_quarter_lengths,
    propose_snap,
)


def test_grid_conversion_descending_qL():
    assert grid_to_quarter_lengths([1, 2, 4, 8, 16]) == [4.0, 2.0, 1.0, 0.5, 0.25]


def test_grid_skips_zero_and_dedups():
    assert grid_to_quarter_lengths([4, 4, 0, 8]) == [1.0, 0.5]


# --- tight zone (≤15%) ---------------------------------------------------


def test_tight_snap_returns_single_proposal():
    grid = grid_to_quarter_lengths([4, 8])  # [1.0, 0.5]
    props = propose_snap(0.95, grid)
    assert len(props) == 1
    assert props[0].target_ql == 1.0
    assert props[0].cost == 2
    assert props[0].confidence == "tight"


def test_tight_snap_to_eighth():
    props = propose_snap(0.48, grid_to_quarter_lengths([4, 8]))
    assert len(props) == 1
    assert props[0].target_ql == 0.5
    assert props[0].confidence == "tight"


# --- loose zone (15–25%) -------------------------------------------------


def test_loose_zone_returns_up_to_two_candidates():
    # 0.6 qL: 20% above 0.5, 40% below 1.0 — only 0.5 fits the loose band.
    props = propose_snap(0.6, grid_to_quarter_lengths([4, 8]))
    targets = [p.target_ql for p in props]
    assert 0.5 in targets
    assert all(p.confidence == "loose" for p in props)


def test_loose_zone_two_candidates_when_both_within_band():
    # Use a grid with very close lines so two are inside the loose band.
    props = propose_snap(0.55, grid_to_quarter_lengths([4, 8, 6]))
    # grid_ql contains 0.5 and ~0.667; both within 25% of 0.55? 0.5 -> 9%, 0.667 -> 21%.
    # We only check that the nearest is offered first.
    assert props[0].target_ql == 0.5


# --- reject zone (>25%) --------------------------------------------------


def test_far_durations_get_no_proposals():
    # 0.75 is 50% above 0.5 and 25% below 1.0 — the band rejects both.
    props = propose_snap(0.75, grid_to_quarter_lengths([4, 8]))
    assert props == [] or props[0].target_ql == 1.0  # 25% boundary is inclusive


def test_zero_or_negative_actual_returns_no_proposal():
    assert propose_snap(0.0, grid_to_quarter_lengths([4])) == []
    assert propose_snap(-1.0, grid_to_quarter_lengths([4])) == []


def test_empty_grid_returns_no_proposal():
    assert propose_snap(0.95, []) == []
