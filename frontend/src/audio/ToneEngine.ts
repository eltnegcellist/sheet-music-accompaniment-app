import * as Tone from "tone";

/**
 * Lazily-constructed singletons so we don't re-fetch samples or rebuild synth
 * graphs on every page render.
 *
 * Piano: Salamander Grand Piano subset hosted by the Tone.js project.
 * Violin: a bowed-string-ish PolySynth (AM + sawtooth) with soft attack/
 *         release. A synth is used instead of real samples so the solo
 *         voice works offline and doesn't tie us to an external CDN for
 *         violin assets; the timbre is intentionally warm-but-clearly-
 *         distinct-from-piano so the solo line is easy to pick out from
 *         the accompaniment during rehearsal.
 */
let samplerPromise: Promise<Tone.Sampler> | null = null;

export function getPianoSampler(): Promise<Tone.Sampler> {
  if (samplerPromise) return samplerPromise;

  samplerPromise = new Promise((resolve, reject) => {
    const sampler = new Tone.Sampler({
      urls: {
        A0: "A0.mp3",
        C1: "C1.mp3",
        "D#1": "Ds1.mp3",
        "F#1": "Fs1.mp3",
        A1: "A1.mp3",
        C2: "C2.mp3",
        "D#2": "Ds2.mp3",
        "F#2": "Fs2.mp3",
        A2: "A2.mp3",
        C3: "C3.mp3",
        "D#3": "Ds3.mp3",
        "F#3": "Fs3.mp3",
        A3: "A3.mp3",
        C4: "C4.mp3",
        "D#4": "Ds4.mp3",
        "F#4": "Fs4.mp3",
        A4: "A4.mp3",
        C5: "C5.mp3",
        "D#5": "Ds5.mp3",
        "F#5": "Fs5.mp3",
        A5: "A5.mp3",
        C6: "C6.mp3",
        "D#6": "Ds6.mp3",
        "F#6": "Fs6.mp3",
        A6: "A6.mp3",
        C7: "C7.mp3",
        "D#7": "Ds7.mp3",
        "F#7": "Fs7.mp3",
        A7: "A7.mp3",
        C8: "C8.mp3",
      },
      release: 1,
      baseUrl: "https://tonejs.github.io/audio/salamander/",
      onload: () => resolve(sampler),
      onerror: (err) => reject(err),
    }).toDestination();
  });

  return samplerPromise;
}

/** Volume node for the solo/violin bus. The caller is expected to reuse the
 *  same instance across the application so volume changes propagate. */
export interface SoloBus {
  synth: Tone.PolySynth;
  volume: Tone.Volume;
}

let soloBusPromise: Promise<SoloBus> | null = null;

export function getViolinSynth(): Promise<SoloBus> {
  if (soloBusPromise) return soloBusPromise;

  soloBusPromise = new Promise((resolve) => {
    const volume = new Tone.Volume(0).toDestination();
    const synth = new Tone.PolySynth(Tone.AMSynth, {
      // A saw-based carrier with a slight amplitude modulation reads as a
      // bowed string more than a piano, which is what we need so the user
      // can pick the solo voice out from the accompaniment by ear.
      harmonicity: 1.5,
      oscillator: { type: "sawtooth" },
      envelope: { attack: 0.08, decay: 0.1, sustain: 0.7, release: 0.4 },
      modulation: { type: "sine" },
      modulationEnvelope: {
        attack: 0.2,
        decay: 0.2,
        sustain: 0.5,
        release: 0.3,
      },
    });
    synth.connect(volume);
    resolve({ synth, volume });
  });

  return soloBusPromise;
}

/** Convert a "normal" | "karaoke" | "off" selection to a dB value. */
export function soloVolumeToDb(
  mode: "normal" | "karaoke" | "off",
): number {
  switch (mode) {
    case "normal":
      return 0;
    case "karaoke":
      return -18;
    case "off":
      return -Infinity;
  }
}

/** Resume the AudioContext on a user gesture (required by browsers). */
export async function ensureAudioRunning(): Promise<void> {
  if (Tone.getContext().state !== "running") {
    await Tone.start();
  }
}
