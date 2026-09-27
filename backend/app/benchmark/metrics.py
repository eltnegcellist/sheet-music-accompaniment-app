"""Reference-based metrics for OMR MusicXML output.

The application's real failure mode is not just a wrong symbol: a wrong onset
or duration can make the accompaniment musically unusable. These metrics
therefore compare pitch, onset and duration together as the primary signal.
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from typing import Any

from music21 import chord, note, stream

from ..pipeline.stages.postprocess import parse_musicxml


def _fraction(value: Any) -> Fraction:
    """Normalize music21 offsets/durations to a stable rational value."""
    if isinstance(value, Fraction):
        return value.limit_denominator(384)
    return Fraction(str(float(value))).limit_denominator(384)


def _event_counters(xml: str) -> dict[str, Counter[tuple[Any, ...]]]:
    score = parse_musicxml(xml)
    exact: Counter[tuple[Any, ...]] = Counter()
    onset_pitch: Counter[tuple[Any, ...]] = Counter()
    rhythm: Counter[tuple[Any, ...]] = Counter()

    for part in score.parts:
        measures = list(part.getElementsByClass(stream.Measure))
        for measure_index, measure in enumerate(measures, start=1):
            for element in measure.flatten().notes:
                onset = _fraction(element.offset)
                duration = _fraction(element.duration.quarterLength)
                pitches: list[int]
                if isinstance(element, note.Note):
                    pitches = [int(element.pitch.midi)]
                elif isinstance(element, chord.Chord):
                    pitches = [int(pitch.midi) for pitch in element.pitches]
                else:
                    continue
                for midi in pitches:
                    exact[(measure_index, onset, midi, duration)] += 1
                    onset_pitch[(measure_index, onset, midi)] += 1
                    rhythm[(measure_index, onset, duration)] += 1

    return {
        "exact": exact,
        "onset_pitch": onset_pitch,
        "rhythm": rhythm,
    }


def _f1(
    predicted: Counter[tuple[Any, ...]],
    reference: Counter[tuple[Any, ...]],
) -> tuple[float, float, float]:
    matched = sum((predicted & reference).values())
    predicted_n = sum(predicted.values())
    reference_n = sum(reference.values())
    if predicted_n == 0 and reference_n == 0:
        return 1.0, 1.0, 1.0
    precision = matched / predicted_n if predicted_n else 0.0
    recall = matched / reference_n if reference_n else 0.0
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, f1


def _score_shape(xml: str) -> tuple[int, int]:
    score = parse_musicxml(xml)
    parts = list(score.parts)
    measure_count = max(
        (len(list(part.getElementsByClass(stream.Measure))) for part in parts),
        default=0,
    )
    return len(parts), measure_count


def _ratio(a: int, b: int) -> float:
    if a == 0 and b == 0:
        return 1.0
    if a == 0 or b == 0:
        return 0.0
    return min(a, b) / max(a, b)


def compare_musicxml(predicted_xml: str, reference_xml: str) -> dict[str, float | int | bool]:
    """Compare recognized MusicXML against a reference score.

    The primary metric is note_exact_f1: MIDI pitch + measure-local onset
    + duration must all match. onset_pitch_f1 separates duration errors,
    while rhythm_f1 ignores pitch and exposes timing/structure failures.
    """
    predicted = _event_counters(predicted_xml)
    reference = _event_counters(reference_xml)

    exact_p, exact_r, exact_f1 = _f1(predicted["exact"], reference["exact"])
    onset_p, onset_r, onset_f1 = _f1(
        predicted["onset_pitch"], reference["onset_pitch"]
    )
    rhythm_p, rhythm_r, rhythm_f1 = _f1(predicted["rhythm"], reference["rhythm"])

    predicted_parts, predicted_measures = _score_shape(predicted_xml)
    reference_parts, reference_measures = _score_shape(reference_xml)
    part_ratio = _ratio(predicted_parts, reference_parts)
    measure_ratio = _ratio(predicted_measures, reference_measures)

    playback_score = (
        0.60 * exact_f1
        + 0.15 * onset_f1
        + 0.15 * rhythm_f1
        + 0.05 * part_ratio
        + 0.05 * measure_ratio
    )

    return {
        "note_exact_precision": round(exact_p, 6),
        "note_exact_recall": round(exact_r, 6),
        "note_exact_f1": round(exact_f1, 6),
        "onset_pitch_precision": round(onset_p, 6),
        "onset_pitch_recall": round(onset_r, 6),
        "onset_pitch_f1": round(onset_f1, 6),
        "rhythm_precision": round(rhythm_p, 6),
        "rhythm_recall": round(rhythm_r, 6),
        "rhythm_f1": round(rhythm_f1, 6),
        "predicted_parts": predicted_parts,
        "reference_parts": reference_parts,
        "part_count_ratio": round(part_ratio, 6),
        "predicted_measures": predicted_measures,
        "reference_measures": reference_measures,
        "measure_count_ratio": round(measure_ratio, 6),
        "playback_score": round(playback_score, 6),
        "gross_failure": bool(exact_f1 < 0.50 or measure_ratio < 0.75),
    }
