import type { FermataWindow, MeasureTiming, NoteEvent } from "../types";

export function parseScore(
  xml: string,
  accompanimentPartId: string | null,
  soloPartId: string | null,
): {
  accNotes: NoteEvent[];
  soloNotes: NoteEvent[];
  measures: MeasureTiming[];
  fermataWindows: FermataWindow[];
} {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const parseError = doc.querySelector("parsererror");
  if (parseError) throw new Error("Failed to parse MusicXML");

  const accPart = pickPart(doc, accompanimentPartId);
  const soloPart = soloPartId ? pickPart(doc, soloPartId) : null;

  const accMeasures = accPart ? collectRawMeasures(accPart) : [];
  const soloMeasures = soloPart ? collectRawMeasures(soloPart) : [];
  const canonicalBeats = computeCanonicalBeats([...accMeasures, ...soloMeasures]);

  const accNotes: NoteEvent[] = [];
  const soloNotes: NoteEvent[] = [];
  const measures: MeasureTiming[] = [];
  const fermataWindows: FermataWindow[] = [];
  let elapsedBeats = 0;

  // IMPORTANT: align parts by *measure order*, not by measure@number.
  // Some sources contain duplicate/non-numeric numbering; index-based lookups
  // can drop later measures and gradually erase notes during playback.
  const totalMeasures = Math.max(accMeasures.length, soloMeasures.length);
  for (let measurePos = 0; measurePos < totalMeasures; measurePos++) {
    const accM = accMeasures[measurePos];
    const soloM = soloMeasures[measurePos];
    const mForLength = accM ?? soloM;
    if (!mForLength) continue;
    const index = mForLength.index;

    const baseLength = pickMeasureLength(mForLength, canonicalBeats);
    const allRawNotes = [...(accM?.notes ?? []), ...(soloM?.notes ?? [])];

    const fermataShifts = new Map<number, number>();
    for (const n of allRawNotes) {
      if (!n.hasFermata) continue;
      const extra = n.durationBeats * 0.75;
      const endBeat = Math.round((n.relativeBeats + n.durationBeats) * 1000) / 1000;
      fermataShifts.set(endBeat, Math.max(fermataShifts.get(endBeat) ?? 0, extra));
      fermataWindows.push({
        start: elapsedBeats + n.relativeBeats + n.durationBeats,
        end: elapsedBeats + n.relativeBeats + n.durationBeats + extra,
      });
    }

    const getShiftForBeat = (beat: number) => {
      let shift = 0;
      for (const [endBeat, extra] of fermataShifts.entries()) {
        if (beat >= endBeat - 1e-4) shift += extra;
      }
      return shift;
    };

    const pushNotes = (rawNotes: RawNote[], targetArray: NoteEvent[]) => {
      for (const n of rawNotes) {
        const shift = getShiftForBeat(n.relativeBeats);
        const endKey = Math.round((n.relativeBeats + n.durationBeats) * 1000) / 1000;
        const selfExtra = n.hasFermata ? (fermataShifts.get(endKey) ?? 0) : 0;
        targetArray.push({
          beat: elapsedBeats + n.relativeBeats + shift,
          durationBeats: n.durationBeats + selfExtra,
          pitch: n.pitch,
          velocity: n.velocity,
          measureIndex: index,
        });
      }
    };

    if (accM) pushNotes(accM.notes, accNotes);
    if (soloM) pushNotes(soloM.notes, soloNotes);

    let totalShift = 0;
    for (const extra of fermataShifts.values()) totalShift += extra;

    measures.push({ index, startBeat: elapsedBeats, lengthBeats: baseLength + totalShift });
    elapsedBeats += baseLength + totalShift;
  }

  accNotes.sort((a, b) => a.beat - b.beat);
  soloNotes.sort((a, b) => a.beat - b.beat);
  fermataWindows.sort((a, b) => a.start - b.start);
  return { accNotes, soloNotes, measures, fermataWindows };
}

export function parseMusicXml(
  xml: string,
  partId: string | null,
): { notes: NoteEvent[]; measures: MeasureTiming[]; fermataBeats: number[] } {
  // Keep this parser path intentionally independent from parseScore().
  // In practice this has proven the most stable scheduling source for each
  // individual part during long-form playback.
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const parseError = doc.querySelector("parsererror");
  if (parseError) throw new Error("Failed to parse MusicXML");

  const part = pickPart(doc, partId);
  if (!part) return { notes: [], measures: [], fermataBeats: [] };

  const rawMeasures = collectRawMeasures(part);
  const canonicalBeats = computeCanonicalBeats(rawMeasures);
  const notes: NoteEvent[] = [];
  const measures: MeasureTiming[] = [];
  const fermataBeats: number[] = [];
  let elapsedBeats = 0;

  for (const raw of rawMeasures) {
    const lengthBeats = pickMeasureLength(raw, canonicalBeats);
    let measureFermataExtra = 0;

    measures.push({
      index: raw.index,
      startBeat: elapsedBeats,
      lengthBeats: lengthBeats,
    });

    for (const n of raw.notes) {
      const selfExtra = n.hasFermata ? n.durationBeats * 0.75 : 0;
      if (n.hasFermata) {
        measureFermataExtra += selfExtra;
        fermataBeats.push(elapsedBeats + n.relativeBeats + n.durationBeats);
      }
      notes.push({
        beat: elapsedBeats + n.relativeBeats,
        durationBeats: n.durationBeats + selfExtra,
        pitch: n.pitch,
        velocity: n.velocity,
        measureIndex: n.measureIndex,
      });
    }

    measures[measures.length - 1].lengthBeats += measureFermataExtra;
    elapsedBeats += lengthBeats + measureFermataExtra;
  }

  notes.sort((a, b) => a.beat - b.beat);
  return { notes, measures, fermataBeats };
}

