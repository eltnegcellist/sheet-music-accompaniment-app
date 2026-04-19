import type { MeasureTiming, NoteEvent } from "../types";

/**
 * Parse MusicXML and emit playback events for the requested part.
 *
 * Returns:
 *   - notes: ordered NoteEvent[] (rests are skipped)
 *   - measures: MeasureTiming[] aligned with the MusicXML measure numbers,
 *               useful for looping and highlighting.
 *
 * Limitations (MVP): repeat structures (D.C., D.S., volta brackets) are not
 * unrolled; we play the score as written, top-to-bottom.
 */
export function parseMusicXml(
  xml: string,
  partId: string | null,
): { notes: NoteEvent[]; measures: MeasureTiming[] } {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const parseError = doc.querySelector("parsererror");
  if (parseError) {
    throw new Error("Failed to parse MusicXML");
  }

  const part = pickPart(doc, partId);
  if (!part) {
    return { notes: [], measures: [] };
  }

  const notes: NoteEvent[] = [];
  const measures: MeasureTiming[] = [];

  let divisions = 1; // ticks per quarter; updated when <attributes><divisions>
  // Expected measure length in ticks, derived from the current <time> signature.
  // 0 means "unknown" — we haven't seen a time signature yet.
  let expectedMeasureTicks = 0;
  let elapsedBeats = 0;

  const measureEls = Array.from(part.getElementsByTagName("measure"));
  for (const measureEl of measureEls) {
    const measureIndex = Number(measureEl.getAttribute("number") ?? "0") || 0;
    // <measure implicit="yes"> marks an anacrusis / pickup that is deliberately
    // shorter than a full bar. Don't pad those.
    const isImplicit = measureEl.getAttribute("implicit") === "yes";
    const measureStartBeat = elapsedBeats;
    let measureLengthTicks = 0;
    let cursorTicks = 0;

    for (const child of Array.from(measureEl.children)) {
      switch (child.tagName.toLowerCase()) {
        case "attributes": {
          const divEl = child.getElementsByTagName("divisions")[0];
          if (divEl?.textContent) {
            const parsed = Number.parseInt(divEl.textContent, 10);
            if (Number.isFinite(parsed) && parsed > 0) {
              divisions = parsed;
            }
          }
          const timeEl = child.getElementsByTagName("time")[0];
          if (timeEl) {
            const beats = Number.parseInt(
              timeEl.getElementsByTagName("beats")[0]?.textContent ?? "",
              10,
            );
            const beatType = Number.parseInt(
              timeEl.getElementsByTagName("beat-type")[0]?.textContent ?? "",
              10,
            );
            if (
              Number.isFinite(beats) &&
              beats > 0 &&
              Number.isFinite(beatType) &&
              beatType > 0
            ) {
              // Ticks per whole note = divisions * 4, so one beat at `beat-type`
              // spans (divisions * 4 / beat-type) ticks.
              expectedMeasureTicks = Math.round(
                (beats * divisions * 4) / beatType,
              );
            }
          }
          break;
        }
        case "backup": {
          const dur = readDuration(child);
          cursorTicks = Math.max(0, cursorTicks - dur);
          break;
        }
        case "forward": {
          cursorTicks += readDuration(child);
          measureLengthTicks = Math.max(measureLengthTicks, cursorTicks);
          break;
        }
        case "note": {
          const dur = readDuration(child);
          const isChord = child.getElementsByTagName("chord").length > 0;
          const isRest = child.getElementsByTagName("rest").length > 0;
          const noteStartTicks = isChord
            ? cursorTicks - dur // chord notes share the previous note's start
            : cursorTicks;

          if (!isRest) {
            const pitch = readPitch(child);
            if (pitch) {
              notes.push({
                beat:
                  measureStartBeat + ticksToBeats(noteStartTicks, divisions),
                durationBeats: ticksToBeats(dur, divisions),
                pitch,
                velocity: 0.8,
                measureIndex,
              });
            }
          }

          if (!isChord) {
            cursorTicks += dur;
            measureLengthTicks = Math.max(measureLengthTicks, cursorTicks);
          }
          break;
        }
      }
    }

    // OMR sometimes drops short notes/rests, leaving a measure whose content
    // sums to less than one bar. If we advance by just the observed ticks the
    // next measure starts early and every subsequent beat is shifted — the
    // classic "skipped half a beat" symptom. Fall back to the time-signature
    // length whenever we know it, except on explicitly short pickup measures.
    const effectiveLengthTicks =
      !isImplicit &&
      expectedMeasureTicks > 0 &&
      measureLengthTicks < expectedMeasureTicks
        ? expectedMeasureTicks
        : measureLengthTicks;
    const lengthBeats =
      effectiveLengthTicks > 0 ? ticksToBeats(effectiveLengthTicks, divisions) : 0;
    measures.push({
      index: measureIndex,
      startBeat: measureStartBeat,
      lengthBeats,
    });
    elapsedBeats += lengthBeats;
  }

  notes.sort((a, b) => a.beat - b.beat);
  return { notes, measures };
}

function pickPart(doc: Document, partId: string | null): Element | null {
  const parts = Array.from(doc.getElementsByTagName("part"));
  if (parts.length === 0) return null;
  if (partId) {
    const matched = parts.find((p) => p.getAttribute("id") === partId);
    if (matched) return matched;
  }
  return parts[parts.length - 1];
}

function readDuration(el: Element): number {
  const durEl = el.getElementsByTagName("duration")[0];
  if (!durEl?.textContent) return 0;
  const parsed = Number.parseInt(durEl.textContent, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function ticksToBeats(ticks: number, divisions: number): number {
  return divisions > 0 ? ticks / divisions : 0;
}

const STEP_TO_SEMITONE: Record<string, number> = {
  C: 0,
  D: 2,
  E: 4,
  F: 5,
  G: 7,
  A: 9,
  B: 11,
};

function readPitch(noteEl: Element): string | null {
  const pitchEl = noteEl.getElementsByTagName("pitch")[0];
  if (!pitchEl) return null;
  const step = pitchEl.getElementsByTagName("step")[0]?.textContent ?? "";
  const octave = Number.parseInt(
    pitchEl.getElementsByTagName("octave")[0]?.textContent ?? "",
    10,
  );
  const alterText = pitchEl.getElementsByTagName("alter")[0]?.textContent;
  if (!(step in STEP_TO_SEMITONE) || !Number.isFinite(octave)) return null;

  const alter = alterText ? Number.parseInt(alterText, 10) : 0;
  const base = STEP_TO_SEMITONE[step] + alter;
  // Normalize into 0..11 with octave adjustment for under/overflow.
  const normalized = ((base % 12) + 12) % 12;
  const octaveShift = Math.floor(base / 12);
  const noteName = SEMITONE_TO_NAME[normalized];
  return `${noteName}${octave + octaveShift}`;
}

const SEMITONE_TO_NAME = [
  "C",
  "C#",
  "D",
  "D#",
  "E",
  "F",
  "F#",
  "G",
  "G#",
  "A",
  "A#",
  "B",
];
