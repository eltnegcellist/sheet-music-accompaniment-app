"""Phase 4-1 scoring — six indicators + a ScoreCard aggregator.

Each function takes a music21 Score and returns a value in [0, 1] (or
[0, ∞) for `edits_penalty`). They are deliberately tolerant: missing
context (no time signature, no notes) collapses gracefully to 0 rather
than raising — the evaluator treats such trials as failures upstream
via `validate_musicxml_shape`.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable

from music21 import note, stream

from ..postprocess.rhythm import analyse_measures, measure_duration_match_rate


@dataclass
class ScoreCard:
    measure_duration_match: float = 0.0
    in_range: float = 0.0
    density: float = 0.0
    key_consistency: float = 0.0
    structure_consistency: float = 0.0
    edits_penalty: float = 0.0


# --- 4-1-a: measure_duration_match --------------------------------------


def compute_measure_duration_match(score: stream.Score) -> float:
    return measure_duration_match_rate(analyse_measures(score))


# --- 4-1-a: in_range ----------------------------------------------------

# Wide piano-ish range used as the default. The plan calls out per-instrument
# tables in `instrument_ranges.py` for a future ticket; until that lands the
# wide default avoids over-flagging legitimate notes.
_DEFAULT_RANGE_MIDI = (21, 108)  # A0 .. C8


def compute_in_range(
    score: stream.Score,
    range_midi: tuple[int, int] = _DEFAULT_RANGE_MIDI,
) -> float:
    lo, hi = range_midi
    pitches: list[int] = []
    for n in score.flatten().notes:
        if isinstance(n, note.Note):
            pitches.append(int(n.pitch.midi))
        else:  # Chord
            pitches.extend(int(p.midi) for p in n.pitches)
    if not pitches:
        return 0.0
    in_count = sum(1 for p in pitches if lo <= p <= hi)
    return in_count / len(pitches)


# --- 4-1-a: density -----------------------------------------------------


def _notes_per_measure(score: stream.Score) -> list[int]:
    out: list[int] = []
    for part in score.parts:
        for measure in part.getElementsByClass("Measure"):
            n = sum(1 for _ in measure.flatten().notes)
            out.append(n)
    return out


def compute_density(score: stream.Score) -> float:
    """Fraction of measures whose note count sits within IQR (Phase 3-4-c)."""
    counts = _notes_per_measure(score)
    if not counts:
        return 0.0
    if len(counts) < 4:
        # IQR is meaningless for tiny scores — treat as fully in-band.
        return 1.0
    sorted_counts = sorted(counts)
    q1 = sorted_counts[len(sorted_counts) // 4]
    q3 = sorted_counts[(3 * len(sorted_counts)) // 4]
    iqr = q3 - q1
    upper = q3 + 1.5 * iqr
    in_band = sum(1 for c in counts if c <= upper)
    return in_band / len(counts)


# --- 4-1-a: key_consistency ---------------------------------------------


# Krumhansl-Schmuckler key profiles (major / minor) — values from the
# original 1990 paper, normalised so the min term doesn't dominate.
_KS_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_KS_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def _pitch_class_histogram(score: stream.Score) -> list[float]:
    bins = [0.0] * 12
    for n in score.flatten().notes:
        ql = float(n.duration.quarterLength)
        if isinstance(n, note.Note):
            bins[n.pitch.pitchClass] += ql
        else:
            for p in n.pitches:
                bins[p.pitchClass] += ql
    return bins


def _correlation(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    da = sum((x - mean_a) ** 2 for x in a) ** 0.5
    db = sum((y - mean_b) ** 2 for y in b) ** 0.5
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def compute_key_consistency(score: stream.Score) -> float:
    """Best K-S correlation across all 24 keys, clipped to [0, 1].

    Negative correlations collapse to 0 — they indicate "this is *not* in
    any key", which is what we want to penalise.
    """
    hist = _pitch_class_histogram(score)
    if sum(hist) == 0:
        return 0.0
    best = 0.0
    for offset in range(12):
        rotated = hist[offset:] + hist[:offset]
        for profile in (_KS_MAJOR, _KS_MINOR):
            c = _correlation(rotated, profile)
            if c > best:
                best = c
    return max(0.0, min(1.0, best))


# --- 4-1-a: structure_consistency ---------------------------------------


def compute_structure_consistency(score: stream.Score) -> float:
    """Composite of: part counts agree on measure count, no empty parts.

    Per the plan this should also include tie integrity; that depends on
    Phase 3-6 work and is left as a follow-up. We return a 2-term score
    here (each term contributes 0.5) so adding tie integrity later moves
    the metric toward 1.0 for known-good scores instead of capping it.
    """
    parts = list(score.parts)
    if not parts:
        return 0.0

    measure_counts = [len(part.getElementsByClass("Measure")) for part in parts]
    if not measure_counts:
        return 0.0
    consistent_count_score = (
        1.0 if len(set(measure_counts)) == 1 else min(measure_counts) / max(measure_counts)
    )

    empty_parts = sum(1 for p in parts if sum(1 for _ in p.flatten().notes) == 0)
    no_empty_parts_score = 1.0 - (empty_parts / len(parts))

    return 0.5 * consistent_count_score + 0.5 * no_empty_parts_score


# --- aggregator ---------------------------------------------------------


def score_musicxml(
    score: stream.Score,
    *,
    edits_count: int = 0,
    range_midi: tuple[int, int] = _DEFAULT_RANGE_MIDI,
) -> ScoreCard:
    """Compute every Phase 4-1 sub-score and bundle them in a ScoreCard."""
    notes_total = sum(1 for _ in score.flatten().notes)
    edits_penalty = (edits_count / notes_total) if notes_total > 0 else float(edits_count)
    return ScoreCard(
        measure_duration_match=compute_measure_duration_match(score),
        in_range=compute_in_range(score, range_midi=range_midi),
        density=compute_density(score),
        key_consistency=compute_key_consistency(score),
        structure_consistency=compute_structure_consistency(score),
        edits_penalty=edits_penalty,
    )
