import { createContext, useContext } from "react";

export type Lang = "ja" | "en";

const ja = {
  // Status badge
  statusDrop: "PDFをドロップして開始",
  statusAnalyzing: "OMR 解析中…",
  statusPlaying: (m: number, total: number) => `再生中 — 小節 ${m} / ${total}`,
  statusLoaded: (
    measures: number,
    accId: string,
    soloId: string,
    tempo: string,
    timeSig: string,
  ) => `解析完了 · ${measures}小節 · ${accId}+${soloId} · ${tempo} · ${timeSig}`,
  soloNone: "なし",
  errorPrefix: "エラー: ",
  // Header / topbar
  backToUpload: "アップロード画面に戻る",
  fileLabel: "PDFを開く",
  uploadAnother: "＋ 別のPDFをアップロード",
  uploadAnotherTitle: "別のPDFをアップロード",
  reanalyze: "↺ もう一度PDFを再解析",
  reanalyzeTitle: "キャッシュを破棄してAudiverisを再起動します",
  tabSheet: "譜面",
  // Cache list
  recentlyOpened: "最近の曲から開く",
  deleteCache: "キャッシュを削除",
  cacheLoadError: "キャッシュの読み込みに失敗しました: ",
  // Warnings / zoom
  close: "閉じる",
  zoomLabel: "表示",
  // Analyzing screen
  analyzingTitle: "OMR 解析中…",
  analyzingElapsed: (sec: number) => `${sec}s 経過 — 数分かかる場合があります`,
  // PdfUploader
  dropTitle: "楽譜PDFをドロップ",
  clickToSelect: "クリックしてファイルを選択",
  pdfOnly: ".pdf のみ、または",
  skipOmr: "で OMR をスキップ",
  uploaderHint: "IMSLP などから取得した伴奏パート譜に対応",
  // PlaybackControls — instruments
  instrAuto: "自動検出",
  instrViolin: "ヴァイオリン",
  instrCello: "チェロ",
  instrFlute: "フルート",
  instrClarinet: "クラリネット",
  instrTrumpet: "トランペット",
  instrSax: "サックス",
  instrGuitar: "ギター",
  // PlaybackControls — solo volume
  soloVolNormal: "普通",
  soloVolKaraoke: "カラオケ",
  soloVolOff: "無し",
  // PlaybackControls — controls
  playBtn: "再生",
  stopBtn: "停止",
  measureLabel: "小節",
  timeSig: "拍子",
  tempo: "テンポ",
  accompVol: "伴奏音量",
  playRange: "再生範囲",
  reset: "リセット",
  countIn: "カウントイン",
  countInNone: "なし",
  countIn1: "1小節",
  countIn2: "2小節",
  countIn4: "4小節",
  loop: "ループ",
  metronome: "メトロノーム",
  soloInstr: "ソロ楽器",
  soloInstrNone: "(なし)",
  soloVol: "ソロ音量",
  downloadMusicXml: "解析済みMusicXMLをダウンロード",
  // PdfViewer
  prevPage: "← 前ページ",
  nextPage: "次ページ →",
  // SheetViewer
  generatingSheet: "譜面を生成中…",
  generatingSheetRetry: "譜面を生成中… (元XMLでリトライ)",
  sheetNoSanitize: "サニタイズなしで表示しました (詳細はコンソール参照)",
  sheetRenderFail: (msg: string) => `譜面のレンダリングに失敗しました: ${msg}`,
  sheetEmpty: "PDF を読み込むと譜面が表示されます。",
};

