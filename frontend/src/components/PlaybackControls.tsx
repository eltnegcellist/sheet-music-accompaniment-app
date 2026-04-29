import type { ChangeEvent } from "react";

import type { SoloInstrumentName } from "../audio/ToneEngine";

export type SoloVolumeMode = "normal" | "karaoke" | "off";

/** "auto" defers to the part-name heuristic; everything else is a hard
 *  override the user picked from the dropdown. */
export type SoloInstrumentChoice = "auto" | SoloInstrumentName;

export interface PlaybackState {
  bpm: number;
  startMeasure: number;
  endMeasure: number;
  loop: boolean;
  countInBars: number;
  metronome: boolean;
  pianoVolume: number;
  soloVolume: SoloVolumeMode;
  soloInstrument: SoloInstrumentChoice;
}

const SOLO_INSTRUMENT_LABELS: Array<[SoloInstrumentChoice, string]> = [
  ["auto", "自動"],
  ["violin", "Violin"],
  ["cello", "Cello"],
  ["flute", "Flute"],
  ["clarinet", "Clarinet"],
  ["trumpet", "Trumpet"],
  ["saxophone", "Saxophone"],
  ["guitar", "Guitar"],
];

interface Props {
  state: PlaybackState;
  onChange: (next: PlaybackState) => void;
  measureCount: number;
  firstMeasure: number;
  lastMeasure: number;
  hasSolo: boolean;
  isPlaying: boolean;
  isReady: boolean;
  onPlay: () => void;
  onStop: () => void;
}

export function PlaybackControls({
  state,
  onChange,
  measureCount,
  firstMeasure,
  lastMeasure,
  hasSolo,
  isPlaying,
  isReady,
  onPlay,
  onStop,
}: Props) {
  const update = (patch: Partial<PlaybackState>) =>
    onChange({ ...state, ...patch });

  const intInput =
    (key: keyof PlaybackState) => (e: ChangeEvent<HTMLInputElement>) => {
      const v = Number.parseInt(e.target.value, 10);
      if (Number.isFinite(v)) update({ [key]: v } as Partial<PlaybackState>);
    };

  const resetRange = () => {
    if (measureCount === 0) return;
    update({ startMeasure: firstMeasure, endMeasure: lastMeasure });
  };

  return (
    <div className="controls">
      <button
        type="button"
        className="controls__primary"
        disabled={!isReady}
        onClick={isPlaying ? onStop : onPlay}
      >
        {isPlaying ? "停止" : "再生"}
      </button>

      <label>
        テンポ ({state.bpm} bpm)
        <input
          type="range"
          min={30}
          max={240}
          value={state.bpm}
          onChange={intInput("bpm")}
        />
      </label>

      <label>
        伴奏音量 ({state.pianoVolume}%)
        <input
          type="range"
          min={0}
          max={120}
          value={state.pianoVolume}
          onChange={intInput("pianoVolume")}
        />
      </label>

      <label>
        開始小節
        <input
          type="number"
          min={1}
          max={Math.max(1, measureCount)}
          value={state.startMeasure}
          onChange={intInput("startMeasure")}
        />
      </label>

      <label>
        終了小節 <small className="controls__hint">(全 {measureCount} 小節)</small>
        <input
          type="number"
          min={state.startMeasure}
          max={Math.max(state.startMeasure, measureCount)}
          value={state.endMeasure}
          onChange={intInput("endMeasure")}
        />
        <button
          type="button"
          className="controls__reset"
          onClick={resetRange}
          disabled={measureCount === 0}
        >
          リセット
        </button>
      </label>

      <label className="controls__toggle">
        <input
          type="checkbox"
          checked={state.loop}
          onChange={(e) => update({ loop: e.target.checked })}
        />
        指定範囲をループ
      </label>

      <label>
        カウントイン (小節)
        <input
          type="number"
          min={0}
          max={4}
          value={state.countInBars}
          onChange={intInput("countInBars")}
        />
      </label>

      <label className="controls__toggle">
        <input
          type="checkbox"
          checked={state.metronome}
          onChange={(e) => update({ metronome: e.target.checked })}
        />
        メトロノーム
      </label>

      <label>
        ソロ音量 {!hasSolo && <small className="controls__hint">(ソロなし)</small>}
        <select
          value={state.soloVolume}
          disabled={!hasSolo}
          onChange={(e) =>
            update({ soloVolume: e.target.value as SoloVolumeMode })
          }
        >
          <option value="normal">普通</option>
          <option value="karaoke">カラオケ</option>
          <option value="off">無し</option>
        </select>
      </label>

      <label>
        ソロ楽器
        <select
          value={state.soloInstrument}
          disabled={!hasSolo}
          onChange={(e) =>
            update({
              soloInstrument: e.target.value as SoloInstrumentChoice,
            })
          }
        >
          {SOLO_INSTRUMENT_LABELS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <small className="controls__hint">
          OMRが楽器名を取り違えた場合に手動で上書きできます
        </small>
      </label>
    </div>
  );
}
