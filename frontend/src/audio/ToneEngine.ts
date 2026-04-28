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

/** Anything we can use as the solo instrument. Both Tone.Sampler and
 *  Tone.PolySynth satisfy this — keep the surface narrow so the scheduler
 *  doesn't accidentally rely on Sampler-only methods. */
export interface SoloInstrument {
  triggerAttackRelease(
    notes: string | string[],
    duration: Tone.Unit.Time,
    time?: Tone.Unit.Time,
    velocity?: number,
  ): unknown;
  disconnect(): unknown;
  connect(node: Tone.ToneAudioNode | Tone.Volume): unknown;
}

/** Solo bus: instrument + a volume node so the UI can mute / boost cleanly. */
export interface SoloBus {
  synth: SoloInstrument;
  volume: Tone.Volume;
  /** Identifier of the loaded instrument so callers can re-use the bus when
   *  the same instrument is requested again. */
  instrument: SoloInstrumentName;
}

/**
 * Catalogue of sampled instruments hosted by `nbrosowsky/tonejs-instruments`.
 *
 * The repository ships free, license-friendly recordings sampled at the
 * notes listed below. We use an MP3 baseUrl (CDN-friendly), which trades a
 * little CPU for ~5x smaller downloads compared to WAV. When the chosen
 * instrument fails to load we fall back to the legacy synth so playback
 * still works offline.
 */
const SOLO_SAMPLE_BASE =
  "https://nbrosowsky.github.io/tonejs-instruments/samples";

type SamplerSpec = {
  baseUrl: string;
  urls: Record<string, string>;
  /** Release tail in seconds. Strings ring out longer than winds. */
  release: number;
};

const SOLO_INSTRUMENT_SPECS: Record<string, SamplerSpec> = {
  violin: {
    baseUrl: `${SOLO_SAMPLE_BASE}/violin/`,
    urls: {
      A3: "A3.mp3",
      A4: "A4.mp3",
      A5: "A5.mp3",
      C4: "C4.mp3",
      C5: "C5.mp3",
      C6: "C6.mp3",
      E4: "E4.mp3",
      E5: "E5.mp3",
      E6: "E6.mp3",
      G4: "G4.mp3",
      G5: "G5.mp3",
      G6: "G6.mp3",
    },
    release: 1.4,
  },
  cello: {
    baseUrl: `${SOLO_SAMPLE_BASE}/cello/`,
    urls: {
      A2: "A2.mp3",
      A3: "A3.mp3",
      A4: "A4.mp3",
      C2: "C2.mp3",
      C3: "C3.mp3",
      C4: "C4.mp3",
      E2: "E2.mp3",
      E3: "E3.mp3",
      E4: "E4.mp3",
      G2: "G2.mp3",
      G3: "G3.mp3",
      G4: "G4.mp3",
    },
    release: 1.6,
  },
  flute: {
    baseUrl: `${SOLO_SAMPLE_BASE}/flute/`,
    urls: {
      A4: "A4.mp3",
      A5: "A5.mp3",
      A6: "A6.mp3",
      C4: "C4.mp3",
      C5: "C5.mp3",
      C6: "C6.mp3",
      E4: "E4.mp3",
      E5: "E5.mp3",
      E6: "E6.mp3",
      G4: "G4.mp3",
      G5: "G5.mp3",
      G6: "G6.mp3",
    },
    release: 0.6,
  },
  clarinet: {
    baseUrl: `${SOLO_SAMPLE_BASE}/clarinet/`,
    urls: {
      D3: "D3.mp3",
      D4: "D4.mp3",
      D5: "D5.mp3",
      F3: "F3.mp3",
      F4: "F4.mp3",
      F5: "F5.mp3",
      A3: "A3.mp3",
      A4: "A4.mp3",
      A5: "A5.mp3",
    },
    release: 0.5,
  },
  trumpet: {
    baseUrl: `${SOLO_SAMPLE_BASE}/trumpet/`,
    urls: {
      C4: "C4.mp3",
      D4: "D4.mp3",
      F4: "F4.mp3",
      G4: "G4.mp3",
      A4: "A4.mp3",
      C5: "C5.mp3",
      D5: "D5.mp3",
    },
    release: 0.4,
  },
  saxophone: {
    baseUrl: `${SOLO_SAMPLE_BASE}/saxophone/`,
    urls: {
      A4: "A4.mp3",
      C4: "C4.mp3",
      C5: "C5.mp3",
      E4: "E4.mp3",
      E5: "E5.mp3",
      G4: "G4.mp3",
      G5: "G5.mp3",
    },
    release: 0.5,
  },
  guitar: {
    baseUrl: `${SOLO_SAMPLE_BASE}/guitar-acoustic/`,
    urls: {
      A2: "A2.mp3",
      A3: "A3.mp3",
      A4: "A4.mp3",
      C3: "C3.mp3",
      C4: "C4.mp3",
      D3: "D3.mp3",
      D4: "D4.mp3",
      E2: "E2.mp3",
      E3: "E3.mp3",
      E4: "E4.mp3",
      G3: "G3.mp3",
      G4: "G4.mp3",
    },
    release: 1.0,
  },
};

