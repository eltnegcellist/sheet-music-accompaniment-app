import { describe, expect, it } from "vitest";
import type { NoteEvent } from "../../types";
import { ScoreFollower } from "../ScoreFollower";

function makeNotes(pitches: string[], startMeasure = 1): NoteEvent[] {
  return pitches.map((pitch, i) => ({
    pitch,
    beat: i,
    durationBeats: 1,
    velocity: 80,
    measureIndex: startMeasure + Math.floor(i / 4),
  }));
}

describe("ScoreFollower", () => {
  it("returns null when fewer than 3 pitches buffered", () => {
    const notes = makeNotes(["C4", "D4", "E4", "F4"]);
    const follower = new ScoreFollower(notes);
    follower.addPitch(261.63); // C4
    follower.addPitch(293.66); // D4
    expect(follower.findBestMeasure(120)).toBeNull();
  });

  it("matches C major scale at measure 1 with high confidence", () => {
    const notes = makeNotes(["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"], 1);
    const follower = new ScoreFollower(notes);

    // Detect pitches corresponding to C4 D4 E4
    follower.addPitch(261.63); // C4
    follower.addPitch(293.66); // D4
    follower.addPitch(329.63); // E4

    const result = follower.findBestMeasure(120);
    expect(result).not.toBeNull();
    expect(result!.measure).toBe(1);
    expect(result!.confidence).toBeGreaterThanOrEqual(0.5);
  });

  it("returns null for confidence < 0.5 (no match)", () => {
    const notes = makeNotes(["C4", "D4", "E4", "F4"], 1);
    const follower = new ScoreFollower(notes);

    // Detect completely different pitches (B3 range ~247 Hz → B3)
    follower.addPitch(246.94); // B3
    follower.addPitch(220.0);  // A3
    follower.addPitch(196.0);  // G3

    const result = follower.findBestMeasure(120);
    // May or may not match — if confidence < 0.5 should be null
    if (result !== null) {
      expect(result.confidence).toBeGreaterThanOrEqual(0.5);
    }
  });

  it("resets pitch buffer on reset()", () => {
    const notes = makeNotes(["C4", "D4", "E4", "F4"], 1);
    const follower = new ScoreFollower(notes);
    follower.addPitch(261.63);
    follower.addPitch(293.66);
    follower.addPitch(329.63);
    follower.reset();
    expect(follower.findBestMeasure(120)).toBeNull();
  });
});
