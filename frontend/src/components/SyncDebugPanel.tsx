import type { LevelDetail } from "../audio/AudioAnalyzer";

export interface SyncEvent {
  time: string;
  kind: "onset" | "silence" | "activity" | "bpm";
  label: string;
}

interface Props {
  levelDetail: LevelDetail | null;
  pitchHz: number | null;
  syncState: string;
  events: SyncEvent[];
}

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

function hzToNoteName(hz: number): string {
  if (hz <= 0) return "—";
  const midi = Math.round(12 * Math.log2(hz / 440) + 69);
  if (midi < 0 || midi > 127) return "—";
  const octave = Math.floor(midi / 12) - 1;
  return `${NOTE_NAMES[midi % 12]}${octave}`;
}

/** Maps dB range [-80, -10] → percentage [0, 100] for display. */
function dbToPercent(db: number): number {
  return Math.max(0, Math.min(100, ((db + 80) / 70) * 100));
}

function markerStyle(db: number): { left: string } {
  return { left: `${dbToPercent(db)}%` };
}

export function SyncDebugPanel({ levelDetail, pitchHz, syncState, events }: Props) {
  const ld = levelDetail;
  const noteName = pitchHz != null ? hzToNoteName(pitchHz) : "—";
  const hzLabel = pitchHz != null ? `${Math.round(pitchHz)} Hz` : "—";

  return (
    <div className="sync-debug">
      <div className="sync-debug__title">🔬 デバッグ情報</div>

      {/* Level bar with threshold markers */}
      <div className="sync-debug__row">
        <span className="sync-debug__lbl">レベル</span>
        <div className="sync-debug__bar-wrap">
          {ld && (
            <>
              <div
                className="sync-debug__bar-fill"
                style={{ width: `${dbToPercent(ld.rmsDb)}%` }}
              />
              {/* Noise floor marker */}
              <div className="sync-debug__marker sync-debug__marker--floor" style={markerStyle(ld.noiseFloorDb)} title={`ノイズフロア: ${ld.noiseFloorDb.toFixed(1)} dB`} />
              {/* Silence threshold */}
              <div className="sync-debug__marker sync-debug__marker--silence" style={markerStyle(ld.silenceThresholdDb)} title={`無音閾値: ${ld.silenceThresholdDb.toFixed(1)} dB`} />
              {/* Onset threshold */}
              <div className="sync-debug__marker sync-debug__marker--onset" style={markerStyle(ld.onsetThresholdDb)} title={`オンセット閾値: ${ld.onsetThresholdDb.toFixed(1)} dB`} />
            </>
          )}
        </div>
        <span className="sync-debug__val">
          {ld ? `${ld.rmsDb.toFixed(1)} dB` : "—"}
        </span>
      </div>

      {/* Threshold legend */}
      {ld && (
        <div className="sync-debug__legend">
          <span className="sync-debug__legend-item">
            <span className="sync-debug__dot sync-debug__dot--floor" /> NF {ld.noiseFloorDb.toFixed(1)}
          </span>
          <span className="sync-debug__legend-item">
            <span className="sync-debug__dot sync-debug__dot--silence" /> 無音 {ld.silenceThresholdDb.toFixed(1)}
          </span>
          <span className="sync-debug__legend-item">
            <span className="sync-debug__dot sync-debug__dot--onset" /> 発音 {ld.onsetThresholdDb.toFixed(1)}
          </span>
        </div>
      )}

      {/* Pitch */}
      <div className="sync-debug__row">
        <span className="sync-debug__lbl">音程</span>
        <span className="sync-debug__pitch">{noteName}</span>
        <span className="sync-debug__val">{hzLabel}</span>
      </div>

      {/* State */}
      <div className="sync-debug__row">
        <span className="sync-debug__lbl">状態</span>
        <span className={`sync-debug__state sync-debug__state--${syncState}`}>{syncState}</span>
      </div>

      {/* Event log */}
      <div className="sync-debug__log">
        {events.length === 0 && <div className="sync-debug__log-empty">イベントなし</div>}
        {events.map((e, i) => (
          <div key={i} className={`sync-debug__log-row sync-debug__log-row--${e.kind}`}>
            <span className="sync-debug__log-time">{e.time}</span>
            <span className="sync-debug__log-label">{e.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
