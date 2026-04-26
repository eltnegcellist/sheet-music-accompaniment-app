"""Pitch correction passes (Phase 3-3-b/c/d).

Each pass is a pure function over a music21 Score that takes:
  * the score itself (mutated in place)
  * a `KeyEstimate` (or None for "not confident enough")
  * the shared EditLog

Caller (`postprocess.pitch_fix` stage) wires them up; tests can call
each pass independently with hand-crafted inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable

from music21 import note, stream

from .edits import EditLocation, EditLog
from .key_estimation import KeyEstimate


@dataclass
class ScaleFixReport:
    """Stats for the scale-outlier pass (Phase 3-3-b)."""

    candidates: int = 0          # notes that were off-scale
    corrected: int = 0           # notes whose pitch we actually changed
    skipped_by_per_measure_cap: int = 0


def _pitched_notes(score: stream.Score) -> list[tuple[note.Note, int]]:
    """Yield (note, measure_number) pairs for every single Note in the score.

    Chord constituents are intentionally skipped: chord pitches are
    chosen together so flipping one in isolation would break the chord.
    """
    out: list[tuple[note.Note, int]] = []
    for part in score.parts:
        for measure in part.getElementsByClass("Measure"):
            mnum = int(measure.number) if measure.number is not None else -1
            for el in measure.flatten().notes:
                if isinstance(el, note.Note):
                    out.append((el, mnum))
    return out


def _nearest_scale_pc(midi: int, scale_pcs: set[int]) -> tuple[int, int]:
    """Return (corrected_midi, semitone_delta) — the nearest scale-pc note.

    Ties (one semitone up vs. one semitone down) resolve toward zero
    delta first, then upward. This keeps the correction deterministic.
    """
    if midi % 12 in scale_pcs:
        return midi, 0
    # Search outward by ±1, ±2 semitones — never more than 2 since any
    # diatonic scale has at most a 2-semitone gap.
    for delta in (1, -1, 2, -2):
        if (midi + delta) % 12 in scale_pcs:
            return midi + delta, delta
    return midi, 0  # Should never happen for a 7-note scale.


def _is_isolated_outlier(
    seq: list[note.Note], idx: int, scale_pcs: set[int]
) -> bool:
    """Phase 3-3-b's "single occurrence between in-scale neighbours" rule.

    The neighbours-must-be-in-scale check is what stops chromatic
    passages (where many adjacent notes are off-scale together) from
    being decimated.
    """
    n = seq[idx]
    if n.pitch.midi % 12 in scale_pcs:
        return False
    prev_in = idx == 0 or seq[idx - 1].pitch.midi % 12 in scale_pcs
    next_in = idx == len(seq) - 1 or seq[idx + 1].pitch.midi % 12 in scale_pcs
    return prev_in and next_in


def fix_scale_outliers(
    score: stream.Score,
    key: KeyEstimate,
    *,
    log: EditLog,
    confidence_floor: float = 0.6,
    max_per_measure: int = 1,
) -> ScaleFixReport:
    """Phase 3-3-b: snap isolated off-scale notes to the nearest scale tone.

    No-op when `key.confidence < confidence_floor` — the plan calls this
    out explicitly to avoid blowing up chromatic / atonal scores. Same
    when more than `max_per_measure` corrections would fire in one bar
    (signal: "this measure has many accidentals on purpose").
    """
    report = ScaleFixReport()
    if key.confidence < confidence_floor:
        return report

    scale_pcs = key.scale_pcs()
    notes = _pitched_notes(score)

    # First pass: count outliers per measure to apply the per-measure cap
    # before mutating anything (the rule wants to disable the fix entirely
    # for measures with many accidentals, not just truncate it).
    per_measure_outliers: dict[int, list[int]] = {}
    seq_per_measure: dict[int, list[note.Note]] = {}
    for i, (n, mnum) in enumerate(notes):
        seq_per_measure.setdefault(mnum, []).append(n)

    for mnum, seq in seq_per_measure.items():
        out_in_measure: list[int] = []
        for idx, n in enumerate(seq):
            if _is_isolated_outlier(seq, idx, scale_pcs):
                out_in_measure.append(idx)
        per_measure_outliers[mnum] = out_in_measure
        report.candidates += len(out_in_measure)
        if len(out_in_measure) > max_per_measure:
            report.skipped_by_per_measure_cap += len(out_in_measure)
            per_measure_outliers[mnum] = []  # disable for this bar

    for mnum, out_idxs in per_measure_outliers.items():
        if not out_idxs:
            continue
        seq = seq_per_measure[mnum]
        for idx in out_idxs:
            n = seq[idx]
            old_midi = int(n.pitch.midi)
            new_midi, delta = _nearest_scale_pc(old_midi, scale_pcs)
            if delta == 0 or new_midi == old_midi:
                continue
            n.pitch.midi = new_midi
            report.corrected += 1
            log.append(
                "scale_fix",
                reason=(
                    f"isolated off-scale note moved {delta:+d} semitone "
                    f"toward {key.mode} key tonic_pc={key.tonic_pc}"
                ),
                location=EditLocation(
                    measure=mnum,
                    beat=float(n.offset),
                ),
                before={"midi": old_midi},
                after={"midi": new_midi},
            )
    return report


@dataclass
class OctaveFixReport:
    """Stats for the octave-error pass (Phase 3-3-d)."""

    candidates: int = 0
    corrected: int = 0


def _melodic_jumps(seq: list[note.Note]) -> list[int]:
    """Absolute semitone differences between adjacent notes."""
    return [
        abs(int(seq[i].pitch.midi) - int(seq[i - 1].pitch.midi))
        for i in range(1, len(seq))
    ]


def fix_octave_errors(
    score: stream.Score,
    *,
    log: EditLog,
    jump_threshold_semitones: int = 18,
) -> OctaveFixReport:
    """Phase 3-3-d: shift notes by ±octave when it makes the melody smoother.

    For each note `n` with adjacent notes `prev` and `next`, if:
      * the local jumps |n - prev| and |next - n| both exceed
        `jump_threshold_semitones`, AND
      * shifting n by +12 or -12 brings both jumps under the threshold,
    we apply the shift.

    This catches Audiveris's classic "ledger line off-by-an-octave" without
    dragging legitimate octave leaps into the correction.
    """
    report = OctaveFixReport()
    for part in score.parts:
        # Build the melodic sequence per part (interleaving parts would
        # produce phantom jumps at part boundaries).
        flat_notes = [n for n in part.flatten().notes if isinstance(n, note.Note)]
        for i in range(1, len(flat_notes) - 1):
            prev_n = flat_notes[i - 1]
            cur = flat_notes[i]
            nxt = flat_notes[i + 1]
            prev_jump = abs(int(cur.pitch.midi) - int(prev_n.pitch.midi))
            next_jump = abs(int(nxt.pitch.midi) - int(cur.pitch.midi))
            if prev_jump < jump_threshold_semitones or next_jump < jump_threshold_semitones:
                continue
            report.candidates += 1
            best_delta = 0
            best_score = prev_jump + next_jump
            for delta in (-12, 12):
                shifted = int(cur.pitch.midi) + delta
                p2 = abs(shifted - int(prev_n.pitch.midi))
                n2 = abs(int(nxt.pitch.midi) - shifted)
                # Require both new jumps to drop below the threshold, and
                # the total to strictly improve on the no-op baseline.
                if (
                    p2 < jump_threshold_semitones
                    and n2 < jump_threshold_semitones
                    and p2 + n2 < best_score
                ):
                    best_delta = delta
                    best_score = p2 + n2
            if best_delta == 0:
                continue
            old_midi = int(cur.pitch.midi)
            cur.pitch.midi = old_midi + best_delta
            report.corrected += 1
            log.append(
                "octave_fix",
                reason=f"shift {best_delta:+d} semitones to smooth jumps {prev_jump}/{next_jump}",
                location=EditLocation(
                    measure=int(cur.measureNumber) if cur.measureNumber is not None else None,
                    beat=float(cur.offset),
                ),
                before={"midi": old_midi},
                after={"midi": cur.pitch.midi},
            )
    return report


@dataclass
class NgramFixReport:
    """Stats for the n-gram melodic outlier pass (Phase 3-3-c)."""

    candidates: int = 0
    corrected: int = 0
    capped_by_max_ratio: int = 0


def fix_ngram_outliers(
    score: stream.Score,
    *,
    log: EditLog,
    max_ratio: float = 0.02,
    quantile: float = 0.99,
    correction_window_semitones: int = 1,
) -> NgramFixReport:
    """Phase 3-3-c: smooth out unusual 3-gram melodic jumps.

    Compute the distribution of |interval_in| + |interval_out| triplets
    across the whole score; flag the worst `quantile` fraction as
    candidates for nudging the middle note ±1 semitone toward the
    linear interpolation of its neighbours.

    Limited to `max_ratio` of total notes per the plan.
    """
    report = NgramFixReport()
    triples: list[tuple[stream.base.Music21Object, int, int, int]] = []
    for part in score.parts:
        flat_notes = [n for n in part.flatten().notes if isinstance(n, note.Note)]
        for i in range(1, len(flat_notes) - 1):
            prev_m = int(flat_notes[i - 1].pitch.midi)
            cur_m = int(flat_notes[i].pitch.midi)
            next_m = int(flat_notes[i + 1].pitch.midi)
            cost = abs(cur_m - prev_m) + abs(next_m - cur_m)
            triples.append((flat_notes[i], prev_m, cur_m, next_m, cost))  # type: ignore[arg-type]

    if not triples:
        return report

    costs = sorted(t[-1] for t in triples)
    cutoff_idx = max(0, int(quantile * (len(costs) - 1)))
    cutoff = costs[cutoff_idx]
    candidates = [t for t in triples if t[-1] >= cutoff]
    report.candidates = len(candidates)

    total_notes = sum(
        1 for n in score.flatten().notes if isinstance(n, note.Note)
    )
    cap = int(total_notes * max_ratio)

    for n_obj, prev_m, cur_m, next_m, _ in candidates:
        if report.corrected >= cap:
            report.capped_by_max_ratio += 1
            continue
        target = (prev_m + next_m) // 2  # linear interpolation
        # Only allow ±1 semitone shifts so we don't rewrite the melody.
        delta_to_target = target - cur_m
        if abs(delta_to_target) > correction_window_semitones:
            continue
        if delta_to_target == 0:
            continue
        old_midi = int(n_obj.pitch.midi)  # type: ignore[union-attr]
        n_obj.pitch.midi = old_midi + delta_to_target  # type: ignore[union-attr]
        report.corrected += 1
        log.append(
            "ngram_fix",
            reason=(
                f"unusual 3-gram (cost={prev_m}->{cur_m}->{next_m}); "
                f"nudged {delta_to_target:+d} toward midpoint"
            ),
            location=EditLocation(
                measure=int(n_obj.measureNumber) if getattr(n_obj, "measureNumber", None) is not None else None,
                beat=float(n_obj.offset),
            ),
            before={"midi": old_midi},
            after={"midi": int(n_obj.pitch.midi)},  # type: ignore[union-attr]
        )
    return report
