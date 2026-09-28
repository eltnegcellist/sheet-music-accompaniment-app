import type { AnalyzeResponse } from "../types";
import {
  authHeaders,
  configuredOmrEngine,
  configuredServerUrl,
} from "./serverConfig";

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

  const serverUrl = configuredServerUrl();
  const selectedEngine = configuredOmrEngine();

  // A pre-v0.2.3 server may silently ignore unknown multipart fields.
  // For neural requests, require explicit capability support before uploading
  // the PDF so a "homr" selection can never fall back to Audiveris unnoticed.
  if (serverUrl && selectedEngine === "homr") {
    const capabilities = await fetch(`${serverUrl}/capabilities`, {
      headers: authHeaders(),
    });
    if (!capabilities.ok) {
      throw new Error(
        "OMRサーバーがニューラルOMR対応を確認できません。サーバーを最新版へ更新してください。",
      );
    }
    const body = (await capabilities.json()) as {
      omr_engines?: unknown;
      per_request_engine_selection?: unknown;
    };
    const engines = Array.isArray(body.omr_engines)
      ? body.omr_engines.filter((item): item is string => typeof item === "string")
      : [];
    if (!engines.includes("homr") || body.per_request_engine_selection !== true) {
      throw new Error(
        "このOMRサーバーはhomrの選択に対応していません。サーバーを最新版へ更新してください。",
      );
    }
  }

  const serverUrl = configuredServerUrl();
  const selectedEngine = configuredOmrEngine();

  // A pre-v0.2.3 server may silently ignore unknown multipart fields.
  // For neural requests, require explicit capability support before uploading
  // the PDF so a "homr" selection can never fall back to Audiveris unnoticed.
  if (serverUrl && selectedEngine === "homr") {
    const capabilities = await fetch(`${serverUrl}/capabilities`, {
      headers: authHeaders(),
    });
    if (!capabilities.ok) {
      throw new Error(
        "OMRサーバーがニューラルOMR対応を確認できません。サーバーを最新版へ更新してください。",
      );
    }
    const body = (await capabilities.json()) as {
      omr_engines?: unknown;
      per_request_engine_selection?: unknown;
    };
    const engines = Array.isArray(body.omr_engines)
      ? body.omr_engines.filter((item): item is string => typeof item === "string")
      : [];
    if (!engines.includes("homr") || body.per_request_engine_selection !== true) {
      throw new Error(
        "このOMRサーバーはhomrの選択に対応していません。サーバーを最新版へ更新してください。",
      );
    }
  }

  const form = new FormData();
  if (pdf) form.append("pdf", pdf);
  if (musicXml) form.append("music_xml", musicXml);
  if (options.soloPdf) form.append("solo_pdf", options.soloPdf);
  if (options.force) form.append("force", "true");
  // Only self-hosted/Android server requests carry an engine preference.
  // Desktop Tauri continues to follow PIPELINE_PARAM_SET in its sidecar.
  if (serverUrl) {
    form.append("omr_engine", selectedEngine);
  }

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
  /** Present for Android-local entries so two OMR engines can coexist. */
  engine?: "audiveris" | "homr";
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
