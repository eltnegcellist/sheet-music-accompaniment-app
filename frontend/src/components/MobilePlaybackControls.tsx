import { useState, type ChangeEvent } from "react";

import type { SoloInstrumentName } from "../audio/ToneEngine";
import { useLang } from "../i18n";
import type { TimeSignature } from "../types";
import type {
  PlaybackState,
  SoloInstrumentChoice,
  SoloVolumeMode,
} from "./PlaybackControls";

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
}

export function MobilePlaybackControls({
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
}: Props) {
  const { lang, T } = useLang();
  const [expanded, setExpanded] = useState(false);
  const ja = lang === "ja";

  const update = (patch: Partial<PlaybackState>) =>
    onChange({ ...state, ...patch });

  const intInput =
    (key: keyof PlaybackState) => (e: ChangeEvent<HTMLInputElement>) => {
      const value = Number.parseInt(e.target.value, 10);
      if (Number.isFinite(value)) {
        update({ [key]: value } as Partial<PlaybackState>);
      }
    };

  const instruments: Array<[SoloInstrumentChoice, string]> = [
    ["auto", T.instrAuto],
    ["violin", T.instrViolin],
    ["cello", T.instrCello],
    ["flute", T.instrFlute],
    ["clarinet", T.instrClarinet],
    ["trumpet", T.instrTrumpet],
    ["saxophone", T.instrSax],
    ["guitar", T.instrGuitar],
  ];

  const soloVolumes: Array<[SoloVolumeMode, string]> = [
    ["normal", T.soloVolNormal],
    ["karaoke", T.soloVolKaraoke],
    ["off", T.soloVolOff],
  ];

  const shownMeasure = isPlaying && currentMeasure != null
    ? currentMeasure
    : state.startMeasure;

  return (
    <div className={"mobile-player" + (expanded ? " mobile-player--expanded" : "")}>
      {expanded && (
        <div className="mobile-player__sheet">
          <div className="mobile-player__sheet-head">
            <strong>{ja ? "再生設定" : "Playback settings"}</strong>
            <button type="button" onClick={() => setExpanded(false)} aria-label={T.close}>
              ×
            </button>
          </div>

          <div className="mobile-control">
            <div className="mobile-control__label">
              <span>{T.tempo}</span>
              <strong>{state.bpm} bpm</strong>
            </div>
            <div className="mobile-stepper">
              <button type="button" onClick={() => update({ bpm: Math.max(30, state.bpm - 5) })}>−</button>
              <input
                type="range"
                min={30}
                max={240}
                value={state.bpm}
                onChange={intInput("bpm")}
              />
              <button type="button" onClick={() => update({ bpm: Math.min(240, state.bpm + 5) })}>＋</button>
            </div>
          </div>

          <div className="mobile-control">
            <div className="mobile-control__label">
              <span>{T.accompVol}</span>
              <strong>{state.pianoVolume}%</strong>
            </div>
            <input
              className="mobile-full-slider"
              type="range"
              min={0}
              max={120}
              value={state.pianoVolume}
              onChange={intInput("pianoVolume")}
            />
          </div>

          <div className="mobile-settings-grid">
            <label className="mobile-field">
              <span>{ja ? "開始小節" : "Start measure"}</span>
              <input
                type="number"
                min={firstMeasure}
                max={Math.max(firstMeasure, lastMeasure)}
                value={state.startMeasure}
                onChange={intInput("startMeasure")}
              />
            </label>
            <label className="mobile-field">
              <span>{ja ? "終了小節" : "End measure"}</span>
              <input
                type="number"
                min={state.startMeasure}
                max={Math.max(firstMeasure, lastMeasure)}
                value={state.endMeasure}
                onChange={intInput("endMeasure")}
              />
            </label>
            <label className="mobile-field">
              <span>{T.countIn}</span>
              <select
                value={state.countInBars}
                onChange={(e) => update({ countInBars: +e.target.value })}
              >
                <option value={0}>{T.countInNone}</option>
                <option value={1}>{T.countIn1}</option>
                <option value={2}>{T.countIn2}</option>
                <option value={4}>{T.countIn4}</option>
              </select>
            </label>
            <div className="mobile-field">
              <span>{ja ? "拍子" : "Time signature"}</span>
              <div className="mobile-field__static">
                {timeSignature
                  ? `${timeSignature.beats}/${timeSignature.beat_type}`
                  : "—"}
              </div>
            </div>
          </div>

          <div className="mobile-toggle-row">
            <button
              type="button"
              className={state.loop ? "mobile-toggle mobile-toggle--on" : "mobile-toggle"}
              onClick={() => update({ loop: !state.loop })}
            >
              ↻ {T.loop}
            </button>
            <button
              type="button"
              className={state.metronome ? "mobile-toggle mobile-toggle--on" : "mobile-toggle"}
              onClick={() => update({ metronome: !state.metronome })}
            >
              ♩ {T.metronome}
            </button>
          </div>

          {hasSolo && (
            <>
              <label className="mobile-field mobile-field--wide">
                <span>{T.soloInstr}</span>
                <select
                  value={state.soloInstrument}
                  onChange={(e) =>
                    update({
                      soloInstrument: e.target.value as SoloInstrumentName | "auto",
                    })
                  }
                >
                  {instruments.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
              <div className="mobile-segmented" aria-label={T.soloVol}>
                {soloVolumes.map(([value, label]) => (
                  <button
                    type="button"
                    key={value}
                    className={state.soloVolume === value ? "mobile-segmented__on" : ""}
                    onClick={() => update({ soloVolume: value })}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </>
          )}

          <button
            type="button"
            className="mobile-export"
            disabled={!canDownload}
            onClick={onDownloadMusicXml}
          >
            ↓ {ja ? "MusicXMLを保存" : "Save MusicXML"}
          </button>
        </div>
      )}

      <div className="mobile-player__bar">
        <button
          type="button"
          className={isPlaying ? "mobile-play mobile-play--stop" : "mobile-play"}
          disabled={!isReady}
          onClick={isPlaying ? onStop : onPlay}
          aria-label={isPlaying ? T.stopBtn : T.playBtn}
        >
          {isPlaying ? "■" : "▶"}
        </button>
        <div className="mobile-player__measure">
          <span>{ja ? "小節" : "Measure"}</span>
          <strong>{shownMeasure}</strong>
          <small>/ {measureCount || 0}</small>
        </div>
        <button
          type="button"
          className="mobile-bpm"
          onClick={() => setExpanded(true)}
          aria-label={ja ? "再生設定を開く" : "Open playback settings"}
        >
          <strong>{state.bpm}</strong>
          <span>bpm</span>
        </button>
        <button
          type="button"
          className="mobile-more"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
        >
          {expanded ? "⌄" : "☰"}
        </button>
      </div>
    </div>
  );
}
