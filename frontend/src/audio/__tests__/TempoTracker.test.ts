import { describe, expect, it } from "vitest";
import { TempoTracker } from "../TempoTracker";

/** Feed evenly-spaced onsets at a given BPM, starting at t0. */
function feedOnsets(tracker: TempoTracker, bpm: number, count: number, t0 = 0): void {
  const interval = 60000 / bpm;
  for (let i = 0; i < count; i++) {
    tracker.handleOnset(t0 + i * interval);
  }
}

describe("TempoTracker", () => {
  it("emits BPM close to 120 after steady onsets", () => {
    const tracker = new TempoTracker();
    tracker.reset(100);
    let lastBpm: number | null = null;
    tracker.onBpmChange = (b) => { lastBpm = b; };

    feedOnsets(tracker, 120, 16, 0);
    expect(lastBpm).not.toBeNull();
    expect(lastBpm!).toBeGreaterThanOrEqual(110);
    expect(lastBpm!).toBeLessThanOrEqual(130);
  });

  it("ignores implausible IOIs (< 150 ms)", () => {
    const tracker = new TempoTracker();
    tracker.reset(120);
    let called = false;
    tracker.onBpmChange = () => { called = true; };

    // Send onsets 10 ms apart (way too fast)
    for (let i = 0; i < 8; i++) tracker.handleOnset(i * 10);
    expect(called).toBe(false);
  });

  it("rate-limits BPM changes per second", () => {
    const tracker = new TempoTracker();
    tracker.reset(100);
    const emitted: number[] = [];
    tracker.onBpmChange = (b) => emitted.push(b);

    // Feed 120 BPM onsets over 5 seconds
    feedOnsets(tracker, 120, 12, 0);

    // No single step should jump > 8% from 100 bpm
    for (let i = 1; i < emitted.length; i++) {
      const delta = Math.abs(emitted[i] - emitted[i - 1]);
      expect(delta).toBeLessThanOrEqual(emitted[i - 1] * 0.1); // 10% tolerance
    }
  });

  it("triggers catchup after two consecutive large divergences", () => {
    const tracker = new TempoTracker();
    tracker.reset(100);
    let lastBpm = 100;
    tracker.onBpmChange = (b) => { lastBpm = b; };

    // 200 BPM — very far from 100 BPM
    feedOnsets(tracker, 200, 16, 0);

    // After catchup, should be much closer to 200
    expect(lastBpm).toBeGreaterThan(130);
  });

  it("resets state on reset()", () => {
    const tracker = new TempoTracker();
    tracker.reset(100);
    feedOnsets(tracker, 120, 8, 0);
    tracker.reset(80);
    expect(tracker.currentAppliedBpm).toBe(80);
    expect(tracker.currentEstimatedBpm).toBe(80);
  });
});
