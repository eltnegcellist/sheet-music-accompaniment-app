import type { ChangeEvent } from "react";

import type { SoloInstrumentName } from "../audio/ToneEngine";
import type { TimeSignature } from "../types";

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
  ["auto", "自動検出"],
  ["violin", "ヴァイオリン"],
  ["cello", "チェロ"],
  ["flute", "フルート"],
  ["clarinet", "クラリネット"],
  ["trumpet", "トランペット"],
  ["saxophone", "サックス"],
  ["guitar", "ギター"],
];

const SOLO_VOLUMES: Array<{ k: SoloVolumeMode; l: string }> = [
  { k: "normal", l: "普通" },
  { k: "karaoke", l: "カラオケ" },
  { k: "off", l: "無し" },
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
  onDownloadMusicXml?: () => void;
  canDownload: boolean;
  timeSignature: TimeSignature | null;
  currentMeasure: number | null;
  /** When true, expand the transport from a 64px play pill to the full bar. */
  expanded: boolean;
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
  onDownloadMusicXml,
  canDownload,
  timeSignature,
  currentMeasure,
  expanded,
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

  const cur = isPlaying ? currentMeasure : null;
  const measureMax = Math.max(1, lastMeasure);

  return (
    <div className={`transport${expanded ? " transport--expanded" : ""}`}>
      <div className="transport__inner">
        {/* Row 1: play + measure + bpm + piano vol + range */}
        <div className="transport__row">
          <div className="tr-sec">
            <button
              type="button"
              className={`play-btn${isPlaying ? " play-btn--stop" : ""}`}
              disabled={!isReady}
              onClick={isPlaying ? onStop : onPlay}
              aria-label={isPlaying ? "停止" : "再生"}
            >
              {isPlaying ? "■" : "▶"}
            </button>
            <div className="measure-ro">
              <span className="measure-ro__lbl">小節</span>
              <span className="measure-ro__val">
                {cur != null ? String(cur).padStart(2, "0") : "—"}
              </span>
              <span className="measure-ro__tot">/ {measureCount || 0}</span>
            </div>
            {timeSignature && (
              <div className="timesig" title="拍子">
                <span className="timesig__n">{timeSignature.beats}</span>
                <div className="timesig__line" />
                <span className="timesig__n">{timeSignature.beat_type}</span>
              </div>
            )}
          </div>
          <div className="tr-sep" />

          <div className="tr-sec">
            <div className="sl-ctl">
              <div className="sl-ctl__head">
                <span className="sl-ctl__val">{state.bpm}</span>
                <span className="sl-ctl__unit">bpm</span>
              </div>
              <input
                type="range"
                className="sl"
                min={30}
                max={240}
                value={state.bpm}
                onChange={intInput("bpm")}
              />
              <span className="sl-ctl__lbl">テンポ</span>
            </div>
          </div>
          <div className="tr-sep" />

          <div className="tr-sec">
            <div className="sl-ctl sl-ctl--sm">
              <div className="sl-ctl__head">
                <span className="sl-ctl__val">{state.pianoVolume}</span>
                <span className="sl-ctl__unit">%</span>
              </div>
              <input
                type="range"
                className="sl"
                min={0}
                max={120}
                value={state.pianoVolume}
                onChange={intInput("pianoVolume")}
              />
              <span className="sl-ctl__lbl">伴奏音量</span>
            </div>
          </div>
          <div className="tr-sep" />

          <div className="tr-sec">
            <div className="range-ctl">
              <div className="range-ctl__head">
                <span className="range-ctl__lbl">再生範囲</span>
                <button
                  type="button"
                  className="range-ctl__reset"
                  disabled={!isReady || measureCount === 0}
                  onClick={resetRange}
                >
                  リセット
                </button>
              </div>
              <div className="range-ctl__row">
                <input
                  type="number"
                  className="range-num"
                  min={firstMeasure}
                  max={measureMax}
                  value={state.startMeasure}
                  onChange={intInput("startMeasure")}
                />
                <span className="range-arrow">→</span>
                <input
                  type="number"
                  className="range-num"
                  min={state.startMeasure}
                  max={measureMax}
                  value={state.endMeasure}
                  onChange={intInput("endMeasure")}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Row 2: count-in + toggles + solo instr + solo vol + dl */}
        <div className="transport__row transport__row--2">
          <div
            className="tr-sec"
            style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}
          >
            <span className="sl-ctl__lbl">カウントイン</span>
            <select
              className="cnt-sel"
              value={state.countInBars}
              onChange={(e) => update({ countInBars: +e.target.value })}
            >
              <option value={0}>なし</option>
              <option value={1}>1小節</option>
              <option value={2}>2小節</option>
              <option value={4}>4小節</option>
            </select>
          </div>
          <div className="tr-sep" />

          <div className="tr-sec">
            <div className="tog-group">
              <div
                className="tog-row"
                onClick={() => update({ loop: !state.loop })}
              >
                <div className={`tog-track${state.loop ? " tog-track--on" : ""}`} />
                <span className="tog-lbl">ループ</span>
              </div>
              <div
                className="tog-row"
                onClick={() => update({ metronome: !state.metronome })}
              >
                <div
                  className={`tog-track${state.metronome ? " tog-track--on" : ""}`}
                />
                <span className="tog-lbl">メトロノーム</span>
              </div>
            </div>
          </div>
          <div className="tr-sep" />

          <div className="tr-sec">
            <div className="solo-instr">
              <span className="solo-instr__lbl">
                ソロ楽器
                {!hasSolo && (
                  <span style={{ marginLeft: 4, opacity: 0.5 }}>(なし)</span>
                )}
              </span>
              <select
                className="solo-instr__sel"
                disabled={!hasSolo}
                value={state.soloInstrument}
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
            </div>
          </div>
          <div className="tr-sep" />

          <div className="tr-sec">
            <div className="solo-ctl">
              <span className="solo-ctl__lbl">ソロ音量</span>
              <div className="solo-pills">
                {SOLO_VOLUMES.map((s) => (
                  <button
                    type="button"
                    key={s.k}
                    className={`solo-pill${state.soloVolume === s.k ? " solo-pill--on" : ""}`}
                    disabled={!hasSolo}
                    onClick={() => update({ soloVolume: s.k })}
                  >
                    {s.l}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="tr-sep" />

          <div className="tr-sec">
            <button
              type="button"
              className="act-btn"
              disabled={!canDownload}
              onClick={onDownloadMusicXml}
              title="解析済みMusicXMLをダウンロード"
            >
              <span className="act-btn__ico">↓</span>
              <span className="act-btn__lbl">MusicXML</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
