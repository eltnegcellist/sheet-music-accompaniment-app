import * as Tone from "tone";

/**
 * Simple click track. The "click" oscillator is intentionally short and high
 * pitched so it cuts through the piano sample. The first beat of each bar
 * uses a slightly higher pitch so it's audibly distinguishable as a downbeat.
 *
 * Fermata handling: a list of beat positions can be supplied. During a
 * window starting just before each fermata beat, the click is suppressed so
 * the user isn't distracted while holding the note; a single accent click
 * fires one beat before the next scheduled beat to give a clear "ready" cue.
 */
export class Metronome {
  private synth: Tone.MembraneSynth;
  private accentSynth: Tone.MembraneSynth;
  private loopId: number | null = null;
  private enabled = false;
  private beatsPerBar = 4;
  /** Absolute beat positions of fermata release points (in score beats). */
  private fermataBeats: number[] = [];

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

  setFermataBeats(beats: number[]): void {
    this.fermataBeats = beats.slice().sort((a, b) => a - b);
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
      // Suppress click while a fermata is being held: from the fermata's
      // original release beat (when the note would have ended without the
      // fermata) back one beat, and up to one beat forward. The exact window
      // is approximate — fermata duration is musically flexible — but this
      // keeps the click from fighting the soloist while preserving the
      // surrounding bar's pulse.
      const isInFermataWindow = this.fermataBeats.some(
        (f) => elapsed >= f - 1 && elapsed < f,
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
