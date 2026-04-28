import { describe, expect, it } from "vitest";

import {
  expandRepeats,
  type MeasureRepeatMeta,
} from "../repeatExpander";

function meta(
  index: number,
  patch: Partial<MeasureRepeatMeta> = {},
): MeasureRepeatMeta {
  return {
    index,
    forwardRepeat: false,
    backwardRepeat: null,
    endingStarts: [],
    endingStops: [],
    hasSegno: false,
    hasCoda: false,
    fine: false,
    toCoda: false,
    jump: null,
    ...patch,
  };
}

function order(slots: { measureIndex: number }[]): number[] {
  return slots.map((s) => s.measureIndex);
}

describe("expandRepeats", () => {
  it("returns the input unchanged when there are no repeats", () => {
    const ms = [meta(1), meta(2), meta(3)];
    expect(order(expandRepeats(ms))).toEqual([1, 2, 3]);
  });

  it("plays |: 2 3 :| as 2 3 2 3", () => {
    const ms = [
      meta(1),
      meta(2, { forwardRepeat: true }),
      meta(3, { backwardRepeat: 2 }),
      meta(4),
    ];
    expect(order(expandRepeats(ms))).toEqual([1, 2, 3, 2, 3, 4]);
  });

  it("repeats from start when no explicit forward marker is present", () => {
    const ms = [meta(1), meta(2, { backwardRepeat: 2 }), meta(3)];
    expect(order(expandRepeats(ms))).toEqual([1, 2, 1, 2, 3]);
  });

  it("honours times>2 on backward-repeat", () => {
    const ms = [
      meta(1, { forwardRepeat: true }),
      meta(2, { backwardRepeat: 4 }),
    ];
    // First pass + 3 additional repeats = 4 total visits.
    expect(order(expandRepeats(ms))).toEqual([1, 2, 1, 2, 1, 2, 1, 2]);
  });

  it("selects volta brackets per pass", () => {
    // |: 2 [1. 3] :| [2. 4] 5
    const ms = [
      meta(1),
      meta(2, { forwardRepeat: true }),
      meta(3, { endingStarts: [1], endingStops: [1], backwardRepeat: 2 }),
      meta(4, { endingStarts: [2], endingStops: [2] }),
      meta(5),
    ];
    expect(order(expandRepeats(ms))).toEqual([1, 2, 3, 2, 4, 5]);
  });

  it("Da Capo al Fine returns to top and stops at Fine", () => {
    const ms = [
      meta(1),
      meta(2, { fine: true }),
      meta(3),
      meta(4, { jump: "da-capo-al-fine" }),
    ];
    expect(order(expandRepeats(ms))).toEqual([1, 2, 3, 4, 1, 2]);
  });

  it("Dal Segno al Coda jumps to segno then to coda on second pass", () => {
    const ms = [
      meta(1),
      meta(2, { hasSegno: true }),
      meta(3, { toCoda: true }),
      meta(4),
      meta(5, { jump: "dal-segno-al-coda" }),
      meta(6, { hasCoda: true }),
      meta(7),
    ];
    expect(order(expandRepeats(ms))).toEqual([
      1,
      2,
      3,
      4,
      5,
      2,
      3,
      6,
      7,
    ]);
  });

  it("does not loop forever when D.C. lives next to a backward-repeat", () => {
    // Even pathological combinations are bounded by `dcDsTaken`.
    const ms = [
      meta(1),
      meta(2, { backwardRepeat: 2, jump: "da-capo" }),
      meta(3),
    ];
    const slots = expandRepeats(ms, { maxSlots: 100 });
    // Backward repeat fires once, then D.C. fires once; we should NOT see a
    // third revisit of the backward.
    expect(slots.length).toBeLessThan(20);
    expect(order(slots)[0]).toBe(1);
  });

  it("respects the maxSlots safety cap", () => {
    const ms = [
      meta(1, { forwardRepeat: true }),
      meta(2, { backwardRepeat: 100 }),
    ];
    const slots = expandRepeats(ms, { maxSlots: 7 });
    expect(slots.length).toBeLessThanOrEqual(7);
  });

  it("handles multi-number volta brackets like 1.,2.", () => {
    const ms = [
      meta(1, { forwardRepeat: true }),
      meta(2, { endingStarts: [1, 2], endingStops: [1, 2], backwardRepeat: 3 }),
      meta(3, { endingStarts: [3], endingStops: [3] }),
      meta(4),
    ];
    // First pass: 1, 2 (matches 1), back to 1
    // Second pass: 1, 2 (matches 2), back to 1
    // Third pass: 1, skip 2 (3 doesn't match), 3, 4.
    expect(order(expandRepeats(ms))).toEqual([
      1, 2, 1, 2, 1, 3, 4,
    ]);
  });
});
