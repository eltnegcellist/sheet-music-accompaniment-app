import { describe, expect, it } from "vitest";
import { TempoTracker } from "../TempoTracker";
import type { NoteEvent } from "../../types";

/** Build a simple scale of NoteEvent objects at a given BPM. */
function buildNotes(pitches: string[], _bpm: number, startBeat = 0): NoteEvent[] {
  return pitches.map((pitch, i) => ({
    pitch,
    beat: startBeat + i,
    durationBeats: 1,
    velocity: 80,
    measureIndex: Math.floor(i / 4) + 1,
  }));
}

/** Feed pitch onsets at a given BPM as if a musician played them. */
function feedOnsets(tracker: TempoTracker, pitches: string[], bpm: number, t0 = 0): void {
  const msBeat = 60000 / bpm;
  // Simple Hz lookup for test pitches (only notes used in tests)
  const hzMap: Record<string, number> = {
    C4: 261.63, D4: 293.66, E4: 329.63, F4: 349.23,
    G4: 392.00, A4: 440.00, B4: 493.88, C5: 523.25,
    D5: 587.33, E5: 659.25,
  };
  pitches.forEach((pitch, i) => {
    const hz = hzMap[pitch] ?? 440;
    tracker.addPitchOnset(hz, t0 + i * msBeat);
  });
}

const SCALE = ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"];

describe("TempoTracker", () => {
  it("emits BPM close to target when playing score at that tempo", () => {
    const tracker = new TempoTracker();
    tracker.reset(100);
    tracker.setScore(buildNotes(SCALE, 120));
    let lastBpm: number | null = null;
    tracker.onBpmChange = (b) => { lastBpm = b; };

    // Feed at 120 BPM starting at 2000ms (so span ≥ 2s within 6s buffer)
    feedOnsets(tracker, SCALE, 120, 0);
    // Second onset batch after UPDATE_INTERVAL_MS to trigger estimate
    feedOnsets(tracker, SCALE, 120, 2001);

    expect(lastBpm).not.toBeNull();
    expect(lastBpm!).toBeGreaterThanOrEqual(90);
    expect(lastBpm!).toBeLessThanOrEqual(130);
  });

  it("does not emit when pitch buffer has fewer than 4 onsets", () => {
    const tracker = new TempoTracker();
    tracker.reset(120);
    tracker.setScore(buildNotes(SCALE, 120));
    let called = false;
    tracker.onBpmChange = () => { called = true; };

    tracker.addPitchOnset(440, 0);
    tracker.addPitchOnset(440, 500);
    tracker.addPitchOnset(440, 1000);
    expect(called).toBe(false);
  });

  it("rate-limits changes to max 5% per update", () => {
    const tracker = new TempoTracker();
    tracker.reset(100);
    tracker.setScore(buildNotes(SCALE, 200));
    const emitted: number[] = [];
    tracker.onBpmChange = (b) => emitted.push(b);

    feedOnsets(tracker, SCALE, 200, 0);
    feedOnsets(tracker, SCALE, 200, 2001);
    feedOnsets(tracker, SCALE, 200, 4002);

    for (let i = 1; i < emitted.length; i++) {
      const delta = Math.abs(emitted[i] - emitted[i - 1]);
      // Each step should be ≤ 5% of previous
      expect(delta).toBeLessThanOrEqual(emitted[i - 1] * 0.06);
    }
  });

  it("resets state on reset()", () => {
    const tracker = new TempoTracker();
    tracker.reset(100);
    tracker.setScore(buildNotes(SCALE, 120));
    feedOnsets(tracker, SCALE, 120, 0);
    tracker.reset(80);
    expect(tracker.currentAppliedBpm).toBe(80);
  });

  it("does not emit when no score is set", () => {
    const tracker = new TempoTracker();
    tracker.reset(100);
    let called = false;
    tracker.onBpmChange = () => { called = true; };

    feedOnsets(tracker, SCALE, 120, 0);
    feedOnsets(tracker, SCALE, 120, 2001);
    expect(called).toBe(false);
  });
});
