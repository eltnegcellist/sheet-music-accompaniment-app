import type { OmrEngine } from "./serverConfig";

const STORAGE_KEY = "imslp-accompanist.desktop-omr.v1";

export function isDesktopApp(): boolean {
  return typeof window !== "undefined" && Boolean(
    window.__BACKEND_URL__ ||
    (window as Window & { __TAURI_IPC__?: unknown }).__TAURI_IPC__,
  );
}

export function desktopOmrEngine(): OmrEngine {
  try {
    const engine = window.localStorage.getItem(STORAGE_KEY);
    return engine === "homr" || engine === "hybrid" ? engine : "audiveris";
  } catch {
    return "audiveris";
  }
}

export function saveDesktopOmrEngine(engine: OmrEngine): void {
  window.localStorage.setItem(STORAGE_KEY, engine);
}
