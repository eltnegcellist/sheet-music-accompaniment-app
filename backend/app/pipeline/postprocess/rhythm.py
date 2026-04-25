"""Rhythm analysis primitives for Phase 3-1.

This module is split from `rhythm_fix.py` so the analyser stays a pure,
side-effect-free function and is reusable by the evaluator
(`measure_duration_match` metric in Phase 4).

`analyse_measures` walks every (part, voice) and returns a flat list of
`MeasureRhythm` records that downstream code can reason about without
poking music21 internals.
"""

from __future__ import annotations

from dataclasses import dataclass

from music21 import stream


@dataclass(frozen=True)
class MeasureRhythm:
    """Per-(part, voice, measure) rhythm summary.

    `expected_ql` is the bar duration in quarter-lengths; `actual_ql` is
    the sum of `notesAndRests` durations. `delta_ql = actual - expected`
    so positive = too long, negative = too short. Voice 0 means the
    measure has no explicit voice partition (single-voice case).
    """

    part: str
    measure: int
    voice: int
    expected_ql: float
    actual_ql: float

    @property
    def delta_ql(self) -> float:
        return self.actual_ql - self.expected_ql

    @property
    def matches(self) -> bool:
        # Allow tiny floating-point slop; anything > 1/256 of a bar is real.
        return abs(self.delta_ql) <= 1e-3


def _voice_durations(voice_or_measure) -> float:
    return float(
        sum(n.duration.quarterLength for n in voice_or_measure.notesAndRests)
    )


def analyse_measures(score: stream.Score) -> list[MeasureRhythm]:
    """Return one `MeasureRhythm` per (part, voice, measure)."""
    out: list[MeasureRhythm] = []
    for part in score.parts:
        # `Part.id` defaults to a generated string when MusicXML doesn't carry one.
        part_id = str(part.id) if part.id is not None else "P?"
        for measure in part.getElementsByClass("Measure"):
            expected = float(measure.barDuration.quarterLength)
            voices = list(measure.getElementsByClass("Voice"))
            if voices:
                # Multiple voices: each voice is treated as an independent bar.
                for v in voices:
                    out.append(
                        MeasureRhythm(
                            part=part_id,
                            measure=int(measure.number) if measure.number is not None else -1,
                            voice=int(getattr(v, "id", 0) or 0),
                            expected_ql=expected,
                            actual_ql=_voice_durations(v),
                        )
                    )
            else:
                out.append(
                    MeasureRhythm(
                        part=part_id,
                        measure=int(measure.number) if measure.number is not None else -1,
                        voice=0,
                        expected_ql=expected,
                        actual_ql=_voice_durations(measure),
                    )
                )
    return out


def measure_duration_match_rate(records: list[MeasureRhythm]) -> float:
    """Phase 4-1 metric: fraction of measure-voices whose duration matches."""
    if not records:
        return 0.0
    return sum(1 for r in records if r.matches) / len(records)
