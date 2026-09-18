import type { AnalyzeResponse } from "../types";
import { authHeaders, configuredServerUrl } from "./serverConfig";

function resolveBackendUrl(): string {
  // Desktop Tauri injects its bundled local sidecar URL. Android has no
  // sidecar, so it falls through to the server configured in the app.
  if (typeof window !== "undefined" && window.__BACKEND_URL__) {
    return window.__BACKEND_URL__;
  }
  const configured = configuredServerUrl();
  if (configured) return configured;
  const fromEnv = import.meta.env.VITE_BACKEND_URL as string | undefined;
  if (fromEnv) return fromEnv;
  return "http://localhost:8000";
}

function backendUrl(): string {
  return resolveBackendUrl();
}

export interface AnalyzeOptions {
  /** Optional second PDF that contains only the solo part. */
  soloPdf?: File;
  /** When true, ignore a cached result and re-run OMR. */
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
  if (pdf) form.append("pdf", pdf);
  if (musicXml) form.append("music_xml", musicXml);
  if (options.soloPdf) form.append("solo_pdf", options.soloPdf);
  if (options.force) form.append("force", "true");

  const response = await fetch(`${backendUrl()}/analyze`, {
    method: "POST",
    headers: authHeaders(),
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
  pdf_name: string;
  timestamp: number;
  /** Android stores completed analyses on-device; desktop entries are server-backed. */
  source?: "server" | "local";
}

export async function getCacheList(): Promise<CacheEntry[]> {
  const response = await fetch(`${backendUrl()}/cache`, {
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch cache list");
  return (await response.json()) as CacheEntry[];
}

export async function getCachedAnalysis(
  key: string,
  paramSetId: string,
): Promise<AnalyzeResponse> {
  const response = await fetch(`${backendUrl()}/cache/${key}/${paramSetId}`, {
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error("Failed to fetch cached analysis");
  return (await response.json()) as AnalyzeResponse;
}

export async function getCachedPdf(
  key: string,
  paramSetId: string,
): Promise<File> {
  const response = await fetch(
    `${backendUrl()}/cache/${key}/${paramSetId}/pdf`,
    { headers: authHeaders() },
  );
  if (!response.ok) throw new Error("Failed to fetch cached PDF");
  const blob = await response.blob();
  return new File([blob], "cached_score.pdf", { type: "application/pdf" });
}

export async function deleteCache(
  key: string,
  paramSetId: string,
): Promise<void> {
  const response = await fetch(`${backendUrl()}/cache/${key}/${paramSetId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error("Failed to delete cache entry");
}

export async function touchCache(
  key: string,
  paramSetId: string,
): Promise<void> {
  const response = await fetch(
    `${backendUrl()}/cache/${key}/${paramSetId}/touch`,
    {
      method: "POST",
      headers: authHeaders(),
    },
  );
  if (!response.ok) throw new Error("Failed to touch cache entry");
}
