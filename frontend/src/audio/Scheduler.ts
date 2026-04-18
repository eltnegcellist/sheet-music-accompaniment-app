import * as Tone from "tone";

import type { MeasureTiming, NoteEvent } from "../types";

export interface ScheduleOptions {
  notes: NoteEvent[];
  measures: MeasureTiming[];
  sampler: Tone.Sampler;
  /** Called whenever the playhead enters a new measure. */
  onMeasureChange: (measureIndex: number) => void;
  /** 1-based measure to start from (inclusive). */
  startMeasure?: number;
  /** 1-based measure to end on (inclusive). */
  endMeasure?: number;
  loop?: boolean;
}

export interface ScheduledHandle {
  /** Tone Transport event ids we own and need to release. */
  ids: number[];
}

/** Convert a 1-based measure number to its starting beat in the score. */
export function measureToBeat(
  measures: MeasureTiming[],
  index: number,
): number {
  const m = measures.find((x) => x.index === index);
  if (m) return m.startBeat;
  // If the measure number isn't in the list, clamp to the nearest neighbour.
  if (measures.length === 0) return 0;
  if (index < measures[0].index) return measures[0].startBeat;
  const last = measures[measures.length - 1];
  return last.startBeat + last.lengthBeats;
}

/**
 * Schedule notes + measure callbacks on the Tone Transport.
 *
 * The Transport is left stopped; the caller decides when to start it (often
 * after a count-in). Use `cancelSchedule(handle)` to release events before
 * scheduling a new playback range.
 */
export function scheduleScore(opts: ScheduleOptions): ScheduledHandle {
  const {
    notes,
    measures,
    sampler,
    onMeasureChange,
    startMeasure,
    endMeasure,
    loop,
  } = opts;
  const ids: number[] = [];
  const transport = Tone.getTransport();

  const startBeat =
    startMeasure !== undefined ? measureToBeat(measures, startMeasure) : 0;
  const endBeat =
    endMeasure !== undefined
      ? measureToBeat(measures, endMeasure + 1)
      : measures.length > 0
        ? measures[measures.length - 1].startBeat +
          measures[measures.length - 1].lengthBeats
        : 0;

  const offset = startBeat;
  const playable = notes.filter((n) => n.beat >= startBeat && n.beat < endBeat);

  for (const note of playable) {
    const id = transport.schedule((t) => {
      sampler.triggerAttackRelease(
        note.pitch,
        toToneDuration(note.durationBeats),
        t,
        note.velocity,
      );
    }, beatsToBarsBeats(note.beat - offset));
    ids.push(id);
  }

  for (const m of measures) {
    if (m.startBeat < startBeat || m.startBeat >= endBeat) continue;
    const id = transport.schedule(() => {
      onMeasureChange(m.index);
    }, beatsToBarsBeats(m.startBeat - offset));
    ids.push(id);
  }

  if (loop) {
    transport.loop = true;
    transport.loopStart = 0;
    transport.loopEnd = beatsToBarsBeats(endBeat - offset);
  } else {
    transport.loop = false;
  }
  transport.position = 0;

  return { ids };
}

export function cancelSchedule(handle: ScheduledHandle): void {
  const transport = Tone.getTransport();
  for (const id of handle.ids) {
    transport.clear(id);
  }
  handle.ids = [];
  transport.cancel(0);
  transport.loop = false;
}

/**
 * Tone's Transport schedules in "bars:beats:sixteenths". We pass beats
 * directly to keep math simple — Tone accepts a "0:beat:0" style string.
 */
function beatsToBarsBeats(beats: number): string {
  // We use 4/4 time as the scheduling grid (this only affects how Tone
  // positions events, not the audible meter — actual note timings are exact).
  const bars = Math.floor(beats / 4);
  const remBeats = beats - bars * 4;
  return `${bars}:${remBeats}:0`;
}

function toToneDuration(beats: number): string {
  // Tone accepts "0:beats:0" form for arbitrary durations.
  return `0:${beats}:0`;
}
