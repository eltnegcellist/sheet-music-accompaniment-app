"""Key-signature-aware accidental restoration.

Audiveris's most common pitch-side failure on real PDFs is *dropping*
accidentals that the key signature implies. Concretely: a piece in G
major has F# in the key signature, but Audiveris sometimes emits
`<note><pitch><step>F</step><octave>4</octave></pitch>...` with no
`<alter>` for a note that should have inherited the key signature's
sharp. music21 then reads it as natural F (midi 65) rather than F#
(66).

`fix_dropped_key_accidentals` walks each measure under its active key
signature and:
  * finds notes whose step is altered by the key (e.g. F in G major)
  * AND whose pitch is the natural step (no explicit `<alter>` was
    written), AND whose pitch.accidental is None (no explicit natural
    either — meaning Audiveris didn't make any conscious choice)
  * applies the key-signature alteration to bring the pitch into line

We do NOT touch:
  * notes with an explicit `accidental` (sharp / flat / natural) —
    Audiveris saw a symbol and we trust it
  * chord constituents — same reasoning as the scale fix
  * measures with their own active KeySignature override changing
    mid-flow are tracked correctly by music21 (we read `getContext`)
"""

from __future__ import annotations

from dataclasses import dataclass

from music21 import key as m21key
from music21 import note, pitch as m21pitch, stream

from .edits import EditLocation, EditLog


@dataclass
class DroppedAccidentalReport:
    """Stats for the key-signature-aware accidental restorer."""

    candidates_checked: int = 0
    accidentals_restored: int = 0
    parts_processed: int = 0


def _active_key_signature(measure: stream.Measure) -> m21key.KeySignature | None:
    """Return the KeySignature in effect for `measure`, or None.

    Music21 carries the signature on the first measure that declares it
    and inherits forward. `getContextByClass` walks that chain.
    """
    explicit = list(measure.getElementsByClass("KeySignature"))
    if explicit:
        return explicit[0]
    return measure.getContextByClass(m21key.KeySignature)


def _step_alteration(ks: m21key.KeySignature, step: str) -> int:
    """Return the alteration semitones that key signature `ks` applies to `step`.

    Returns 0 when the step is unaltered, +1 for sharp, -1 for flat,
    +2 / -2 for double, etc. Music21's `accidentalByStep` returns
    Accidental objects whose `.alter` attribute carries the integer.
    """
    accidental = ks.accidentalByStep(step)
    if accidental is None:
        return 0
    return int(accidental.alter)


def fix_dropped_key_accidentals(
    score: stream.Score,
    *,
    log: EditLog,
) -> DroppedAccidentalReport:
    """Restore accidentals dropped by the OMR but implied by the key signature.

    Mutates `score` in place; logs one `key_accidental_restore` event
    per altered note.
    """
    report = DroppedAccidentalReport()
    for part in score.parts:
        report.parts_processed += 1
        part_id = str(part.id) if part.id is not None else "P?"
        for measure in part.getElementsByClass("Measure"):
            ks = _active_key_signature(measure)
            if ks is None or ks.sharps == 0:
                continue
            mnum = (
                int(measure.number) if measure.number is not None else -1
            )
            for el in measure.flatten().notes:
                # Skip chords entirely — letting one chord constituent
                # rewrite its own pitch breaks the rest of the chord.
                if not isinstance(el, note.Note):
                    continue
                step = el.pitch.step  # 'C'..'B'
                expected = _step_alteration(ks, step)
                if expected == 0:
                    continue
                report.candidates_checked += 1

                # If the OMR wrote any explicit accidental for this note,
                # respect it.  music21 marks `accidental.displayStatus`:
                # True when the symbol came from the input, False when it
                # was inferred from the key signature alone.
                acc = el.pitch.accidental
                if acc is not None and acc.displayStatus:
                    continue

                # Compare the actual midi to what the natural step would
                # produce. If they're equal, the OMR didn't apply the
                # key sig (the hallmark of the bug). If the midi already
                # equals the altered version, skip — music21 already
                # interpreted the key sig.
                natural_midi = el.pitch.midi - int(acc.alter) if acc else el.pitch.midi
                expected_midi = natural_midi + expected
                if int(el.pitch.midi) == expected_midi:
                    continue

                old_midi = int(el.pitch.midi)
                # Apply the alteration. Setting the accidental writes an
                # explicit display marker so subsequent passes (and the
                # MusicXML serialiser) emit the symbol.
                el.pitch.accidental = m21pitch.Accidental(expected)
                el.pitch.accidental.displayStatus = True
                # Re-derive midi from step + alter to stay consistent.
                el.pitch.midi = expected_midi
                report.accidentals_restored += 1
                log.append(
                    "key_accidental_restore",
                    reason=(
                        f"key signature has {ks.sharps:+d} sharps; "
                        f"step {step} is altered by {expected:+d} "
                        f"semitones, restored from natural"
                    ),
                    location=EditLocation(
                        part=part_id,
                        measure=mnum,
                        beat=float(el.offset),
                    ),
                    before={"midi": old_midi, "step": step, "alter": 0},
                    after={"midi": expected_midi, "step": step, "alter": expected},
                )
    return report
