import type { MeasureTiming, NoteEvent } from "../types";

/**
 * Parse MusicXML and emit playback events for the requested part.
 *
 * Two-pass design:
 *   1. Walk every measure, collecting raw notes (with *relative* beat offsets
 *      within the measure) and the observed measure length in beats.
 *   2. Derive a canonical measure length — the mode of observed lengths across
 *      non-pickup measures — and lay measures on a uniform grid at that
 *      length. Working in beats (not ticks) is important because Audiveris
 *      sometimes changes <divisions> mid-score, so tick counts aren't
 *      comparable across measures.
 *
 * This absorbs OMR outliers (a stray 2.5-beat measure inside an otherwise
 * 2-beat piece would otherwise push every subsequent beat by half a beat).
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

  const rawMeasures = collectRawMeasures(part);
  const canonicalBeats = computeCanonicalBeats(rawMeasures);

  const measures: MeasureTiming[] = [];
  const notes: NoteEvent[] = [];
  let elapsedBeats = 0;

  for (const raw of rawMeasures) {
    const lengthBeats = pickMeasureLength(raw, canonicalBeats);

    if (
      canonicalBeats > 0 &&
      !raw.isImplicit &&
      Math.abs(raw.observedBeats - canonicalBeats) > 1e-6
    ) {
      const action =
        raw.observedBeats < canonicalBeats
          ? "padded up to"
          : "truncated down to";
      // eslint-disable-next-line no-console
      console.warn(
        `[musicxml] measure ${raw.index}: observed ${raw.observedBeats.toFixed(3)} beats, ` +
          `${action} canonical ${canonicalBeats.toFixed(3)} beats`,
      );
    }

    measures.push({
      index: raw.index,
      startBeat: elapsedBeats,
      lengthBeats,
    });

    for (const n of raw.notes) {
      notes.push({
        beat: elapsedBeats + n.relativeBeats,
        durationBeats: n.durationBeats,
        pitch: n.pitch,
        velocity: n.velocity,
        measureIndex: n.measureIndex,
      });
    }

    elapsedBeats += lengthBeats;
  }

  notes.sort((a, b) => a.beat - b.beat);
  return { notes, measures };
}

interface RawNote {
  /** Offset from the start of the owning measure, in beats. */
  relativeBeats: number;
  durationBeats: number;
  pitch: string;
  velocity: number;
  measureIndex: number;
}

interface RawMeasure {
  index: number;
  isImplicit: boolean;
  observedBeats: number;
  /** Length suggested by the active <time> signature, in beats. 0 if unknown. */
  expectedBeats: number;
  notes: RawNote[];
}

function collectRawMeasures(part: Element): RawMeasure[] {
  const out: RawMeasure[] = [];
  let divisions = 1; // ticks per quarter; updated when <attributes><divisions>
  let expectedMeasureTicks = 0;

  for (const measureEl of Array.from(part.getElementsByTagName("measure"))) {
    const measureIndex = Number(measureEl.getAttribute("number") ?? "0") || 0;
    // <measure implicit="yes"> marks a pickup that is deliberately short.
    // Exclude from the mode calculation and keep its observed length.
    const isImplicit = measureEl.getAttribute("implicit") === "yes";
    let measureLengthTicks = 0;
    let cursorTicks = 0;
    const rawNotes: RawNote[] = [];

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
              rawNotes.push({
                relativeBeats: ticksToBeats(noteStartTicks, divisions),
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

    out.push({
      index: measureIndex,
      isImplicit,
      observedBeats: ticksToBeats(measureLengthTicks, divisions),
      expectedBeats:
        expectedMeasureTicks > 0
          ? ticksToBeats(expectedMeasureTicks, divisions)
          : 0,
      notes: rawNotes,
    });
  }

  return out;
}

/**
 * Canonical measure length (in beats) = mode of observed lengths across
 * non-pickup, non-empty measures. More robust than trusting <time>+divisions
 * because Audiveris occasionally emits a wrong time signature. Ties break to
 * the smaller value for deterministic output.
 */
function computeCanonicalBeats(measures: RawMeasure[]): number {
  const counts = new Map<number, number>();
  for (const m of measures) {
    if (m.isImplicit) continue;
    if (m.observedBeats <= 0) continue;
    // Quantize to 1/1000 of a beat to fold floating-point noise.
    const key = Math.round(m.observedBeats * 1000) / 1000;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  if (counts.size === 0) return 0;

  let bestKey = Number.POSITIVE_INFINITY;
  let bestCount = 0;
  for (const [k, c] of counts) {
    if (c > bestCount || (c === bestCount && k < bestKey)) {
      bestKey = k;
      bestCount = c;
    }
  }
  return Number.isFinite(bestKey) ? bestKey : 0;
}

function pickMeasureLength(raw: RawMeasure, canonicalBeats: number): number {
  if (raw.isImplicit) {
    if (raw.observedBeats > 0) return raw.observedBeats;
    return raw.expectedBeats > 0 ? raw.expectedBeats : 0;
  }
  if (canonicalBeats > 0) return canonicalBeats;
  if (raw.expectedBeats > 0) return raw.expectedBeats;
  return raw.observedBeats;
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
