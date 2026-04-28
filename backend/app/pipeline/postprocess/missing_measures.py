"""Missing-measure recovery (Phase 3-8 / Audiveris failure mode).

Audiveris occasionally drops entire measures from its output — the
MusicXML simply skips a measure number, leaving 1, 2, 4, 5… The frontend
playback engine then jumps over the gap silently and the user sees a
"音は出てるが楽譜のここが抜けてる" failure that's confusing without
direct access to the source PDF.

This pass detects gaps in the measure-number sequence and inserts
empty placeholder measures (full-bar rests) so:
  * the measure count matches what the layout overlay expects
  * the playback engine renders silence for the gap (a clear "this
    section was unreadable" cue) instead of gluing two unrelated bars
    together

We deliberately don't try to fabricate notes; that would lie to the
user about content the OCR couldn't see.
"""

from __future__ import annotations

from dataclasses import dataclass

from music21 import note, stream

from .edits import EditLocation, EditLog


@dataclass
class MissingMeasureReport:
    """Stats for the missing-measure recovery pass."""

    gaps_found: int = 0
    measures_inserted: int = 0
    parts_processed: int = 0


def _measure_numbers_of(part: stream.Part) -> list[int]:
    """Return the measure numbers in document order (skipping `None`)."""
    out: list[int] = []
    for m in part.getElementsByClass("Measure"):
        if m.number is None:
            continue
        out.append(int(m.number))
    return out


def _build_placeholder(
    bar_duration_ql: float,
    number: int,
    prev_measure: stream.Measure | None = None,
) -> stream.Measure:
    """Build a music21 Measure containing a single full-bar rest.

    `barDuration` is set explicitly so subsequent passes that read the
    expected duration don't misclassify the placeholder as broken.
    """
    placeholder = stream.Measure(number=number)
    rest_duration = max(bar_duration_ql, 0.0001)  # avoid 0-duration rest

    voices = (
        list(prev_measure.getElementsByClass("Voice"))
        if prev_measure is not None
        else []
    )
    if voices:
        for v in voices:
            new_v = stream.Voice(id=v.id)
            new_v.append(note.Rest(quarterLength=rest_duration))
            placeholder.insert(0.0, new_v)
    else:
        placeholder.append(note.Rest(quarterLength=rest_duration))

    return placeholder


def fill_missing_measures(
    score: stream.Score,
    *,
    log: EditLog,
    max_gap_size: int = 8,
) -> MissingMeasureReport:
    """Walk every part and insert placeholder rest-measures for number gaps.

    `max_gap_size` is a safety cap: a 50-measure gap likely indicates a
    structural issue elsewhere (e.g. a bad measure-number override) and
    blindly inserting 50 empty bars would make the output worse, not
    better. We log the oversized gap as `unfixable_gap` instead.

    Implementation note: we rebuild each part's measure stream from
    scratch with sequential offsets. `Part.insert(offset, placeholder)`
    is unreliable here because the original measures don't leave gaps
    in offset-space for the missing ones — the placeholder ends up
    overlapping the wrong neighbour.
    """
    report = MissingMeasureReport()
    for part in score.parts:
        report.parts_processed += 1
        part_id = str(part.id) if part.id is not None else "P?"

        existing = list(part.getElementsByClass("Measure"))
        if not existing:
            continue

        # Plan: walk pairs and build a list of (number, content) for the
        # full sequence, using the previous bar's duration for any
        # placeholders we need to drop in.
        plan: list[tuple[int, stream.Measure | None, float]] = []
        # Always carry the first measure in.
        first = existing[0]
        first_no = int(first.number) if first.number is not None else 1
        plan.append((first_no, first, float(first.barDuration.quarterLength)))

        for i in range(1, len(existing)):
            prev_no = plan[-1][0]
            prev_bar_ql = plan[-1][2]
            cur = existing[i]
            cur_no = int(cur.number) if cur.number is not None else prev_no + 1
            gap = cur_no - prev_no - 1
            if gap > 0:
                report.gaps_found += 1
                if gap > max_gap_size:
                    log.append(
                        "unfixable_gap",
                        reason=(
                            f"gap of {gap} measures (>{max_gap_size}) between "
                            f"{prev_no} and {cur_no} skipped to avoid runaway insertion"
                        ),
                        location=EditLocation(part=part_id, measure=prev_no),
                        before={"measures_missing": gap},
                    )
                else:
                    for missing_no in range(prev_no + 1, cur_no):
                        plan.append((missing_no, None, prev_bar_ql))
                        report.measures_inserted += 1
                        log.append(
                            "measure_insert",
                            reason=f"fill missing measure number {missing_no} with full-bar rest",
                            location=EditLocation(part=part_id, measure=missing_no),
                            after={"bar_duration_ql": prev_bar_ql},
                        )
            plan.append((cur_no, cur, float(cur.barDuration.quarterLength)))

        # If no gaps were filled, leave the part alone.
        if all(measure is not None for (_, measure, _) in plan):
            continue

        # Rebuild: detach existing measures, re-add at sequential offsets
        # in the correct order with placeholders interleaved.
        for m in existing:
            part.remove(m)
        offset = 0.0
        prev_m_for_placeholder = None
        for number, measure, bar_ql in plan:
            if measure is None:
                m = _build_placeholder(bar_ql, number, prev_m_for_placeholder)
            else:
                m = measure
                # Reset number in case the original carried something odd.
                m.number = number
                prev_m_for_placeholder = m
            part.insert(offset, m)
            offset += bar_ql
    return report
