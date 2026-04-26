"""K-S key estimation (Phase 3-3-a).

Returns the most likely (tonic, mode, confidence) for a music21 Score.
The K-S profiles + Pearson correlation logic is shared with the Phase 4
`compute_key_consistency` metric: this module owns the math, the
evaluator imports from here.

`confidence` is the best correlation clipped to [0, 1]; the postprocess
fixers gate themselves on it (>= 0.6 by default per Phase 3-3-a) to
avoid over-correcting atonal or chromatic music.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from music21 import note, stream

# Krumhansl-Schmuckler 1990 profiles. These are intentionally module-level
# constants so a teaching debugger can inspect what the estimator is using.
KS_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KS_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

Mode = Literal["major", "minor"]


@dataclass(frozen=True)
class KeyEstimate:
    """Result of K-S key estimation.

    `tonic_pc` is 0..11 (C=0, C#=1, ..., B=11). `confidence` is the best
    correlation across all 24 keys, clipped to [0, 1] so 1.0 means a
    perfect match to a K-S profile.
    """

    tonic_pc: int
    mode: Mode
    confidence: float

    def scale_pcs(self) -> set[int]:
        """Pitch classes of the diatonic scale rooted at `tonic_pc`."""
        # Major: W W H W W W H — semitone offsets 0,2,4,5,7,9,11
        # Natural minor: W H W W H W W — offsets 0,2,3,5,7,8,10
        offsets = (0, 2, 4, 5, 7, 9, 11) if self.mode == "major" else (0, 2, 3, 5, 7, 8, 10)
        return {(self.tonic_pc + o) % 12 for o in offsets}


def pitch_class_histogram(score: stream.Score) -> list[float]:
    """Duration-weighted pitch class histogram (12 bins).

    Chord constituents contribute their full duration so a held chord
    counts each pitch class equally — this matches the K-S paper's
    intent (perceptual weight ≈ time presence).
    """
    bins = [0.0] * 12
    for n in score.flatten().notes:
        ql = float(n.duration.quarterLength)
        if isinstance(n, note.Note):
            bins[n.pitch.pitchClass] += ql
        else:  # Chord
            for p in n.pitches:
                bins[p.pitchClass] += ql
    return bins


def correlation(a: list[float], b: list[float]) -> float:
    """Pearson correlation; returns 0 when a or b is constant."""
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


def estimate_key(score: stream.Score) -> KeyEstimate | None:
    """Estimate the score's key using the K-S profiles.

    Returns None when the score has no pitched content — there's nothing
    to correct and the caller should leave pitches alone.
    """
    hist = pitch_class_histogram(score)
    if sum(hist) == 0:
        return None

    best_tonic = 0
    best_mode: Mode = "major"
    best_corr = -1.0
    for tonic in range(12):
        # Rotate the histogram so the tonic sits at index 0, matching the
        # K-S profile orientation.
        rotated = hist[tonic:] + hist[:tonic]
        for mode_name, profile in (("major", KS_MAJOR), ("minor", KS_MINOR)):
            c = correlation(rotated, profile)
            if c > best_corr:
                best_corr = c
                best_tonic = tonic
                best_mode = mode_name  # type: ignore[assignment]

    return KeyEstimate(
        tonic_pc=best_tonic,
        mode=best_mode,
        confidence=max(0.0, min(1.0, best_corr)),
    )
