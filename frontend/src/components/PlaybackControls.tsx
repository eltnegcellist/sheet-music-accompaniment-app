import type { ChangeEvent } from "react";

export interface PlaybackState {
  bpm: number;
  startMeasure: number;
  endMeasure: number;
  loop: boolean;
  countInBars: number;
  metronome: boolean;
}

interface Props {
  state: PlaybackState;
  onChange: (next: PlaybackState) => void;
  measureCount: number;
  isPlaying: boolean;
  isReady: boolean;
  onPlay: () => void;
  onStop: () => void;
}

export function PlaybackControls({
  state,
  onChange,
  measureCount,
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
        終了小節
        <input
          type="number"
          min={state.startMeasure}
          max={Math.max(state.startMeasure, measureCount)}
          value={state.endMeasure}
          onChange={intInput("endMeasure")}
        />
      </label>

      <label>
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

      <label>
        <input
          type="checkbox"
          checked={state.metronome}
          onChange={(e) => update({ metronome: e.target.checked })}
        />
        メトロノーム
      </label>
    </div>
  );
}