interface RawNote {
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
  expectedBeats: number;
  notes: RawNote[];
}

const DYNAMIC_VELOCITY: Record<string, number> = {
  ppp: 0.05,
  pp: 0.15,
  p: 0.3,
  mp: 0.45,
  mf: 0.6,
  f: 0.75,
  ff: 0.9,
  fff: 1.0,
  sf: 0.95,
  sfz: 0.95,
  fp: 0.4,
};
const DEFAULT_VELOCITY = DYNAMIC_VELOCITY.mf;

function collectRawMeasures(part: Element): RawMeasure[] {
  const out: RawMeasure[] = [];
  let divisions = 1;
  let expectedMeasureTicks = 0;
  let currentVelocity = DEFAULT_VELOCITY;
  for (const measureEl of Array.from(part.getElementsByTagName("measure"))) {
    const measureIndex = Number(measureEl.getAttribute("number") ?? "0") || 0;
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
            if (Number.isFinite(parsed) && parsed > 0) divisions = parsed;
          }
          const timeEl = child.getElementsByTagName("time")[0];
          if (timeEl) {
            const beats = Number.parseInt(timeEl.getElementsByTagName("beats")[0]?.textContent ?? "",10);
            const beatType = Number.parseInt(timeEl.getElementsByTagName("beat-type")[0]?.textContent ?? "",10);
            if (Number.isFinite(beats) && beats > 0 && Number.isFinite(beatType) && beatType > 0) {
              expectedMeasureTicks = Math.round((beats * divisions * 4) / beatType);
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
          const dyn = child.getAttribute("dynamics");
          if (dyn) {
            const parsed = Number.parseFloat(dyn);
            if (Number.isFinite(parsed) && parsed > 0) currentVelocity = Math.min(1, parsed / 127);
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
          const noteStartTicks = isChord ? cursorTicks - dur : cursorTicks;
          const hasFermata = hasFermataNotation(child);
          if (!isRest) {
            const pitch = readPitch(child);
            if (pitch) {
              rawNotes.push({ relativeBeats: ticksToBeats(noteStartTicks, divisions), durationBeats: ticksToBeats(dur, divisions), pitch, velocity: currentVelocity, measureIndex, hasFermata });
            }
          }
          if (!isChord) {
            cursorTicks += dur;
            measureLengthTicks = Math.max(measureLengthTicks, cursorTicks);
          }
        }
      }
    }
    out.push({
      index: measureIndex,
      isImplicit,
      observedBeats: ticksToBeats(measureLengthTicks, divisions),
      expectedBeats: expectedMeasureTicks > 0 ? ticksToBeats(expectedMeasureTicks, divisions) : 0,
      notes: rawNotes,
    });
  }
  return out;
}

function computeCanonicalBeats(measures: RawMeasure[]): number {
  const counts = new Map<number, number>();
  for (const m of measures) {
    if (m.isImplicit || m.observedBeats <= 0) continue;
    const key = Math.round(m.observedBeats * 1000) / 1000;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  if (!counts.size) return 0;
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
  if (raw.isImplicit) return raw.observedBeats > 0 ? raw.observedBeats : raw.expectedBeats;
  if (canonicalBeats > 0) return canonicalBeats;
  if (raw.expectedBeats > 0) return raw.expectedBeats;
  return raw.observedBeats;
}

function pickPart(doc: Document, partId: string | null): Element | null {
  const parts = Array.from(doc.getElementsByTagName("part"));
  if (!parts.length) return null;
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
function readDynamic(directionEl: Element): number | null {
  const dynamicsEl = directionEl.getElementsByTagName("dynamics")[0];
  if (dynamicsEl) {
    for (const child of Array.from(dynamicsEl.children)) {
      const key = child.tagName.toLowerCase();
      if (key in DYNAMIC_VELOCITY) return DYNAMIC_VELOCITY[key];
    }
    const text = (dynamicsEl.textContent ?? "").trim().toLowerCase();
    if (text && text in DYNAMIC_VELOCITY) return DYNAMIC_VELOCITY[text];
  }
  const wordEls = directionEl.getElementsByTagName("words");
  for (const el of Array.from(wordEls)) {
    const cleaned = ((el.textContent ?? "").trim().toLowerCase()).replace(/[^a-z]/g, "");
    if (cleaned && cleaned in DYNAMIC_VELOCITY) return DYNAMIC_VELOCITY[cleaned];
  }
  const soundEl = directionEl.getElementsByTagName("sound")[0];
  if (soundEl) {
    const dyn = soundEl.getAttribute("dynamics");
    if (dyn) {
      const parsed = Number.parseFloat(dyn);
      if (Number.isFinite(parsed) && parsed > 0) return Math.min(1, parsed / 127);
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
const STEP_TO_SEMITONE: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const SEMITONE_TO_NAME = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function readPitch(noteEl: Element): string | null {
  const pitchEl = noteEl.getElementsByTagName("pitch")[0];
  if (!pitchEl) return null;
  const step = pitchEl.getElementsByTagName("step")[0]?.textContent ?? "";
  const octave = Number.parseInt(pitchEl.getElementsByTagName("octave")[0]?.textContent ?? "", 10);
  const alterText = pitchEl.getElementsByTagName("alter")[0]?.textContent;
  if (!(step in STEP_TO_SEMITONE) || !Number.isFinite(octave)) return null;
  const alter = alterText ? Number.parseInt(alterText, 10) : 0;
  const base = STEP_TO_SEMITONE[step] + alter;
  const normalized = ((base % 12) + 12) % 12;
  const octaveShift = Math.floor(base / 12);
  return `${SEMITONE_TO_NAME[normalized]}${octave + octaveShift}`;
}
