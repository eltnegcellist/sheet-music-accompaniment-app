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
  getSoloSampler,
  inferSoloInstrument,
  soloVolumeToDb,
  type SoloBus,
  type SoloInstrumentName,
} from "./audio/ToneEngine";
import { PdfUploader, type PdfUploaderHandle } from "./components/PdfUploader";
import { PdfViewer } from "./components/PdfViewer";
import {
  PlaybackControls,
  type PlaybackState,
} from "./components/PlaybackControls";
import { SheetViewer } from "./components/SheetViewer";
import { parseScore } from "./music/musicXmlParser";
import { sanitizeForOsmd } from "./music/sanitize";
import type { AnalyzeResponse } from "./types";

const DEFAULT_PLAYBACK: PlaybackState = {
  bpm: 100,
  startMeasure: 1,
  endMeasure: 1,
  loop: false,
  countInBars: 1,
  metronome: false,
  pianoVolume: 100,
  soloVolume: "normal",
  soloInstrument: "auto",
};

type ViewMode = "pdf" | "sheet";
type Scene = "upload" | "analyzing" | "loaded";
type StatusLed = "" | "on" | "busy" | "err";

const CACHE_HIT_WARNING = "（キャッシュから復元しました）";

export default function App() {
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [musicXmlFile, setMusicXmlFile] = useState<File | null>(null);
  const [soloPdfFile, setSoloPdfFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [statusText, setStatusText] = useState<string>(
    "PDFをドロップして開始",
  );
  const [statusLed, setStatusLed] = useState<StatusLed>("");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [playback, setPlayback] = useState<PlaybackState>(DEFAULT_PLAYBACK);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentMeasure, setCurrentMeasure] = useState<number | null>(null);
  const [currentMeasureOrdinal, setCurrentMeasureOrdinal] = useState<
    number | null
  >(null);
  const [viewMode, setViewMode] = useState<ViewMode>("pdf");
  const [pdfPage, setPdfPage] = useState(0);
  const [pdfTotalPages, setPdfTotalPages] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [warningsDismissed, setWarningsDismissed] = useState(false);

  // Auto-hide topbar/transport based on cursor proximity. The badge / play
  // pill stay visible so the user always has an entry point.
  const [headerVisible, setHeaderVisible] = useState(true);
  const [footerVisible, setFooterVisible] = useState(false);
  const hideTimers = useRef<{ h?: number; f?: number }>({});

  const uploaderRef = useRef<PdfUploaderHandle>(null);
  const samplerRef = useRef<Tone.Sampler | null>(null);
  const pianoVolumeRef = useRef<Tone.Volume | null>(null);
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

  const isLoaded = !!analysis;
  const scene: Scene = busy && !analysis ? "analyzing" : isLoaded ? "loaded" : "upload";

  // Cache state is signaled by a sentinel string in the warnings list (set by
  // the backend when it returns a cached payload); strip it here so it doesn't
  // surface as a user-facing warning while still reflecting it in the badge.
  const cached = useMemo(
    () => !!analysis?.warnings?.includes(CACHE_HIT_WARNING),
    [analysis],
  );
  const visibleWarnings = useMemo(
    () =>
      (analysis?.warnings ?? []).filter((w) => w !== CACHE_HIT_WARNING),
    [analysis],
  );

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

  // Mouse-proximity auto-hide.
  useEffect(() => {
    const HEADER_ZONE = 110;
    const FOOTER_ZONE = 140;
    const onMove = (e: MouseEvent) => {
      const y = e.clientY;
      const h = window.innerHeight;
      if (y < HEADER_ZONE) {
        window.clearTimeout(hideTimers.current.h);
        setHeaderVisible(true);
      } else {
        window.clearTimeout(hideTimers.current.h);
        hideTimers.current.h = window.setTimeout(
          () => setHeaderVisible(false),
          1200,
        );
      }
      if (y > h - FOOTER_ZONE) {
        window.clearTimeout(hideTimers.current.f);
        setFooterVisible(true);
      } else {
        window.clearTimeout(hideTimers.current.f);
        hideTimers.current.f = window.setTimeout(
          () => setFooterVisible(false),
          1500,
        );
      }
    };
    window.addEventListener("mousemove", onMove);
    return () => {
      window.removeEventListener("mousemove", onMove);
      Object.values(hideTimers.current).forEach((t) =>
        window.clearTimeout(t),
      );
    };
  }, []);

  const tempoLabel = useMemo(() => {
    if (!analysis) return "";
    const word = analysis.tempo_matched_word;
    return word ? `${analysis.tempo_bpm} bpm (${word})` : `${analysis.tempo_bpm} bpm`;
  }, [analysis]);

  const timeSigLabel = analysis?.time_signature
    ? `${analysis.time_signature.beats}/${analysis.time_signature.beat_type}`
    : "";

  // Status badge text + LED follow scene state.
  useEffect(() => {
    if (errorText) {
      setStatusLed("err");
      setStatusText(errorText);
      return;
    }
    if (busy) {
      setStatusLed("busy");
      setStatusText("OMR 解析中…");
      return;
    }
    if (analysis) {
      setStatusLed("on");
      const accId = analysis.accompaniment_part_id ?? "?";
      const soloId = analysis.solo_part_id ?? "なし";
      const playing = isPlaying && currentMeasure != null;
      setStatusText(
        playing
          ? `再生中 — 小節 ${currentMeasure} / ${measureCount}`
          : `解析完了 · ${measureCount}小節 · ${accId}+${soloId} · ${tempoLabel} · ${timeSigLabel}`,
      );
      return;
    }
    setStatusLed("");
    setStatusText("PDFをドロップして開始");
  }, [
    analysis,
    busy,
    errorText,
    isPlaying,
    currentMeasure,
    measureCount,
    tempoLabel,
    timeSigLabel,
  ]);

  const runAnalyze = async (
    pdf: File | undefined,
    musicXml: File | undefined,
    soloPdf: File | undefined,
    force: boolean,
  ) => {
    setBusy(true);
    setErrorText(null);
    setAnalysis(null);
    setCurrentMeasure(null);
    setCurrentMeasureOrdinal(null);
    try {
      const result = await analyzePdf(pdf, musicXml, { soloPdf, force });
      result.music_xml = sanitizeForOsmd(result.music_xml);
      setAnalysis(result);
      setWarningsDismissed(false);
    } catch (err) {
      setErrorText(`エラー: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleSelect = async (
    pdf?: File,
    musicXml?: File,
    soloPdf?: File,
  ) => {
    setPdfFile(pdf ?? null);
    setMusicXmlFile(musicXml ?? null);
    setSoloPdfFile(soloPdf ?? null);
    setPdfPage(0);
    setPdfTotalPages(0);
    await runAnalyze(pdf, musicXml, soloPdf, false);
  };

  const handleReanalyze = async () => {
    if (!pdfFile && !musicXmlFile) return;
    await runAnalyze(
      pdfFile ?? undefined,
      musicXmlFile ?? undefined,
      soloPdfFile ?? undefined,
      true,
    );
  };

  const handlePlay = async () => {
    if (!accompanimentScore || !analysis || !parsedScore) return;
    await ensureAudioRunning();
    if (!samplerRef.current) {
      samplerRef.current = await getPianoSampler();
      if (!pianoVolumeRef.current) {
        pianoVolumeRef.current = new Tone.Volume(0).toDestination();
      }
      samplerRef.current.disconnect();
      samplerRef.current.connect(pianoVolumeRef.current);
    }
    if (soloScore) {
      const wantedInstrument: SoloInstrumentName =
        playback.soloInstrument !== "auto"
          ? playback.soloInstrument
          : inferSoloInstrument(analysis?.solo_part_name ?? null);
      if (
        !soloBusRef.current ||
        soloBusRef.current.instrument !== wantedInstrument
      ) {
        soloBusRef.current = await getSoloSampler(wantedInstrument);
      }
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
    metronomeRef.current.setFermataWindows(parsedScore.fermataWindows);
    const playRangeMeasures = accompanimentScore.measures.filter(
      (m) => m.index >= playback.startMeasure && m.index <= playback.endMeasure,
    );
    const offsetBeats = playRangeMeasures[0]?.startBeat ?? 0;
    metronomeRef.current.setMeasures(playRangeMeasures, offsetBeats);
    metronomeRef.current.start();

    if (soloBusRef.current) {
      soloBusRef.current.volume.volume.value = soloVolumeToDb(
        playback.soloVolume,
      );
    }
    if (pianoVolumeRef.current) {
      pianoVolumeRef.current.volume.value = Tone.gainToDb(
        Math.max(0.0001, playback.pianoVolume / 100),
      );
    }

    handleRef.current = scheduleScore({
      notes: accompanimentScore.notes,
      measures: accompanimentScore.measures,
      sampler: samplerRef.current,
      soloNotes: soloScore?.notes,
      soloSynth: soloBusRef.current?.synth,
      onMeasureChange: (ordinal) => {
        setCurrentMeasureOrdinal(ordinal);
        const measureNumber =
          accompanimentScore.measures[ordinal - 1]?.index ?? null;
        setCurrentMeasure(measureNumber);
      },
      startMeasure: playback.startMeasure,
      endMeasure: playback.endMeasure,
      loop: playback.loop,
      onPlaybackComplete: () => {
        metronomeRef.current?.stop();
        handleRef.current = null;
        setIsPlaying(false);
        setCurrentMeasure(null);
        setCurrentMeasureOrdinal(null);
      },
    });

    const startAt = await metronomeRef.current.countIn(
      playback.countInBars,
      playback.bpm,
    );
    transport.start(startAt);
    setIsPlaying(true);
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
    setCurrentMeasureOrdinal(null);
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

  useEffect(() => {
    if (!pianoVolumeRef.current) return;
    pianoVolumeRef.current.volume.rampTo(
      Tone.gainToDb(Math.max(0.0001, playback.pianoVolume / 100)),
      0.05,
    );
  }, [playback.pianoVolume]);

  const fileLabel = pdfFile?.name ?? musicXmlFile?.name ?? "PDFを開く";

  return (
    <div className="app">
      {/* Always-visible logo badge (shown when topbar is collapsed). */}
      <div className={`logo-badge${headerVisible ? " logo-badge--hidden" : ""}`}>
        <div className="logo-badge__glyph">♩</div>
        <span className="logo-badge__name">IMSLP Accompanist</span>
      </div>

      {/* Topbar (auto-hide). */}
      <header className={`topbar${headerVisible ? "" : " topbar--collapsed"}`}>
        <div className="topbar__logo">
          <div className="topbar__glyph">♩</div>
          <span className="topbar__name">IMSLP Accompanist</span>
        </div>
        <div className="topbar__sep" />
        <div
          className={`file-chip${isLoaded ? " file-chip--loaded" : ""}`}
          onClick={() => uploaderRef.current?.open()}
          title="ファイルを開く"
        >
          <span className="file-chip__icon">{isLoaded ? "📄" : "＋"}</span>
          <span className="file-chip__name">{fileLabel}</span>
        </div>
        {isLoaded && analysis && (
          <>
            <div className="topbar__sep" />
            <span
              className="topbar__title"
              title={analysis.score_title ?? undefined}
            >
              {analysis.score_title ?? "(タイトル未検出)"}
            </span>
            <div className="topbar__sep" />
            <div className={`cache-badge${cached ? " cache-badge--hit" : ""}`}>
              <div className="cache-badge__dot" />
              {cached ? "キャッシュ済み" : "未キャッシュ"}
            </div>
            <button
              type="button"
              className="reanalyze-btn"
              disabled={isPlaying || busy}
              onClick={handleReanalyze}
              title="キャッシュを破棄してAudiverisを再起動します"
            >
              ↺ 再解析
            </button>
            <div className="topbar__sep" />
            <div className="view-tabs">
              <button
                type="button"
                className={`vtab${viewMode === "pdf" ? " vtab--on" : ""}`}
                onClick={() => setViewMode("pdf")}
                disabled={!pdfFile}
              >
                PDF
                {pdfTotalPages > 0 && (
                  <span className="vtab__pill">P.{pdfPage + 1}</span>
                )}
              </button>
              <button
                type="button"
                className={`vtab${viewMode === "sheet" ? " vtab--on" : ""}`}
                onClick={() => setViewMode("sheet")}
              >
                譜面 <span className="vtab__pill">OSMD</span>
              </button>
            </div>
          </>
        )}
        <div className="topbar__spacer" />
        <div className="status-badge">
          {statusLed && (
            <div className={`status-badge__led status-badge__led--${statusLed}`} />
          )}
          <span>{statusText}</span>
        </div>
      </header>

      {/* Body. */}
      <div className="body">
        {scene === "upload" && (
          <PdfUploader
            ref={uploaderRef}
            disabled={busy}
            onSelect={handleSelect}
          />
        )}
        {scene === "analyzing" && <Analyzing />}

        {/* Hidden file input is always mounted so the topbar file chip can
            invoke the picker even when the upload zone isn't on screen. */}
        {scene !== "upload" && (
          <PdfUploader
            ref={uploaderRef}
            disabled={busy}
            onSelect={handleSelect}
            hidden
          />
        )}

        {isLoaded && (
          <div className="score-area">
            {/* Both views stay mounted so OSMD can measure its container width
                correctly on first render — toggling display:none collapses the
                width to zero and OSMD produces a squashed layout. */}
            <div
              className={
                "view-panel" +
                (viewMode === "pdf" ? "" : " view-panel--hidden")
              }
            >
              <PdfViewer
                pdfFile={pdfFile}
                measures={analysis?.measures ?? []}
                pageSizes={analysis?.page_sizes ?? []}
                currentMeasureIndex={currentMeasure}
                zoomPct={zoom}
                pageIndex={pdfPage}
                onPageChange={setPdfPage}
                onTotalPages={setPdfTotalPages}
              />
            </div>
            <div
              className={
                "view-panel" +
                (viewMode === "sheet" ? "" : " view-panel--hidden")
              }
            >
              <SheetViewer
                musicXml={analysis?.music_xml ?? null}
                scoreTitle={analysis?.score_title ?? null}
                currentMeasureIndex={currentMeasureOrdinal}
                isPlaying={isPlaying}
                isVisible={viewMode === "sheet"}
                zoomPct={zoom}
              />
            </div>
          </div>
        )}
      </div>

      {/* Warnings (above transport). */}
      {visibleWarnings.length > 0 && !warningsDismissed && (
        <div className="warnings">
          {visibleWarnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
          <button
            type="button"
            className="warnings__close"
            onClick={() => setWarningsDismissed(true)}
            aria-label="閉じる"
            title="閉じる"
          >
            ×
          </button>
        </div>
      )}

      {/* Transport. */}
      {isLoaded && (
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
          onDownloadMusicXml={handleDownloadMusicXml}
          canDownload={!!analysis}
          timeSignature={analysis?.time_signature ?? null}
          currentMeasure={currentMeasure}
          expanded={footerVisible}
        />
      )}

      {/* Zoom control. */}
      {isLoaded && (
        <div className={`zoom-ctl${footerVisible ? "" : " zoom-ctl--hidden"}`}>
          <span className="zoom-ctl__lbl">表示</span>
          <input
            type="range"
            className="zoom-sl"
            min={40}
            max={160}
            step={5}
            value={zoom}
            onChange={(e) => setZoom(+e.target.value)}
          />
          <span className="zoom-ctl__val">{zoom}%</span>
        </div>
      )}
    </div>
  );
}

function Analyzing() {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setSec((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="analyzing">
      <div className="analyzing__ring" />
      <div className="analyzing__title">OMR 解析中…</div>
      <div className="analyzing__elapsed">
        {sec}s 経過 — 数十秒かかる場合があります
      </div>
    </div>
  );
}
