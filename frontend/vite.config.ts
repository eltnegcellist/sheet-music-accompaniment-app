/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // Docker Desktop on Windows/macOS doesn't propagate inotify events through
    // bind mounts, so Vite's native file watcher misses edits made on the host.
    // Polling is slower but works reliably — without it HMR silently goes stale
    // after the first successful build.
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
  optimizeDeps: {
    exclude: ["pdfjs-dist"],
  },
  test: {
    environment: "happy-dom",
  },
});
