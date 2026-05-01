import type { NoteEvent } from "../types";

/** Convert scientific pitch notation (e.g. "C4", "D#5", "Bb3") to MIDI number. */
function pitchToMidi(pitch: string): number | null {
  const m = pitch.match(/^([A-G])([#b]?)(-?\d+)$/);
  if (!m) return null;
  const steps: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  const pc = steps[m[1]] + (m[2] === "#" ? 1 : m[2] === "b" ? -1 : 0);
  return (parseInt(m[3], 10) + 1) * 12 + pc;
}

/** Convert Hz to nearest MIDI note (A4 = 440 Hz = MIDI 69). */
function hzToMidi(hz: number): number | null {
  if (hz <= 0) return null;
  const midi = Math.round(12 * Math.log2(hz / 440) + 69);
  return midi >= 21 && midi <= 108 ? midi : null;
}

/** Fraction of detected MIDI notes matching a score window (±1 semitone, octave-insensitive). */
function matchScore(detected: number[], scoreMidis: number[]): number {
  if (detected.length === 0 || scoreMidis.length === 0) return 0;
  let hits = 0;
  for (let i = 0; i < detected.length && i < scoreMidis.length; i++) {
    const diff = Math.abs((detected[i] % 12) - (scoreMidis[i] % 12));
    if (diff <= 1 || diff === 11) hits++;
  }
  return hits / Math.max(detected.length, scoreMidis.length);
}

interface PitchOnset {
  midi: number;
  timeMs: number;
}

/**
 * Estimates tempo by matching a rolling pitch buffer against score notes.
 * Much more reliable than pure IOI-based detection because it uses actual
 * beat durations from the score rather than assuming every onset = one beat.
 */
export class TempoTracker {
  private scoreMidis: number[] = [];
  private scoreNotes: NoteEvent[] = [];

  private pitchBuffer: PitchOnset[] = [];
  private readonly BUFFER_MS = 6000;

  private appliedBpm = 100;
  private lastUpdateMs = 0;
  private readonly UPDATE_INTERVAL_MS = 2000;
  private readonly MAX_STEP_FRACTION = 0.05; // max 5% change per estimate

  onBpmChange?: (bpm: number) => void;

  setScore(notes: NoteEvent[]): void {
    this.scoreNotes = notes;
    this.scoreMidis = notes.map((n) => pitchToMidi(n.pitch) ?? -1);
  }

  reset(initialBpm: number): void {
    this.pitchBuffer = [];
    this.appliedBpm = initialBpm;
    this.lastUpdateMs = 0;
  }

  /** Call on each onset with the detected pitch at that moment. */
  addPitchOnset(hz: number, timeMs: number): void {
    const midi = hzToMidi(hz);
    if (midi === null) return;

    this.pitchBuffer.push({ midi, timeMs });
    const cutoff = timeMs - this.BUFFER_MS;
    while (this.pitchBuffer.length > 0 && this.pitchBuffer[0].timeMs < cutoff) {
      this.pitchBuffer.shift();
    }

    if (timeMs - this.lastUpdateMs < this.UPDATE_INTERVAL_MS) return;
    if (this.pitchBuffer.length < 4) return;
    this.lastUpdateMs = timeMs;

    const bpm = this.estimateFromBuffer();
    if (bpm !== null) this.applyBpm(bpm);
  }

  private estimateFromBuffer(): number | null {
    const buf = this.pitchBuffer;
    if (buf.length < 4 || this.scoreNotes.length < 4) return null;

    const realSpanMs = buf[buf.length - 1].timeMs - buf[0].timeMs;
    if (realSpanMs < 2000) return null;

    const detectedMidis = buf.map((p) => p.midi);
    const windowSize = Math.min(detectedMidis.length, 8);
    const detected = detectedMidis.slice(-windowSize);

    let bestScore = 0.45; // minimum confidence threshold
    let bestBeatSpan = 0;

    const maxStart = this.scoreNotes.length - windowSize;
    for (let start = 0; start <= maxStart; start++) {
      const window = this.scoreNotes.slice(start, start + windowSize);
      const windowMidis = this.scoreMidis.slice(start, start + windowSize);
      const score = matchScore(detected, windowMidis);
      if (score > bestScore) {
        bestScore = score;
        const first = window[0];
        const last = window[window.length - 1];
        bestBeatSpan = (last.beat + last.durationBeats) - first.beat;
      }
    }

    if (bestBeatSpan <= 0) return null;

    // Use the real-time span of the detected window, not the full buffer
    const detectedSpanMs = buf[buf.length - 1].timeMs - buf[buf.length - windowSize].timeMs;
    if (detectedSpanMs < 1000) return null;

    const bpm = (bestBeatSpan / (detectedSpanMs / 60000));
    if (bpm < 30 || bpm > 300) return null;
    return bpm;
  }

  private applyBpm(target: number): void {
    const maxDelta = this.appliedBpm * this.MAX_STEP_FRACTION;
    this.appliedBpm = target > this.appliedBpm
      ? Math.min(target, this.appliedBpm + maxDelta)
      : Math.max(target, this.appliedBpm - maxDelta);
    this.onBpmChange?.(Math.round(this.appliedBpm));
  }

  get currentAppliedBpm(): number { return this.appliedBpm; }
}
