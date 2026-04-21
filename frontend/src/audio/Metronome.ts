import * as Tone from "tone";

/** Simple click track with optional fermata suppression windows. */
export class Metronome {
  private synth: Tone.MembraneSynth;
  private accentSynth: Tone.MembraneSynth;
  private loopId: number | null = null;
  private enabled = false;
  private beatsPerBar = 4;
  private fermataWindows: Array<{ start: number; end: number }> = [];

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

  setFermataWindows(windows: Array<{ start: number; end: number }>): void {
    this.fermataWindows = windows.slice().sort((a, b) => a.start - b.start);
  }

  /** Schedule a click on every quarter note of the Tone Transport. */
  start(): void {
    this.stop();
    let beat = 0;
    // Elapsed beats since transport start — used to silence clicks that
    // happen while a fermata note is being sustained.
    let elapsedBeats = 0;
    this.loopId = Tone.getTransport().scheduleRepeat((time) => {
      const elapsed = elapsedBeats;
      elapsedBeats += 1;
      if (!this.enabled) {
        beat = (beat + 1) % this.beatsPerBar;
        return;
      }
      const isInFermataWindow = this.fermataWindows.some(
        (w) => elapsed >= w.start && elapsed < w.end,
      );
      if (isInFermataWindow) {
        beat = (beat + 1) % this.beatsPerBar;
        return;
      }
      const synth = beat === 0 ? this.accentSynth : this.synth;
      synth.triggerAttackRelease(beat === 0 ? "C5" : "C4", "32n", time);
      beat = (beat + 1) % this.beatsPerBar;
    }, "4n");
  }

  stop(): void {
    if (this.loopId !== null) {
      Tone.getTransport().clear(this.loopId);
      this.loopId = null;
    }
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
}
