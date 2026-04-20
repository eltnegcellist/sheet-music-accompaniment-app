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
): {
  notes: NoteEvent[];
  measures: MeasureTiming[];
  /** Absolute beat positions at which a fermata is held. Useful for
   *  pausing the metronome click while the note is sustained. */
  fermataBeats: number[];
} {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const parseError = doc.querySelector("parsererror");
  if (parseError) {
    throw new Error("Failed to parse MusicXML");
  }

  const part = pickPart(doc, partId);
  if (!part) {
    return { notes: [], measures: [], fermataBeats: [] };
  }

  const rawMeasures = collectRawMeasures(part);
  const canonicalBeats = computeCanonicalBeats(rawMeasures);

  const measures: MeasureTiming[] = [];
  const notes: NoteEvent[] = [];
  const fermataBeats: number[] = [];
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

    // Fermata stretch within this measure: extend the measure's length so
    // subsequent measures stay aligned with audio, and stretch the fermata
    // note itself so it's audibly longer. We use 1.75× (+75%) as a reasonable
    // middle-of-the-road duration; real fermatas vary but this matches
    // common rehearsal practice.
    let measureFermataExtra = 0;
    for (const n of raw.notes) {
      if (n.hasFermata) {
        const extra = n.durationBeats * 0.75;
        measureFermataExtra += extra;
        // Also log the absolute beat so we can pause metronome mid-bar.
        fermataBeats.push(elapsedBeats + n.relativeBeats + n.durationBeats);
        n.durationBeats += extra;
      }
    }

    measures.push({
      index: raw.index,
      startBeat: elapsedBeats,
      lengthBeats: lengthBeats + measureFermataExtra,
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

    elapsedBeats += lengthBeats + measureFermataExtra;
  }

  notes.sort((a, b) => a.beat - b.beat);
  return { notes, measures, fermataBeats };
}

interface RawNote {
  /** Offset from the start of the owning measure, in beats. */
  relativeBeats: number;
  durationBeats: number;
  pitch: string;
  velocity: number;
  measureIndex: number;
  hasFermata: boolean;
}

interface RawMeasure {
  index: number;
  isImplicit: boolean;
  observedBeats: number;
  /** Length suggested by the active <time> signature, in beats. 0 if unknown. */
  expectedBeats: number;
  notes: RawNote[];
}

// Velocity (0..1) table for MusicXML dynamic marks. The curve is mildly
// compressed compared to the MIDI spec so that `pp` is still audible over the
// metronome click and `ff` doesn't clip the default master gain.
const DYNAMIC_VELOCITY: Record<string, number> = {
  ppp: 0.2,
  pp: 0.3,
  p: 0.45,
  mp: 0.6,
  mf: 0.75,
  f: 0.85,
  ff: 0.95,
  fff: 1.0,
  sf: 0.95,
  sfz: 0.95,
  fp: 0.85,
};

const DEFAULT_VELOCITY = DYNAMIC_VELOCITY.mf;

function collectRawMeasures(part: Element): RawMeasure[] {
  const out: RawMeasure[] = [];
  let divisions = 1; // ticks per quarter; updated when <attributes><divisions>
  let expectedMeasureTicks = 0;
  // Running dynamic level (carried across measures). Default = mf.
  let currentVelocity = DEFAULT_VELOCITY;

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
        case "direction": {
          const dyn = readDynamic(child);
          if (dyn !== null) currentVelocity = dyn;
          break;
        }
        case "sound": {
          // <sound dynamics="NN"/> directly — MIDI-style 0..127 scale.
          const dyn = child.getAttribute("dynamics");
          if (dyn) {
            const parsed = Number.parseFloat(dyn);
            if (Number.isFinite(parsed) && parsed > 0) {
              currentVelocity = Math.min(1, parsed / 127);
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
          const hasFermata = hasFermataNotation(child);

          if (!isRest) {
            const pitch = readPitch(child);
            if (pitch) {
              rawNotes.push({
                relativeBeats: ticksToBeats(noteStartTicks, divisions),
                durationBeats: ticksToBeats(dur, divisions),
                pitch,
                velocity: currentVelocity,
                measureIndex,
                hasFermata,
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

/**
 * Inspect a <direction> for a <dynamics> child (the usual MusicXML location).
 * Also honours an explicit <sound dynamics="NN"/> inside the direction, which
 * some engravers use to override the dynamic tag's default velocity.
 *
 * Audiveris, annoyingly, frequently emits dynamics as italic *text* instead
 * of proper <dynamics> tags — so we also look at <words>p</words>,
 * <words>ff</words>, etc. This is the path that matters in practice: the
 * Elgar "Salut d'Amour" test score, for instance, has every dynamic marking
 * represented as <words> rather than <dynamics>.
 */
function readDynamic(directionEl: Element): number | null {
  const dynamicsEl = directionEl.getElementsByTagName("dynamics")[0];
  if (dynamicsEl) {
    for (const child of Array.from(dynamicsEl.children)) {
      const key = child.tagName.toLowerCase();
      if (key in DYNAMIC_VELOCITY) return DYNAMIC_VELOCITY[key];
    }
    // Some exporters write <dynamics>p</dynamics> with no child tags.
    const text = (dynamicsEl.textContent ?? "").trim().toLowerCase();
    if (text && text in DYNAMIC_VELOCITY) return DYNAMIC_VELOCITY[text];
  }
  // Audiveris-style: <words>p</words>, <words>ff</words>, …
  const wordEls = directionEl.getElementsByTagName("words");
  for (const el of Array.from(wordEls)) {
    const raw = (el.textContent ?? "").trim().toLowerCase();
    // Strip trailing punctuation ("p.") and look up.
    const cleaned = raw.replace(/[^a-z]/g, "");
    if (cleaned && cleaned in DYNAMIC_VELOCITY) {
      return DYNAMIC_VELOCITY[cleaned];
    }
  }
  const soundEl = directionEl.getElementsByTagName("sound")[0];
  if (soundEl) {
    const dyn = soundEl.getAttribute("dynamics");
    if (dyn) {
      const parsed = Number.parseFloat(dyn);
      if (Number.isFinite(parsed) && parsed > 0) {
        return Math.min(1, parsed / 127);
      }
    }
  }
  return null;
}

function hasFermataNotation(noteEl: Element): boolean {
  const notationsList = noteEl.getElementsByTagName("notations");
  for (const n of Array.from(notationsList)) {
    if (n.getElementsByTagName("fermata").length > 0) return true;
  }
  return false;
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