export type SoloInstrumentName = keyof typeof SOLO_INSTRUMENT_SPECS;

/** Heuristic: read the part-name printed in the score (`<part-name>` /
 *  `<instrument-name>`) and pick the closest sampled instrument. Defaults to
 *  violin since that's the most common for this app's repertoire. */
export function inferSoloInstrument(
  partName: string | null | undefined,
): SoloInstrumentName {
  if (!partName) return "violin";
  const text = partName.toLowerCase();
  if (/cello|violoncello|チェロ/.test(text)) return "cello";
  if (/flute|flauto|フルート/.test(text)) return "flute";
  if (/clarinet|clarinetto|クラリネット/.test(text)) return "clarinet";
  if (/trumpet|tromba|トランペット/.test(text)) return "trumpet";
  if (/sax|saxophone|サックス|サクソフォン/.test(text))
    return "saxophone";
  if (/guitar|ギター/.test(text)) return "guitar";
  return "violin";
}

const soloBusPromises: Map<SoloInstrumentName, Promise<SoloBus>> = new Map();

export function getSoloSampler(
  instrument: SoloInstrumentName = "violin",
): Promise<SoloBus> {
  const cached = soloBusPromises.get(instrument);
  if (cached) return cached;

  const spec = SOLO_INSTRUMENT_SPECS[instrument];
  const promise = new Promise<SoloBus>((resolve) => {
    const volume = new Tone.Volume(0).toDestination();
    let resolved = false;
    let sampler: Tone.Sampler | null = null;
    sampler = new Tone.Sampler({
      urls: spec.urls,
      release: spec.release,
      baseUrl: spec.baseUrl,
      onload: () => {
        if (resolved) return;
        resolved = true;
        sampler!.disconnect();
        sampler!.connect(volume);
        resolve({ synth: sampler!, volume, instrument });
      },
      onerror: (err) => {
        if (resolved) return;
        resolved = true;
        // Fall back to the legacy synth so the user still hears the solo
        // line; a CDN outage shouldn't kill playback.
        // eslint-disable-next-line no-console
        console.warn(
          `Solo sampler load failed for ${instrument}; using fallback synth`,
          err,
        );
        const fallback = createFallbackSynth();
        fallback.connect(volume);
        resolve({ synth: fallback, volume, instrument });
      },
    });
  });

  soloBusPromises.set(instrument, promise);
  return promise;
}

/** Backwards-compat alias used by callers that just want "the solo voice". */
export function getViolinSynth(): Promise<SoloBus> {
  return getSoloSampler("violin");
}

function createFallbackSynth(): Tone.PolySynth {
  return new Tone.PolySynth(Tone.AMSynth, {
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
}

/** Convert a "normal" | "karaoke" | "off" selection to a dB value. */
export function soloVolumeToDb(
  mode: "normal" | "karaoke" | "off",
): number {
  switch (mode) {
    case "normal":
      return 2;
    case "karaoke":
      return -8;
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
