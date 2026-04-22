export interface MeasureBox {
  /** 1-based measure number, matching MusicXML measure@number */
  index: number;
  /** 0-based page in the source PDF */
  page: number;
  /** [x, y, width, height] in image pixels (Audiveris space) */
  bbox: [number, number, number, number];
}

export interface TimeSignature {
  beats: number;
  beat_type: number;
}

export interface AnalyzeResponse {
  music_xml: string;
  score_title?: string | null;
  accompaniment_part_id: string | null;
  solo_part_id: string | null;
  measures: MeasureBox[];
  divisions: number;
  tempo_bpm: number;
  /** Which rule produced tempo_bpm: "sound" | "metronome" | "word" | "ocr-word" | "default" */
  tempo_source?: string;
  /** Tempo word that actually matched (e.g. "allegro"). */
  tempo_matched_word?: string | null;
  /** Text strings scanned for tempo words; useful to confirm what Audiveris OCR'd. */
  tempo_candidates?: string[];
  time_signature: TimeSignature | null;
  page_sizes: [number, number][];
  warnings: string[];
}

/** A single note event ready for Tone.js scheduling. */
export interface NoteEvent {
  /** Time in beats (quarter notes) from the start of the score. */
  beat: number;
  /** Duration in beats. */
  durationBeats: number;
  /** Scientific pitch notation, e.g. "C4". */
  pitch: string;
  velocity: number;
  /** 1-based measure number this note belongs to. */
  measureIndex: number;
}

/** Beat range for a single measure, used to drive highlighting and looping. */
export interface MeasureTiming {
  /** 1-based measure number */
  index: number;
  /** Beat offset from the start of the score */
  startBeat: number;
  /** Length of the measure in beats */
  lengthBeats: number;
}

/** A time window (in beats from score start) where a fermata is sustained. */
export interface FermataWindow {
  start: number;
  end: number;
}
