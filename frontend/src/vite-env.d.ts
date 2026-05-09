/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Tauri's setup hook injects this on window before the WebView runs
// any module code. Outside Tauri it stays undefined and the API
// client falls back to VITE_BACKEND_URL / localhost.
interface Window {
  __BACKEND_URL__?: string;
}
