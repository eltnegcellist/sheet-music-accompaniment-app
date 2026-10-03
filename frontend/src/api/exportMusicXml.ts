import { isDesktopApp } from "./desktopConfig";

export async function exportMusicXml(fileName: string, xml: string): Promise<void> {
  const mime = "application/vnd.recordare.musicxml+xml";
  if (window.AndroidBridge?.saveTextFile) {
    window.AndroidBridge.saveTextFile(fileName, mime, xml);
    return;
  }
  if (isDesktopApp()) {
    const { save } = await import("@tauri-apps/api/dialog");
    const path = await save({
      defaultPath: fileName,
      filters: [{ name: "MusicXML", extensions: ["musicxml", "xml"] }],
    });
    if (!path) return;
    const { writeTextFile } = await import("@tauri-apps/api/fs");
    await writeTextFile(path, xml);
    return;
  }
  const url = URL.createObjectURL(new Blob([xml], { type: mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Give the browser time to start reading the blob before revoking it.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
