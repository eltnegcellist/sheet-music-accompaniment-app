import { useEffect, useMemo, useRef, useState } from "react";
import * as Tone from "tone";

import {
  analyzePdf,
  getCacheList,
  getCachedAnalysis,
  getCachedPdf,
  deleteCache,
  touchCache,
  type CacheEntry,
} from "./api/analyze";
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
import { LangContext, translateWarning, translations, useLang, type Lang } from "./i18n";
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
  soloVolume: "off",
  soloInstrument: "auto",
};

type ViewMode = "pdf" | "sheet";
type Scene = "upload" | "analyzing" | "loaded";
type StatusLed = "" | "on" | "busy" | "err";

const CACHE_HIT_WARNING = "（キャッシュから復元しました）";

export default function App() {
  const [lang, setLang] = useState<Lang>(
    () => (localStorage.getItem("lang") as Lang | null) ?? "ja",
  );
  const T = translations[lang];
  const toggleLang = () =>
    setLang((l) => {
      const next = l === "ja" ? "en" : "ja";
      localStorage.setItem("lang", next);
      return next;
    });

  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [musicXmlFile, setMusicXmlFile] = useState<File | null>(null);
  const [soloPdfFile, setSoloPdfFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [playback, setPlayback] = useState<PlaybackState>(DEFAULT_PLAYBACK);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentMeasure, setCurrentMeasure] = useState<number | null>(null);
  const [currentMeasureOrdinal, setCurrentMeasureOrdinal] = useState<
    number | null
  >(null);
  const [viewMode, setViewMode] = useState<ViewMode>("sheet");
  const [pdfPage, setPdfPage] = useState(0);
  const [pdfTotalPages, setPdfTotalPages] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [warningsDismissed, setWarningsDismissed] = useState(false);
  const [cacheList, setCacheList] = useState<CacheEntry[]>([]);

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
  const visibleWarnings = useMemo(() => {
    const warnings = analysis?.warnings ?? [];
    if (warnings.includes(CACHE_HIT_WARNING)) return [];
    return warnings;
  }, [analysis]);

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

  // Status badge — derived from scene state so language changes are reflected immediately.
  const statusLed = useMemo((): StatusLed => {
    if (errorText) return "err";
    if (busy) return "busy";
    if (analysis) return "on";
    return "";
  }, [errorText, busy, analysis]);

  const statusText = useMemo(() => {
    if (errorText) return errorText;
    if (busy) return T.statusAnalyzing;
    if (analysis) {
      const accId = analysis.accompaniment_part_id ?? "?";
      const soloId = analysis.solo_part_id ?? T.soloNone;
      if (isPlaying && currentMeasure != null) {
        return T.statusPlaying(currentMeasure, measureCount);
      }
      return T.statusLoaded(measureCount, accId, soloId, tempoLabel, timeSigLabel);
    }
    return T.statusDrop;
  }, [T, errorText, busy, analysis, isPlaying, currentMeasure, measureCount, tempoLabel, timeSigLabel]);

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
      setErrorText(`${T.errorPrefix}${(err as Error).message}`);
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

  const handleBackToUpload = () => {
    handleStop();
    setAnalysis(null);
    setPdfFile(null);
    setMusicXmlFile(null);
    setSoloPdfFile(null);
    setErrorText(null);
    setWarningsDismissed(false);
    setPdfPage(0);
    setPdfTotalPages(0);
    setViewMode("pdf");
    getCacheList().then(setCacheList).catch(console.error);
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

  const fileLabel = pdfFile?.name ?? musicXmlFile?.name ?? T.fileLabel;

  useEffect(() => {
    // Initial fetch. In Tauri this races the sidecar's READY line
    // (which injects window.__BACKEND_URL__), so the very first call
    // can hit the localhost:8000 fallback and 404. We refresh below
    // when the Rust side fires the `backend-ready` event.
    getCacheList().then(setCacheList).catch(() => {});

    let cancelled = false;
    let unlisten: (() => void) | undefined;
    (async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        unlisten = await listen("backend-ready", () => {
          if (!cancelled) {
            getCacheList().then(setCacheList).catch(console.error);
          }
        });
      } catch {
        // Not running in Tauri (e.g. `npm run dev` standalone). The
        // initial fetch above is the canonical path in that case.
      }
    })();

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  const loadFromCache = async (entry: CacheEntry) => {
    setBusy(true);
    setErrorText(null);
    setAnalysis(null);
    setPdfFile(null);
    setCurrentMeasure(null);
    setCurrentMeasureOrdinal(null);
    try {
      const [analysisResult, pdfFileResult] = await Promise.all([
        getCachedAnalysis(entry.key, entry.param_set_id),
        getCachedPdf(entry.key, entry.param_set_id),
      ]);
      await touchCache(entry.key, entry.param_set_id).catch(() => {});
      analysisResult.music_xml = sanitizeForOsmd(analysisResult.music_xml);
      setPdfFile(pdfFileResult);
      setAnalysis(analysisResult);
      setWarningsDismissed(false);
      setPdfPage(0);
      setPdfTotalPages(0);
      setViewMode("sheet");
      setMusicXmlFile(null);
      setSoloPdfFile(null);
    } catch (err) {
      setErrorText(`${T.cacheLoadError}${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteCache = async (
    e: React.MouseEvent,
    entry: CacheEntry,
  ) => {
    e.stopPropagation();
    try {
      await deleteCache(entry.key, entry.param_set_id);
      setCacheList((prev) =>
        prev.filter(
          (c) => !(c.key === entry.key && c.param_set_id === entry.param_set_id),
        ),
      );
    } catch (err) {
      console.error("Failed to delete cache:", err);
    }
  };

  const dateLocale = lang === "ja" ? "ja-JP" : "en-US";

  return (
    <LangContext.Provider value={{ lang, T, toggleLang }}>
      <div className="app">
        {/* Always-visible logo badge (shown when topbar is collapsed). */}
        <div
          className={`logo-badge${headerVisible ? " logo-badge--hidden" : ""}${isLoaded ? " logo-badge--clickable" : ""}`}
          onClick={isLoaded ? handleBackToUpload : undefined}
          title={isLoaded ? T.backToUpload : undefined}
        >
          <div className="logo-badge__glyph">♩</div>
          <span className="logo-badge__name">IMSLP Accompanist</span>
        </div>

        {/* Topbar (auto-hide). */}
        <header className={`topbar${headerVisible ? "" : " topbar--collapsed"}`}>
          <div
            className={`topbar__logo${isLoaded ? " topbar__logo--clickable" : ""}`}
            onClick={isLoaded ? handleBackToUpload : undefined}
            title={isLoaded ? T.backToUpload : undefined}
          >
            <div className="topbar__glyph">♩</div>
            <span className="topbar__name">IMSLP Accompanist</span>
          </div>
          <div className="topbar__sep" />
          <div className={`file-chip${isLoaded ? " file-chip--loaded" : ""}`}>
            <span className="file-chip__icon">{isLoaded ? "📄" : "＋"}</span>
            <span className="file-chip__name">{fileLabel}</span>
          </div>
          {isLoaded && analysis && (
            <>
              <div className="topbar__sep" />
              <button
                type="button"
                className="reanalyze-btn"
                onClick={() => uploaderRef.current?.open()}
                title={T.uploadAnotherTitle}
              >
                {T.uploadAnother}
              </button>
              <button
                type="button"
                className="reanalyze-btn"
                disabled={isPlaying || busy}
                onClick={handleReanalyze}
                title={T.reanalyzeTitle}
              >
                {T.reanalyze}
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
                  {T.tabSheet} <span className="vtab__pill">OSMD</span>
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
            <div
              className="upload-container"
              style={{
                display: "flex",
                flexDirection: "column",
                height: "100%",
                overflowY: "auto",
              }}
            >
              <PdfUploader
                ref={uploaderRef}
                disabled={busy}
                onSelect={handleSelect}
              />
              <div className="lang-switch">
                <button
                  type="button"
                  className={`lang-switch__opt${lang === "ja" ? " lang-switch__opt--on" : ""}`}
                  onClick={() => lang !== "ja" && toggleLang()}
                >
                  日本語
                </button>
                <span className="lang-switch__sep">|</span>
                <button
                  type="button"
                  className={`lang-switch__opt${lang === "en" ? " lang-switch__opt--on" : ""}`}
                  onClick={() => lang !== "en" && toggleLang()}
                >
                  English
                </button>
              </div>
              {cacheList.length > 0 && (
                <div className="cache-list-container">
                  <h3 className="cache-list-title">{T.recentlyOpened}</h3>
                  <div className="cache-list">
                    {cacheList.map((c) => (
                      <div
                        key={`${c.key}-${c.param_set_id}`}
                        className="cache-item"
                        onClick={() => loadFromCache(c)}
                      >
                        <span className="cache-item__title">{c.pdf_name}</span>
                        <span className="cache-item__date">
                          {new Date(c.timestamp * 1000).toLocaleDateString(dateLocale)}
                        </span>
                        <button
                          type="button"
                          className="cache-item__delete"
                          onClick={(e) => handleDeleteCache(e, c)}
                          title={T.deleteCache}
                          aria-label={T.deleteCache}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
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
                  currentMeasureIndex={currentMeasure}
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
              <div key={i}>⚠ {translateWarning(w, lang)}</div>
            ))}
            <button
              type="button"
              className="warnings__close"
              onClick={() => setWarningsDismissed(true)}
              aria-label={T.close}
              title={T.close}
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
            <span className="zoom-ctl__lbl">{T.zoomLabel}</span>
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
    </LangContext.Provider>
  );
}

function Analyzing() {
  const { T } = useLang();
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setSec((s) => s + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="analyzing">
      <div className="analyzing__ring" />
      <div className="analyzing__title">{T.analyzingTitle}</div>
      <div className="analyzing__elapsed">{T.analyzingElapsed(sec)}</div>
    </div>
  );
}
