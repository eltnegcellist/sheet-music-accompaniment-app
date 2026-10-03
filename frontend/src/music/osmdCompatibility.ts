import { GraphicalVoiceEntry } from "opensheetmusicdisplay";

// OSMD 1.9.7 guards Pitch on only one side of its VexFlow comparator.
// Mixed rest/note entries from OMR can therefore throw in getHalfTone.
// Preserve its ordering and its treatment of rests (0) on both sides.
GraphicalVoiceEntry.prototype.sortForVexflow = function () {
  return this.notes.sort((a, b) =>
    (a.sourceNote.Pitch?.getHalfTone() ?? 0) -
    (b.sourceNote.Pitch?.getHalfTone() ?? 0),
  );
};
