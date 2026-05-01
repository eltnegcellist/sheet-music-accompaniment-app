import type { NoteEvent } from "../types";

export interface PositionResult {
  /** 1-based measure number. */
  measure: number;
  /** 0–1 confidence score. */
  confidence: number;
}

/** Experimental: matches recently detected pitches against the score to
 *  estimate the current playback position. */
export class ScoreFollower {
  private readonly soloNotes: NoteEvent[];
  /** [hz, capturedAtMs] */
  private pitchBuffer: Array<[number, number]> = [];
  private readonly WINDOW_MS = 2000;

  constructor(soloNotes: NoteEvent[]) {
    this.soloNotes = soloNotes;
  }

  addPitch(hz: number): void {
    const now = performance.now();
    this.pitchBuffer.push([hz, now]);
    // Evict entries older than WINDOW_MS
    const cutoff = now - this.WINDOW_MS;
    while (this.pitchBuffer.length > 0 && this.pitchBuffer[0][1] < cutoff) {
      this.pitchBuffer.shift();
    }
  }

  reset(): void {
    this.pitchBuffer = [];
  }

  /** Returns best matching measure or null if confidence < 0.5. */
  findBestMeasure(currentBpm: number): PositionResult | null {
    if (this.pitchBuffer.length < 3 || this.soloNotes.length === 0) return null;

    const detectedHz = this.pitchBuffer.map(([hz]) => hz);
    const detectedNotes = detectedHz.map(hzToNote).filter((n): n is string => n !== null);
    if (detectedNotes.length < 2) return null;

    // Convert BPM to seconds per beat
    const secPerBeat = 60 / currentBpm;

    // Build candidate windows: groups of soloNotes spanning ~2 seconds each
    const windowSec = this.WINDOW_MS / 1000;
    const measures = this.uniqueMeasures();
    let bestMeasure = measures[0];
    let bestScore = 0;

    for (const measureIdx of measures) {
      const windowNotes = this.soloNotesNear(measureIdx, secPerBeat, windowSec);
      if (windowNotes.length === 0) continue;
      const windowPitches = windowNotes.map((n) => n.pitch.replace(/\d$/, ""));
      const score = matchScore(detectedNotes.map((n) => n.replace(/\d$/, "")), windowPitches);
      if (score > bestScore) {
        bestScore = score;
        bestMeasure = measureIdx;
      }
    }

    if (bestScore < 0.5) return null;
    return { measure: bestMeasure, confidence: bestScore };
  }

  private uniqueMeasures(): number[] {
    const seen = new Set<number>();
    return this.soloNotes
      .map((n) => n.measureIndex)
      .filter((m) => { if (seen.has(m)) return false; seen.add(m); return true; });
  }

  private soloNotesNear(measureIdx: number, secPerBeat: number, windowSec: number): NoteEvent[] {
    const startNote = this.soloNotes.find((n) => n.measureIndex === measureIdx);
    if (!startNote) return [];
    const startBeat = startNote.beat;
    const endBeat = startBeat + windowSec / secPerBeat;
    return this.soloNotes.filter((n) => n.beat >= startBeat && n.beat < endBeat);
  }
}

/** Hz → note name without octave (e.g. "C"), or null if out of range. */
function hzToNote(hz: number): string | null {
  if (hz < 60 || hz > 2100) return null;
  const noteNames = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const midi = Math.round(12 * Math.log2(hz / 440) + 69);
  if (midi < 0 || midi > 127) return null;
  const octave = Math.floor(midi / 12) - 1;
  const name = noteNames[midi % 12];
  return `${name}${octave}`;
}

/** Proportion of detectedNotes that appear in windowNotes (order-insensitive). */
function matchScore(detected: string[], window: string[]): number {
  if (detected.length === 0 || window.length === 0) return 0;
  let hits = 0;
  for (const d of detected) {
    // Exact match = 1 point, octave-off = 0.5 points
    if (window.includes(d)) {
      hits += 1;
    } else if (window.some((w) => w === d)) {
      hits += 0.5;
    }
  }
  return hits / Math.max(detected.length, window.length);
}
