import { describe, expect, it } from "vitest";
import { GraphicalVoiceEntry } from "opensheetmusicdisplay";
import "../osmdCompatibility";

describe("OSMD OMR rest compatibility", () => {
  it("sorts a mixed rest/note entry without accessing a missing Pitch", () => {
    const rest = { sourceNote: { Pitch: undefined } };
    const low = { sourceNote: { Pitch: { getHalfTone: () => 48 } } };
    const high = { sourceNote: { Pitch: { getHalfTone: () => 72 } } };
    // Invoke the real library method; constructing graphical staves is irrelevant
    // to the comparator that failed in the Mac error report.
    const entry = { notes: [rest, high, low] } as unknown as GraphicalVoiceEntry;
    expect(() => GraphicalVoiceEntry.prototype.sortForVexflow.call(entry)).not.toThrow();
    expect(entry.notes).toEqual([rest, low, high]);
    entry.notes.reverse();
    expect(GraphicalVoiceEntry.prototype.sortForVexflow.call(entry)).toEqual([rest, low, high]);
  });
});
