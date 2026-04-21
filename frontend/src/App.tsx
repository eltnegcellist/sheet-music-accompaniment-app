import { useEffect, useMemo, useRef, useState } from "react";
import * as Tone from "tone";

import { analyzePdf } from "./api/analyze";
import { Metronome } from "./audio/Metronome";
import {
  cancelSchedule,
  scheduleScore,
  type ScheduledHandle,
} from "./audio/Scheduler";
import {
  ensureAudioRunning,
  getPianoSampler,
  getViolinSynth,
  soloVolumeToDb,
  type SoloBus,
} from "./audio/ToneEngine";
import { PdfUploader } from "./components/PdfUploader";
import { PdfViewer } from "./components/PdfViewer";
import {
  PlaybackControls,
  type PlaybackState,
} from "./components/PlaybackControls";
import { SheetViewer } from "./components/SheetViewer";
import { parseScore } from "./music/musicXmlParser";
import type { AnalyzeResponse } from "./types";

const DEFAULT_PLAYBACK: PlaybackState = {
  bpm: 100,
  startMeasure: 1,
  endMeasure: 1,
  loop: false,
  countInBars: 1,
  metronome: false,
  soloVolume: "normal",
};

type ViewMode = "pdf" | "sheet";

export default function App() {
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [status, setStatus] = useState<string>("PDFを読み込んでください。");
  const [busy, setBusy] = useState(false);
  const [playback, setPlayback] = useState<PlaybackState>(DEFAULT_PLAYBACK);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentMeasure, setCurrentMeasure] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("pdf");

  const samplerRef = useRef<Tone.Sampler | null>(null);
  const soloBusRef = useRef<SoloBus | null>(null);
  const metronomeRef = useRef<Metronome | null>(null);
  const handleRef = useRef<ScheduledHandle | null>(null);

  const parsedScore = useMemo(() => {
    if (!analysis) return null;
    return parseScore(
      analysis.music_xml,
      analysis.accompaniment_part_id,
      analysis.solo_part_id ?? null,
    );
  }, [analysis]);

  const accompanimentScore = useMemo(() => {
    if (!parsedScore) return null;
    return { notes: parsedScore.accNotes, measures: parsedScore.measures };
  }, [parsedScore]);

  const soloScore = useMemo(() => {
    if (!parsedScore) return null;
    return parsedScore.soloNotes.length > 0 ? { notes: parsedScore.soloNotes } : null;
  }, [parsedScore]);

  const measureCount = accompanimentScore?.measures.length ?? 0;
  const firstMeasure = accompanimentScore?.measures[0]?.index ?? 1;
  const lastMeasure =
    accompanimentScore?.measures[
      (accompanimentScore?.measures.length ?? 1) - 1
    ]?.index ?? 1;

  // Reset playback range when a new score loads.
  useEffect(() => {
    if (!accompanimentScore || accompanimentScore.measures.length === 0) return;
    const beats = analysis?.time_signature?.beats;
    setPlayback((p) => ({
      ...p,
      bpm: analysis?.tempo_bpm ?? p.bpm,
      startMeasure: accompanimentScore.measures[0].index,
      endMeasure:
        accompanimentScore.measures[accompanimentScore.measures.length - 1]
          .index,
    }));
    if (metronomeRef.current && beats) {
      metronomeRef.current.setBeatsPerBar(beats);
    }
  }, [accompanimentScore, analysis]);

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
        `解析完了: ${result.measures.length} 小節 / 伴奏: ${
          result.accompaniment_part_id ?? "(自動検出失敗)"
        } / ソロ: ${result.solo_part_id ?? "なし"}`,
      );
    } catch (err) {
      setStatus(`エラー: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const handlePlay = async () => {
    if (!accompanimentScore || !analysis) return;
    await ensureAudioRunning();
    if (!samplerRef.current) {
      setStatus("ピアノ音源を読み込み中…");
      samplerRef.current = await getPianoSampler();
    }
    if (soloScore && !soloBusRef.current) {
      soloBusRef.current = await getViolinSynth();
    }
    if (!metronomeRef.current) {
      metronomeRef.current = new Metronome();
    }

    if (handleRef.current) cancelSchedule(handleRef.current);

    const transport = Tone.getTransport();
    transport.stop();
    transport.cancel(0);
    transport.bpm.value = playback.bpm;

    const beatsPerBar = analysis.time_signature?.beats ?? 4;
    metronomeRef.current.setBeatsPerBar(beatsPerBar);
    metronomeRef.current.setEnabled(playback.metronome);
    const allFermataBeats = accompanimentScore.fermataBeats.concat(
      soloScore?.fermataBeats ?? [],
    );
    metronomeRef.current.setFermataWindows(
      allFermataBeats.map((b) => ({ start: Math.max(0, b - 1), end: b })),
    );
    metronomeRef.current.start();

    if (soloBusRef.current) {
      soloBusRef.current.volume.volume.value = soloVolumeToDb(
        playback.soloVolume,
      );
    }

    handleRef.current = scheduleScore({
      notes: accompanimentScore.notes,
      measures: accompanimentScore.measures,
      sampler: samplerRef.current,
      soloNotes: soloScore?.notes,
      soloSynth: soloBusRef.current?.synth,
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

  useEffect(() => {
    if (soloBusRef.current) {
      soloBusRef.current.volume.volume.value = soloVolumeToDb(
        playback.soloVolume,
      );
    }
  }, [playback.soloVolume]);

  return (
    <div className="app">
      <header className="app__header">
        <strong>IMSLP Accompanist</strong>
        <PdfUploader disabled={busy} onSelect={handleSelect} />
        <span className="status">{status}</span>
      </header>

      <main className="app__main">
        <div className="view-tabs">
          <button
            type="button"
            className={viewMode === "pdf" ? "view-tabs__active" : ""}
            onClick={() => setViewMode("pdf")}
          >
            PDF
          </button>
          <button
            type="button"
            className={viewMode === "sheet" ? "view-tabs__active" : ""}
            onClick={() => setViewMode("sheet")}
            disabled={!analysis}
          >
            譜面
          </button>
        </div>
        {/* Both views stay mounted so OSMD can measure its container width
            correctly on first render — toggling display:none collapses the
            width to zero and OSMD produces a squashed layout. */}
        <div
          className={
            "view-panel" + (viewMode === "pdf" ? "" : " view-panel--hidden")
          }
        >
          <PdfViewer
            pdfFile={pdfFile}
            measures={analysis?.measures ?? []}
            pageSizes={analysis?.page_sizes ?? []}
            currentMeasureIndex={currentMeasure}
          />
        </div>
        <div
          className={
            "view-panel" + (viewMode === "sheet" ? "" : " view-panel--hidden")
          }
        >
          <SheetViewer
            musicXml={analysis?.music_xml ?? null}
            currentMeasureIndex={currentMeasure}
            isPlaying={isPlaying}
            isVisible={viewMode === "sheet"}
          />
        </div>
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
              テンポ: {analysis.tempo_bpm} bpm
              {analysis.tempo_matched_word
                ? ` (${analysis.tempo_matched_word})`
                : ` (source: ${analysis.tempo_source ?? "?"})`}
              {analysis.time_signature && (
                <>
                  {" / 拍子: "}
                  {analysis.time_signature.beats}/
                  {analysis.time_signature.beat_type}
                </>
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
          firstMeasure={firstMeasure}
          lastMeasure={lastMeasure}
          hasSolo={!!soloScore}
          isPlaying={isPlaying}
          isReady={!!accompanimentScore && !busy}
          onPlay={handlePlay}
          onStop={handleStop}
        />
      </footer>
    </div>
  );
}
