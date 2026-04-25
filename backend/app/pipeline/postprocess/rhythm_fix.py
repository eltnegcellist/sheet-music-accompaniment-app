"""Apply Phase 3-1 rhythm fixes to a music21 Score.

`fix_rhythm` walks measures, asks `plan_measure_fix` for an edit plan,
and applies the resulting actions to the live music21 objects. Every
applied action is also recorded into the supplied `EditLog` so the
evaluator can read the trail later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from music21 import note, stream

from .edits import EditLocation, EditLog
from .measure_dp import Action, FixPlan, WorkNote, plan_measure_fix
from .snap import grid_to_quarter_lengths


@dataclass
class RhythmFixReport:
    """Aggregate stats over an entire score's rhythm fix pass."""

    measures_total: int = 0
    measures_fixed: int = 0
    measures_unfixable: int = 0
    actions_by_kind: dict[str, int] = field(default_factory=dict)


def _voice_or_measure_elements(container) -> list:
    """Return the list of `Note`/`Rest` objects in document order."""
    return [el for el in container.notesAndRests]


def _apply_actions(
    container,
    actions: list[Action],
    *,
    log: EditLog,
    part_id: str,
    measure_no: int,
    voice_no: int,
) -> dict[str, int]:
    """Mutate `container` by executing `actions`. Returns a count by kind."""
    counts: dict[str, int] = {}

    # Build an index map: WorkNote.index -> live element. We snapshot once
    # because `tail_delete` removes elements and would shift positional ids.
    elements = _voice_or_measure_elements(container)

    for action in actions:
        counts[action.kind] = counts.get(action.kind, 0) + 1
        loc = EditLocation(part=part_id, measure=measure_no, voice=voice_no)

        if action.kind == "rest_insert":
            new_rest = note.Rest(quarterLength=float(action.new_duration_ql or 0))
            container.append(new_rest)
            log.append(
                "rest_insert",
                reason=action.reason,
                location=loc,
                after={"duration_ql": float(action.new_duration_ql or 0)},
            )
            continue

        if action.kind == "tail_delete":
            target = elements[action.note_index] if action.note_index is not None else None
            if target is not None:
                before = {"duration_ql": float(target.duration.quarterLength)}
                container.remove(target)
                log.append(
                    "tail_delete",
                    reason=action.reason,
                    location=loc,
                    before=before,
                )
            continue

        if action.kind == "snap":
            target = elements[action.note_index] if action.note_index is not None else None
            new_qL = float(action.new_duration_ql or 0)
            if target is not None and new_qL > 0:
                before = {"duration_ql": float(target.duration.quarterLength)}
                target.duration.quarterLength = new_qL
                log.append(
                    "snap",
                    reason=action.reason,
                    location=loc,
                    before=before,
                    after={"duration_ql": new_qL},
                )
            continue

        # noop or unknown — record nothing.

    return counts


def fix_rhythm(
    score: stream.Score,
    *,
    snap_durations: list[int],
    max_edits_per_measure: int,
    log: EditLog,
) -> RhythmFixReport:
    """Walk every (part, voice, measure) and apply the minimum-edit fix.

    The function mutates `score` in place — callers serialise the result
    via `write_musicxml` afterwards. The returned report is meant for
    stage metrics, not for re-application.
    """
    grid_ql = grid_to_quarter_lengths(snap_durations)
    report = RhythmFixReport()

    for part in score.parts:
        part_id = str(part.id) if part.id is not None else "P?"
        for measure in part.getElementsByClass("Measure"):
            measure_no = (
                int(measure.number) if measure.number is not None else -1
            )
            voices = list(measure.getElementsByClass("Voice"))
            containers = voices if voices else [measure]
            for v in containers:
                voice_no = (
                    int(getattr(v, "id", 0) or 0) if voices else 0
                )
                report.measures_total += 1
                expected_ql = float(measure.barDuration.quarterLength)
                work = [
                    WorkNote(
                        index=i,
                        duration_ql=float(el.duration.quarterLength),
                        is_rest=isinstance(el, note.Rest),
                    )
                    for i, el in enumerate(v.notesAndRests)
                ]
                plan: FixPlan = plan_measure_fix(
                    work,
                    expected_ql=expected_ql,
                    grid_ql=grid_ql,
                    max_edits=max_edits_per_measure,
                )
                if not plan.feasible:
                    report.measures_unfixable += 1
                    continue
                if not plan.actions:
                    # Already balanced — nothing to do, nothing to log.
                    continue
                report.measures_fixed += 1
                kind_counts = _apply_actions(
                    v,
                    plan.actions,
                    log=log,
                    part_id=part_id,
                    measure_no=measure_no,
                    voice_no=voice_no,
                )
                for k, c in kind_counts.items():
                    report.actions_by_kind[k] = (
                        report.actions_by_kind.get(k, 0) + c
                    )
    return report
