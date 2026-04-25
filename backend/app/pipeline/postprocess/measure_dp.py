"""Minimum-edit DP for fixing one measure (Phase 3-1-b).

Operations + costs (matches the plan's table):
  - rest_insert  (cost 1) : append a rest to absorb a `delta < 0` shortfall
  - tail_delete  (cost 3) : remove the last note when `delta > 0` and the
                            note's duration matches the surplus
  - snap         (cost 2) : replace one note's duration with a grid candidate
  - tie_extend   (cost 1) : not implemented yet — left as a no-op for v1
                            (requires cross-measure context the DP doesn't have)

This module operates on `MeasureWorkItem` records (a tiny DTO mirror of
the music21 `Note`/`Rest` we care about) so the DP can be unit-tested
without spinning up music21 at all. The applier in `rhythm_fix.py`
maps the DP's chosen actions back onto the actual score.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Literal

from .snap import SnapProposal, propose_snap

ActionKind = Literal["snap", "rest_insert", "tail_delete", "noop"]


@dataclass(frozen=True)
class WorkNote:
    """A single note's duration before edits.

    `index` is its position in the measure; we use it as a stable handle
    so the planner result can be applied back without depending on the
    list order surviving intermediate transformations.
    """

    index: int
    duration_ql: float
    is_rest: bool = False


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    note_index: int | None
    new_duration_ql: float | None = None
    cost: int = 0
    reason: str = ""


@dataclass
class FixPlan:
    actions: list[Action] = field(default_factory=list)
    final_duration_ql: float = 0.0
    cost: int = 0
    feasible: bool = False


def _quantise(value: float) -> float:
    """Round to 6 decimals so floating-point arithmetic doesn't bloat the DP state space."""
    return round(value, 6)


def plan_measure_fix(
    notes: list[WorkNote],
    expected_ql: float,
    grid_ql: list[float],
    *,
    max_edits: int = 4,
) -> FixPlan:
    """Pick the lowest-cost edit set that makes the measure sum to `expected_ql`.

    Strategy:
      1. Try a no-edit plan first — if the measure already balances, we're done.
      2. Greedily explore each note's snap candidates (sorted by closeness)
         + the structural edits (rest_insert / tail_delete). Edits commute
         enough at this scale (≤ max_edits ≤ 4 in practice) that a depth-
         bounded DFS over (snap_or_skip)^N with structural fixes at the
         end is fast and complete.

    Returns `feasible=False` if no plan within `max_edits` reaches the
    target. The caller writes that case to metrics as `unfixable`.
    """
    initial_total = _quantise(sum(n.duration_ql for n in notes))
    target = _quantise(expected_ql)

    if abs(initial_total - target) <= 1e-3:
        return FixPlan(actions=[], final_duration_ql=initial_total, cost=0, feasible=True)

    # Pre-compute snap candidates per note so the DFS doesn't recompute them.
    snap_candidates: list[list[SnapProposal]] = [
        propose_snap(n.duration_ql, grid_ql) for n in notes
    ]

    best: FixPlan | None = None

    def _try_finish(actions: list[Action], total: float, cost: int) -> None:
        nonlocal best
        delta = _quantise(target - total)
        # Already balanced after snaps alone.
        if abs(delta) <= 1e-3:
            plan = FixPlan(
                actions=list(actions), final_duration_ql=total, cost=cost, feasible=True
            )
            if best is None or plan.cost < best.cost:
                best = plan
            return

        # Short bar -> pad with a single rest.
        if delta > 0 and len(actions) < max_edits:
            actions.append(
                Action(
                    kind="rest_insert",
                    note_index=None,
                    new_duration_ql=delta,
                    cost=1,
                    reason=f"insert rest of {delta} qL to fill measure",
                )
            )
            plan = FixPlan(
                actions=list(actions),
                final_duration_ql=_quantise(total + delta),
                cost=cost + 1,
                feasible=True,
            )
            if best is None or plan.cost < best.cost:
                best = plan
            actions.pop()
            return

        # Long bar -> delete the trailing note iff it exactly removes the surplus.
        if delta < 0 and notes and len(actions) < max_edits:
            tail = notes[-1]
            if abs(tail.duration_ql + delta) <= 1e-3:
                actions.append(
                    Action(
                        kind="tail_delete",
                        note_index=tail.index,
                        cost=3,
                        reason=f"delete trailing note of {tail.duration_ql} qL",
                    )
                )
                plan = FixPlan(
                    actions=list(actions),
                    final_duration_ql=_quantise(total - tail.duration_ql),
                    cost=cost + 3,
                    feasible=True,
                )
                if best is None or plan.cost < best.cost:
                    best = plan
                actions.pop()
                return

    def _dfs(idx: int, total: float, cost: int, actions: list[Action]) -> None:
        if cost > max_edits:
            return
        # If best is already cheaper than the *minimum* we could still post,
        # prune. Lower-bound on extra cost = 0 (we might still finish here).
        if best is not None and cost >= best.cost:
            return

        if idx == len(notes):
            _try_finish(actions, total, cost)
            return

        # Branch 1: don't snap this note.
        _dfs(idx + 1, _quantise(total + notes[idx].duration_ql), cost, actions)

        # Branch 2..n: snap to each candidate.
        for cand in snap_candidates[idx]:
            new_total = _quantise(total + cand.target_ql)
            actions.append(
                Action(
                    kind="snap",
                    note_index=notes[idx].index,
                    new_duration_ql=cand.target_ql,
                    cost=cand.cost,
                    reason=f"snap {notes[idx].duration_ql} -> {cand.target_ql} ({cand.confidence})",
                )
            )
            _dfs(idx + 1, new_total, cost + cand.cost, actions)
            actions.pop()

    _dfs(0, 0.0, 0, [])

    if best is None:
        return FixPlan(
            actions=[], final_duration_ql=initial_total, cost=0, feasible=False
        )
    return best
