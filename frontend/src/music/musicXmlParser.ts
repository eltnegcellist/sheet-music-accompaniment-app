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
  let elapsedBeats = 0;

  const measureEls = Array.from(part.getElementsByTagName("measure"));
  for (const measureEl of measureEls) {
    const measureIndex = Number(measureEl.getAttribute("number") ?? "0") || 0;
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

    const lengthBeats =
      measureLengthTicks > 0 ? ticksToBeats(measureLengthTicks, divisions) : 0;
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
