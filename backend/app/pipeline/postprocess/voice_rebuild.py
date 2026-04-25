"""Voice rebuild applier for Phase 3-5.

Scope of this v1 cut: read the parsed Score, propose RH/LH voice
assignments for each note, compute the reassignment rate, and apply
the assignments **non-destructively** by writing to `note.editorial.voice`.

We deliberately do NOT move notes between music21 `Part`s because:
  * music21 already splits 2-staff parts into two Parts at parse time, so
    in most piano scores the physical layout is already correct.
  * Inter-part moves require careful handling of part-list/voice/staff
    ids that easily corrupt the document; the rollback guard would
    rarely save us from that.

The rollback guard still matters: when the proposed reassignment changes
more than `rollback_rate_threshold` of notes, the applier records a
single `voice_rebuild_rollback` edit and returns without writing
voice tags. This implements the plan's "保守: 再割当て率が 30% を超え
たら元の割当てに rollback" rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from music21 import note, stream

from .edits import EditLocation, EditLog
from .voice import OnsetEvent, assign_voices_piano, reassignment_rate


@dataclass
class VoiceRebuildReport:
    notes_total: int = 0
    notes_reassigned: int = 0
    rollback: bool = False
    reassignment_rate: float = 0.0
    parts_processed: list[str] = field(default_factory=list)


def _existing_voice_for(note_obj, part_index: int) -> int:
    """Read music21's existing voice/staff hint for a note.

    `editorial.voice` is honoured when present; otherwise we fall back
    to the part's index — most piano scores parse into Part 1 (RH) and
    Part 2 (LH), so part_index gives a sensible default.
    """
    voice = getattr(note_obj.editorial, "voice", None)
    if voice in (1, 2):
        return int(voice)
    return 1 if part_index == 0 else 2


def _is_piano_part(part: stream.Part) -> bool:
    """Best-effort piano detection.

    The accompaniment heuristic in `app.music.accompaniment` is more
    sophisticated; here we just check the part name. This stage is
    skipped via params when no piano is involved, so a simple check
    avoids cross-package coupling.
    """
    raw = getattr(part, "partName", None) or part.id or ""
    name = str(raw).lower()
    return any(tok in name for tok in ("piano", "klavier", "pianoforte", "ピアノ"))


def rebuild_voices(
    score: stream.Score,
    *,
    log: EditLog,
    rollback_rate_threshold: float = 0.30,
    split_pitch_midi: int = 60,
) -> VoiceRebuildReport:
    """Propose RH/LH voice assignments and apply them or rollback.

    Mutates `score` in place when applied: writes `editorial.voice = 1|2`.
    """
    report = VoiceRebuildReport()

    # Music21 splits multi-staff piano parts into "P1-Staff1" / "P1-Staff2";
    # treat the whole bundle as one unit by collecting events across
    # piano-named parts only.
    piano_parts = [
        (i, p) for i, p in enumerate(score.parts) if _is_piano_part(p)
    ]
    if not piano_parts:
        # Nothing to rebuild — skipping is the right default for non-piano.
        return report

    # Build OnsetEvent stream from the piano parts.
    events: list[OnsetEvent] = []
    note_handles: list[note.Note] = []
    before: dict[int, int] = {}

    flat_index = 0
    for part_index, part in piano_parts:
        report.parts_processed.append(str(part.id))
        for n in part.flatten().notes:
            # Only single Notes participate; chord constituents inherit the
            # chord's voice so reassigning one would split the chord.
            if not isinstance(n, note.Note):
                continue
            try:
                midi = int(n.pitch.midi)
            except Exception:  # noqa: BLE001 - pitch errors come in many shapes
                continue
            existing = _existing_voice_for(n, part_index)
            before[flat_index] = existing
            events.append(
                OnsetEvent(
                    index=flat_index,
                    onset_ql=float(n.offset),
                    duration_ql=float(n.duration.quarterLength),
                    pitch_midi=midi,
                    staff=existing,
                    is_rest=False,
                )
            )
            note_handles.append(n)
            flat_index += 1

    report.notes_total = len(events)
    if report.notes_total == 0:
        return report

    proposed = assign_voices_piano(events, split_pitch_midi=split_pitch_midi)
    rate = reassignment_rate(before, proposed)
    report.reassignment_rate = rate

    if rate > rollback_rate_threshold:
        report.rollback = True
        log.append(
            "voice_rebuild_rollback",
            reason=(
                f"proposed reassignment rate {rate:.2%} exceeds threshold "
                f"{rollback_rate_threshold:.0%}; keeping original voices"
            ),
            location=EditLocation(),
            before={"reassignment_rate": rate},
        )
        return report

    # Apply: only flip notes whose voice changed.
    for va in proposed:
        if before.get(va.note_index) == va.voice:
            continue
        target = note_handles[va.note_index]
        target.editorial.voice = va.voice
        report.notes_reassigned += 1
        log.append(
            "voice_assign",
            reason=f"voice {before[va.note_index]} -> {va.voice}",
            location=EditLocation(
                part=str(target.activeSite.id) if target.activeSite is not None else None,
                measure=int(target.measureNumber) if target.measureNumber is not None else None,
                voice=va.voice,
                beat=float(target.offset),
            ),
            before={"voice": before[va.note_index]},
            after={"voice": va.voice},
        )
    return report