const en: typeof ja = {
  statusDrop: "Drop a PDF to start",
  statusAnalyzing: "OMR analyzing…",
  statusPlaying: (m: number, total: number) => `Playing — Measure ${m} / ${total}`,
  statusLoaded: (
    measures: number,
    accId: string,
    soloId: string,
    tempo: string,
    timeSig: string,
  ) =>
    `Analysis complete · ${measures} measure${measures !== 1 ? "s" : ""} · ${accId}+${soloId} · ${tempo} · ${timeSig}`,
  soloNone: "None",
  errorPrefix: "Error: ",
  backToUpload: "Back to upload",
  fileLabel: "Open PDF",
  uploadAnother: "＋ Upload another PDF",
  uploadAnotherTitle: "Upload another PDF",
  reanalyze: "↺ Re-analyze PDF",
  reanalyzeTitle: "Discard cache and restart Audiveris",
  tabSheet: "Sheet",
  recentlyOpened: "Recently opened",
  deleteCache: "Delete cache",
  cacheLoadError: "Failed to load cache: ",
  close: "Close",
  zoomLabel: "Zoom",
  analyzingTitle: "OMR Analyzing…",
  analyzingElapsed: (sec: number) => `${sec}s elapsed — may take several minutes`,
  dropTitle: "Drop sheet music PDF",
  clickToSelect: "Click to select a file",
  pdfOnly: ".pdf only, or",
  skipOmr: " to skip OMR",
  uploaderHint: "Supports accompaniment part scores from IMSLP and similar",
  instrAuto: "Auto-detect",
  instrViolin: "Violin",
  instrCello: "Cello",
  instrFlute: "Flute",
  instrClarinet: "Clarinet",
  instrTrumpet: "Trumpet",
  instrSax: "Saxophone",
  instrGuitar: "Guitar",
  soloVolNormal: "Normal",
  soloVolKaraoke: "Karaoke",
  soloVolOff: "Off",
  playBtn: "Play",
  stopBtn: "Stop",
  measureLabel: "Measure",
  timeSig: "Time sig.",
  tempo: "Tempo",
  accompVol: "Accomp. vol.",
  playRange: "Play range",
  reset: "Reset",
  countIn: "Count-in",
  countInNone: "None",
  countIn1: "1 bar",
  countIn2: "2 bars",
  countIn4: "4 bars",
  loop: "Loop",
  metronome: "Metronome",
  soloInstr: "Solo instrument",
  soloInstrNone: "(none)",
  soloVol: "Solo volume",
  downloadMusicXml: "Download analyzed MusicXML",
  prevPage: "← Prev",
  nextPage: "Next →",
  generatingSheet: "Generating sheet…",
  generatingSheetRetry: "Generating sheet… (retrying with original XML)",
  sheetNoSanitize: "Displayed without sanitization (see console)",
  sheetRenderFail: (msg: string) => `Failed to render sheet: ${msg}`,
  sheetEmpty: "Load a PDF to display the sheet music.",
};

export const translations = { ja, en };
export type Translations = typeof ja;

/** Translate a backend-generated warning string for display in the given language. */
export function translateWarning(w: string, lang: Lang): string {
  if (lang === "ja") return w;

  // Static messages
  if (w === "MusicXML のみで解析しました。PDF連動ハイライトは利用できません。")
    return "Analyzed with MusicXML only. PDF measure highlighting is unavailable.";
  if (w.startsWith("Audiveris をスキップしてアップロードされた MusicXML で解析しました"))
    return "Analyzed with uploaded MusicXML, skipping Audiveris. Measure highlighting unavailable.";
  if (w === "Uploaded MusicXML did not look valid; falling back to OMR.")
    return w; // already English

  // Dynamic: solo-only score errors
  const soloFail = w.match(/^ソロ専用譜の解析に失敗しました \((.+)\)/);
  if (soloFail)
    return `Failed to analyze solo-only score (${soloFail[1]}); using full-score result only.`;

  const soloPipeline = w.match(/^ソロ専用譜のパイプラインが中断しました \((.+)\)/);
  if (soloPipeline)
    return `Solo-only score pipeline aborted (${soloPipeline[1]}).`;

  // "[ソロ譜] ..." prefix
  const soloPrefix = w.match(/^\[ソロ譜\] (.*)/s);
  if (soloPrefix)
    return `[Solo score] ${soloPrefix[1]}`;

  // MusicXML-based solo detection notice (long dynamic message)
  const soloDetect = w.match(
    /^MusicXML 解析の結果、(\d+)〜(\d+) 小節 \(PDF (\d+)〜(\d+) ページ\) で伴奏パートが (\d+) 小節連続して空のため、(前半|後半)をソロ専用譜と判定し再解析します。/,
  );
  if (soloDetect) {
    const half = soloDetect[6] === "前半" ? "first half" : "second half";
    return (
      `Based on MusicXML analysis, measures ${soloDetect[1]}–${soloDetect[2]} ` +
      `(PDF pages ${soloDetect[3]}–${soloDetect[4]}) have ${soloDetect[5]} consecutive ` +
      `empty accompaniment measures. The ${half} was identified as the solo-only score; re-analyzing.`
    );
  }

  return w; // unknown warning — show as-is
}

export const LangContext = createContext<{
  lang: Lang;
  T: Translations;
  toggleLang: () => void;
}>({
  lang: "ja",
  T: ja,
  toggleLang: () => {},
});

export function useLang() {
  return useContext(LangContext);
}
