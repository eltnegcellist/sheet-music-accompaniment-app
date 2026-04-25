"""Tests for plan_measure_fix — the minimum-edit DP for one measure (3-1-b)."""

from app.pipeline.postprocess.measure_dp import (
    Action,
    FixPlan,
    WorkNote,
    plan_measure_fix,
)
from app.pipeline.postprocess.snap import grid_to_quarter_lengths


GRID = grid_to_quarter_lengths([1, 2, 4, 8, 16])  # whole..16th


def _q(idx: int, dur: float, *, rest: bool = False) -> WorkNote:
    return WorkNote(index=idx, duration_ql=dur, is_rest=rest)


# --- already-balanced ----------------------------------------------------


def test_balanced_measure_needs_no_edits():
    notes = [_q(0, 1.0), _q(1, 1.0), _q(2, 1.0), _q(3, 1.0)]
    plan = plan_measure_fix(notes, expected_ql=4.0, grid_ql=GRID)
    assert plan.feasible
    assert plan.actions == []
    assert plan.cost == 0


# --- rest_insert (delta > 0) ---------------------------------------------


def test_short_measure_padded_with_rest():
    notes = [_q(0, 1.0), _q(1, 1.0), _q(2, 1.0)]
    plan = plan_measure_fix(notes, expected_ql=4.0, grid_ql=GRID)
    assert plan.feasible
    assert plan.cost == 1
    assert len(plan.actions) == 1
    assert plan.actions[0].kind == "rest_insert"
    assert plan.actions[0].new_duration_ql == 1.0


# --- tail_delete (delta < 0 and tail matches) ---------------------------


def test_long_measure_trims_trailing_note_when_it_fits():
    notes = [_q(0, 1.0), _q(1, 1.0), _q(2, 1.0), _q(3, 1.0), _q(4, 1.0)]
    plan = plan_measure_fix(notes, expected_ql=4.0, grid_ql=GRID)
    assert plan.feasible
    assert plan.cost == 3
    assert plan.actions[0].kind == "tail_delete"
    assert plan.actions[0].note_index == 4


# --- snap is the only viable cheap fix (slight overshoot) ---------------


def test_snap_is_chosen_for_slight_overshoot():
    # Total 4.05 in a 4/4 bar. tail_delete would over-cut (3.0). rest_insert
    # only handles delta > 0 (this is delta = -0.05). Only snap fits.
    notes = [_q(0, 1.0), _q(1, 1.0), _q(2, 1.0), _q(3, 1.05)]
    plan = plan_measure_fix(notes, expected_ql=4.0, grid_ql=GRID)
    assert plan.feasible
    snap_actions = [a for a in plan.actions if a.kind == "snap"]
    assert any(a.note_index == 3 and a.new_duration_ql == 1.0 for a in snap_actions)


def test_rest_insert_beats_snap_when_both_could_apply():
    # delta > 0 is always cheaper as a single rest_insert (cost 1) than
    # snap+rest (cost 3), so the DP should NOT introduce a snap here.
    notes = [_q(0, 1.0), _q(1, 1.0), _q(2, 0.95)]  # total 2.95, target 4.0
    plan = plan_measure_fix(notes, expected_ql=4.0, grid_ql=GRID)
    assert plan.feasible
    assert plan.cost == 1
    assert [a.kind for a in plan.actions] == ["rest_insert"]


# --- infeasibility ------------------------------------------------------


def test_unfixable_when_max_edits_exhausted():
    # Wildly mismatched durations that can't be reconciled with ≤2 edits.
    notes = [_q(0, 7.3), _q(1, 1.7)]
    plan = plan_measure_fix(notes, expected_ql=4.0, grid_ql=GRID, max_edits=1)
    assert plan.feasible is False
    assert plan.actions == []


def test_empty_measure_with_zero_target_is_balanced():
    plan = plan_measure_fix([], expected_ql=0.0, grid_ql=GRID)
    assert plan.feasible
    assert plan.cost == 0


def test_empty_measure_with_positive_target_padded():
    plan = plan_measure_fix([], expected_ql=4.0, grid_ql=GRID)
    assert plan.feasible
    assert plan.actions[0].kind == "rest_insert"


# --- minimal cost is preferred ------------------------------------------


def test_picks_minimum_cost_plan():
    # 2 quarters + 1 quarter-equivalent in a 4/4 bar — short by 1.
    # Compare cost: rest_insert(1) vs snap(2) variants. Should pick rest_insert.
    notes = [_q(0, 1.0), _q(1, 1.0), _q(2, 1.0)]
    plan = plan_measure_fix(notes, expected_ql=4.0, grid_ql=GRID)
    assert plan.cost == 1


# --- structural ---------------------------------------------------------


def test_action_dataclass_carries_reason():
    notes = [_q(0, 1.0)]
    plan = plan_measure_fix(notes, expected_ql=4.0, grid_ql=GRID)
    # The single rest_insert action must carry a non-empty reason for the log.
    assert plan.actions and plan.actions[0].reason
