import type { AnalyzeResponse } from "../types";

const BACKEND_URL =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ??
  "http://localhost:8000";

export interface AnalyzeOptions {
  /** Optional second PDF that contains only the solo part. When provided
   *  the backend uses it to refine solo recognition. */
  soloPdf?: File;
  /** When true, the backend ignores any cached result and re-runs OMR. */
  force?: boolean;
}

export async function analyzePdf(
  pdf?: File,
  musicXml?: File,
  options: AnalyzeOptions = {},
): Promise<AnalyzeResponse> {
  if (!pdf && !musicXml) {
    throw new Error("PDF か MusicXML のどちらかを選択してください。");
  }
  const form = new FormData();
  if (pdf) {
    form.append("pdf", pdf);
  }
  if (musicXml) {
    form.append("music_xml", musicXml);
  }
  if (options.soloPdf) {
    form.append("solo_pdf", options.soloPdf);
  }
  if (options.force) {
    form.append("force", "true");
  }

  const response = await fetch(`${BACKEND_URL}/analyze`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Backend error ${response.status}: ${text}`);
  }
  return (await response.json()) as AnalyzeResponse;
}

export interface CacheEntry {
  key: string;
  param_set_id: string;
  score_title: string;
  timestamp: number;
}

export async function getCacheList(): Promise<CacheEntry[]> {
  const response = await fetch(`${BACKEND_URL}/cache`);
  if (!response.ok) throw new Error("Failed to fetch cache list");
  return (await response.json()) as CacheEntry[];
}

export async function getCachedAnalysis(
  key: string,
  paramSetId: string,
): Promise<AnalyzeResponse> {
  const response = await fetch(`${BACKEND_URL}/cache/${key}/${paramSetId}`);
  if (!response.ok) throw new Error("Failed to fetch cached analysis");
  return (await response.json()) as AnalyzeResponse;
}

export async function getCachedPdf(key: string, paramSetId: string): Promise<File> {
  const response = await fetch(`${BACKEND_URL}/cache/${key}/${paramSetId}/pdf`);
  if (!response.ok) throw new Error("Failed to fetch cached PDF");
  const blob = await response.blob();
  return new File([blob], "cached_score.pdf", { type: "application/pdf" });
}
