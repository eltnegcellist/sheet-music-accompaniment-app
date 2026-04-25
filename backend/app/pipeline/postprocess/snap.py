"""Duration snapping (Phase 3-1-c).

`snap_durations: [1, 2, 4, 8, 16]` in the params YAML refers to MusicXML
note types (whole=1, half=2, quarter=4, …). Internally we work in
quarter-lengths (qL) because that's music21's native unit.

A grid value `g` (e.g. 4 = quarter) corresponds to `4 / g` qL:
  - 1 (whole)   = 4.0 qL
  - 2 (half)    = 2.0 qL
  - 4 (quarter) = 1.0 qL
  - 8 (eighth)  = 0.5 qL
  - 16 (16th)   = 0.25 qL

The plan defines two zones (3-1-c):
  * |Δ| ≤ 15%  → snap unconditionally
  * 15–25%      → propose nearest two grid candidates; the DP later picks
  * >25%        → leave alone
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SnapProposal:
    """One candidate snapping for an input duration.

    `cost` mirrors the plan's Phase 3-1-b table (snap = 2). Unconditional
    snaps still cost something so the DP doesn't run away with them.
    """

    target_ql: float
    cost: int
    confidence: str  # "tight" (≤15%) or "loose" (≤25%)


def grid_to_quarter_lengths(grid: list[int]) -> list[float]:
    """Convert snap_durations note-type values to qL, sorted desc.

    Sorting matters because the snapper iterates from coarsest to finest;
    when two grid values are equally close the coarser one wins (it's the
    less invasive edit).
    """
    qls = sorted({4.0 / g for g in grid if g > 0}, reverse=True)
    return qls


def _relative_distance(actual: float, target: float) -> float:
    if target == 0:
        return float("inf")
    return abs(actual - target) / target


def propose_snap(
    actual_ql: float,
    grid_ql: list[float],
    *,
    tight_threshold: float = 0.15,
    loose_threshold: float = 0.25,
) -> list[SnapProposal]:
    """Return zero, one, or two snap proposals for `actual_ql`.

    Caller is responsible for picking a proposal (or rejecting all) — we
    don't mutate the score here.
    """
    if actual_ql <= 0 or not grid_ql:
        return []

    # Sort by closeness to actual so the first entry is always the best fit.
    by_distance = sorted(
        ((g, _relative_distance(actual_ql, g)) for g in grid_ql),
        key=lambda kv: kv[1],
    )

    proposals: list[SnapProposal] = []
    nearest, nearest_dist = by_distance[0]
    if nearest_dist <= tight_threshold:
        proposals.append(SnapProposal(target_ql=nearest, cost=2, confidence="tight"))
        # When tightly snapped we don't bother offering the second-closest
        # grid line — the plan only branches the DP in the loose zone.
        return proposals
    if nearest_dist <= loose_threshold:
        proposals.append(SnapProposal(target_ql=nearest, cost=2, confidence="loose"))
        if len(by_distance) > 1:
            second, second_dist = by_distance[1]
            if second_dist <= loose_threshold:
                proposals.append(SnapProposal(target_ql=second, cost=2, confidence="loose"))
    return proposals
