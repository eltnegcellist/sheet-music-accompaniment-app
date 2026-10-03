import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ save: vi.fn(), write: vi.fn() }));
vi.mock("@tauri-apps/api/dialog", () => ({ save: mocks.save }));
vi.mock("@tauri-apps/api/fs", () => ({ writeTextFile: mocks.write }));
import { exportMusicXml } from "./exportMusicXml";

describe("Mac MusicXML export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.__BACKEND_URL__ = "http://127.0.0.1:8000";
    mocks.write.mockResolvedValue(undefined);
  });
  it("writes the original XML to the user-selected path", async () => {
    mocks.save.mockResolvedValue("/chosen/score.musicxml");
    await exportMusicXml("score.musicxml", "<score-partwise/>");
    expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ defaultPath: "score.musicxml" }));
    expect(mocks.write).toHaveBeenCalledWith("/chosen/score.musicxml", "<score-partwise/>");
  });
  it("does not write when the user cancels", async () => {
    mocks.save.mockResolvedValue(null);
    await exportMusicXml("score.musicxml", "<score-partwise/>");
    expect(mocks.write).not.toHaveBeenCalled();
  });
  it("propagates save failures for the UI to display", async () => {
    mocks.save.mockResolvedValue("/chosen/score.musicxml");
    mocks.write.mockRejectedValueOnce(new Error("disk full"));
    await expect(exportMusicXml("score.musicxml", "xml")).rejects.toThrow("disk full");
  });
});
