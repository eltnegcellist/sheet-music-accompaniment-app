import { useEffect, useMemo, useRef, useState } from "react";
import * as Tone from "tone";

import { analyzePdf } from "./api/analyze";
import { Metronome } from "./audio/Metronome";
import {
  cancelSchedule,
  scheduleScore,
  type ScheduledHandle,
} from "./audio/Scheduler";
import { ensureAudioRunning, getPianoSampler } from "./audio/ToneEngine";
import { PdfUploader } from "./components/PdfUploader";
import { PdfViewer } from "./components/PdfViewer";
import {
  PlaybackControls,
  type PlaybackState,
} from "./components/PlaybackControls";
import { parseMusicXml } from "./music/musicXmlParser";
import type { AnalyzeResponse } from "./types";

const DEFAULT_PLAYBACK: PlaybackState = {
  bpm: 100,
  startMeasure: 1,
  endMeasure: 1,
  loop: false,
  countInBars: 1,
  metronome: false,
};

export default function App() {
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [status, setStatus] = useState<string>("PDFを読み込んでください。");
  const [busy, setBusy] = useState(false);
  const [playback, setPlayback] = useState<PlaybackState>(DEFAULT_PLAYBACK);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentMeasure, setCurrentMeasure] = useState<number | null>(null);

  const samplerRef = useRef<Tone.Sampler | null>(null);
  const metronomeRef = useRef<Metronome | null>(null);
  const handleRef = useRef<ScheduledHandle | null>(null);

  const score = useMemo(() => {
    if (!analysis) return null;
    return parseMusicXml(analysis.music_xml, analysis.accompaniment_part_id);
  }, [analysis]);

  const measureCount = score?.measures.length ?? 0;

  // Reset playback range when a new score loads.
  useEffect(() => {
    if (!score || score.measures.length === 0) return;
    setPlayback((p) => ({
      ...p,
      bpm: analysis?.tempo_bpm ?? p.bpm,
      startMeasure: score.measures[0].index,
      endMeasure: score.measures[score.measures.length - 1].index,
    }));
  }, [score, analysis]);

  const handleSelect = async (pdf: File, musicXml?: File) => {
    setPdfFile(pdf);
    setBusy(true);
    setAnalysis(null);
    setCurrentMeasure(null);
    setStatus("解析中… (OMR には数十秒かかる場合があります)");
    try {
      const result = await analyzePdf(pdf, musicXml);
      setAnalysis(result);
      setStatus(
        `解析完了: ${result.measures.length} 小節 / 伴奏パート: ${
          result.accompaniment_part_id ?? "(自動検出失敗)"
        }`,
      );
    } catch (err) {
      setStatus(`エラー: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const handlePlay = async () => {
    if (!score || !analysis) return;
    await ensureAudioRunning();
    if (!samplerRef.current) {
      setStatus("ピアノ音源を読み込み中…");
      samplerRef.current = await getPianoSampler();
    }
    if (!metronomeRef.current) {
      metronomeRef.current = new Metronome();
    }

    if (handleRef.current) cancelSchedule(handleRef.current);

    const transport = Tone.getTransport();
    transport.stop();
    transport.cancel(0);
    transport.bpm.value = playback.bpm;

    metronomeRef.current.setBeatsPerBar(4);
    metronomeRef.current.setEnabled(playback.metronome);
    metronomeRef.current.start();

    handleRef.current = scheduleScore({
      notes: score.notes,
      measures: score.measures,
      sampler: samplerRef.current,
      onMeasureChange: (idx) => setCurrentMeasure(idx),
      startMeasure: playback.startMeasure,
      endMeasure: playback.endMeasure,
      loop: playback.loop,
    });

    const startAt = await metronomeRef.current.countIn(
      playback.countInBars,
      playback.bpm,
    );
    transport.start(startAt);
    setIsPlaying(true);
    setStatus("再生中");
  };

  const handleDownloadMusicXml = () => {
    if (!analysis) return;
    const blob = new Blob([analysis.music_xml], {
      type: "application/vnd.recordare.musicxml+xml",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const base = pdfFile?.name.replace(/\.pdf$/i, "") ?? "score";
    a.href = url;
    a.download = `${base}.musicxml`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleStop = () => {
    const transport = Tone.getTransport();
    transport.stop();
    transport.cancel(0);
    metronomeRef.current?.stop();
    if (handleRef.current) cancelSchedule(handleRef.current);
    handleRef.current = null;
    setIsPlaying(false);
    setCurrentMeasure(null);
    setStatus("停止");
  };

  // Live tempo updates while playing.
  useEffect(() => {
    Tone.getTransport().bpm.rampTo(playback.bpm, 0.05);
  }, [playback.bpm]);

  useEffect(() => {
    metronomeRef.current?.setEnabled(playback.metronome);
  }, [playback.metronome]);

  return (
    <div className="app">
      <header className="app__header">
        <strong>IMSLP Accompanist</strong>
        <PdfUploader disabled={busy} onSelect={handleSelect} />
        <span className="status">{status}</span>
      </header>

      <main className="app__main">
        <PdfViewer
          pdfFile={pdfFile}
          measures={analysis?.measures ?? []}
          pageSizes={analysis?.page_sizes ?? []}
          currentMeasureIndex={currentMeasure}
        />
      </main>

      <footer className="app__footer">
        <div className="analysis-actions">
          <button
            type="button"
            onClick={handleDownloadMusicXml}
            disabled={!analysis}
          >
            MusicXML をダウンロード
          </button>
          <small>
            次回は PDF と一緒にこのファイルもドロップすると OMR をスキップして即解析できます。
          </small>
          {analysis && (
            <small className="tempo-debug">
              テンポ: {analysis.tempo_bpm} bpm (source: {analysis.tempo_source ?? "?"})
              {analysis.tempo_candidates && analysis.tempo_candidates.length > 0 && (
                <> / 検出テキスト: {analysis.tempo_candidates.join(" | ")}</>
              )}
            </small>
          )}
        </div>
        {analysis?.warnings && analysis.warnings.length > 0 && (
          <div className="warnings">
            {analysis.warnings.map((w, i) => (
              <div key={i}>⚠ {w}</div>
            ))}
          </div>
        )}
        <PlaybackControls
          state={playback}
          onChange={setPlayback}
          measureCount={measureCount}
          isPlaying={isPlaying}
          isReady={!!score && !busy}
          onPlay={handlePlay}
          onStop={handleStop}
        />
      </footer>
    </div>
  );
}
