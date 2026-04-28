import * as Tone from "tone";

import type { FermataWindow, MeasureTiming } from "../types";

/**
 * Click track tied to the score's measure timeline.
 *
 * Earlier revisions used `Transport.scheduleRepeat("4n")`, which fires on a
 * fixed quarter-note grid. That's fine for a constant-tempo score, but every
 * fermata stretches a measure by the parsed extension (~75% of the held
 * note's duration) — and once the measure timeline is no longer aligned with
 * the integer-beat grid the metronome ends up running ahead of (or behind)
 * the accompaniment, depending on how the fermata duration rounds.
 *
 * We instead pre-compute the absolute beat positions where the metronome
 * should click — derived from `MeasureTiming.startBeat` / `lengthBeats`
 * (which already reflect every fermata extension applied during parsing) —
 * and schedule one Transport event per click. This guarantees the metronome,
 * accompaniment and solo all consume the same timeline; no drift can
 * accumulate after a fermata.
 */
export class Metronome {
  private synth: Tone.MembraneSynth;
  private accentSynth: Tone.MembraneSynth;
  private scheduledIds: number[] = [];
  private enabled = false;
  private beatsPerBar = 4;
  private fermataWindows: FermataWindow[] = [];
  private measures: MeasureTiming[] = [];
  private offsetBeats = 0;

  constructor() {
    this.synth = new Tone.MembraneSynth({
      pitchDecay: 0.008,
      octaves: 2,
      envelope: { attack: 0.001, decay: 0.1, sustain: 0, release: 0.1 },
    }).toDestination();
    this.accentSynth = new Tone.MembraneSynth({
      pitchDecay: 0.008,
      octaves: 4,
      envelope: { attack: 0.001, decay: 0.1, sustain: 0, release: 0.1 },
    }).toDestination();
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  setBeatsPerBar(beats: number): void {
    this.beatsPerBar = Math.max(1, Math.floor(beats));
  }

  setFermataWindows(windows: FermataWindow[]): void {
    this.fermataWindows = windows.slice().sort((a, b) => a.start - b.start);
  }

  /**
   * Tell the metronome which measures it should click through. `offsetBeats`
   * is the absolute beat at which playback starts on the Transport, so we can
   * subtract it when scheduling — if the user only plays from measure 5, we
   * still want the click on its first beat instead of waiting for the
   * imaginary "measure 1" to elapse.
   */
  setMeasures(measures: MeasureTiming[], offsetBeats: number): void {
    this.measures = measures;
    this.offsetBeats = offsetBeats;
  }

  /** Schedule one click per beat across the configured measure list. */
  start(): void {
    this.stop();
    if (this.measures.length === 0) return;
    const transport = Tone.getTransport();

    // Per-measure beat positions — important: derive beat count from the
    // measure's lengthBeats, NOT from beatsPerBar, so fermata-extended
    // measures don't accumulate stray clicks during the held note.
    for (let i = 0; i < this.measures.length; i++) {
      const m = this.measures[i];
      const baseBars = Math.max(
        1,
        Math.floor(m.lengthBeats / Math.max(1, this.beatsPerBar)),
      );
      const beatsInMeasure =
        baseBars * this.beatsPerBar > m.lengthBeats + 1e-3
          ? Math.max(1, Math.floor(m.lengthBeats))
          : baseBars * this.beatsPerBar;

      for (let b = 0; b < beatsInMeasure; b++) {
        const absoluteBeat = m.startBeat + b;
        if (absoluteBeat >= m.startBeat + m.lengthBeats - 1e-3) break;
        if (this.isInFermataWindow(absoluteBeat)) continue;
        const transportBeat = absoluteBeat - this.offsetBeats;
        if (transportBeat < -1e-4) continue;
        const isAccent = b === 0;
        const id = transport.schedule((time) => {
          if (!this.enabled) return;
          const synth = isAccent ? this.accentSynth : this.synth;
          synth.triggerAttackRelease(isAccent ? "C5" : "C4", "32n", time);
        }, beatsToTransportTime(transportBeat));
        this.scheduledIds.push(id);
      }
    }
  }

  stop(): void {
    const transport = Tone.getTransport();
    for (const id of this.scheduledIds) transport.clear(id);
    this.scheduledIds = [];
  }

  /**
   * Play a count-in of `bars` bars before resolving. Returns the time (in
   * Transport seconds) at which the actual playback should begin.
   */
  async countIn(bars: number, bpm: number): Promise<number> {
    if (bars <= 0) return Tone.now();
    const secondsPerBeat = 60 / bpm;
    const totalBeats = bars * this.beatsPerBar;
    const startTime = Tone.now() + 0.05;
    for (let i = 0; i < totalBeats; i++) {
      const t = startTime + i * secondsPerBeat;
      const isAccent = i % this.beatsPerBar === 0;
      (isAccent ? this.accentSynth : this.synth).triggerAttackRelease(
        isAccent ? "C5" : "C4",
        "32n",
        t,
      );
    }
    return startTime + totalBeats * secondsPerBeat;
  }

  private isInFermataWindow(beat: number): boolean {
    for (const w of this.fermataWindows) {
      if (beat >= w.start - 1e-4 && beat < w.end - 1e-4) return true;
    }
    return false;
  }
}

function beatsToTransportTime(beats: number): string {
  // Tone accepts "bars:beats:sixteenths"; we use a 4-beat grid so converting
  // arbitrary beat positions is straightforward. Negative values are clamped
  // by the caller above.
  const safe = Math.max(0, beats);
  const bars = Math.floor(safe / 4);
  const remBeats = safe - bars * 4;
  return `${bars}:${remBeats}:0`;
}
