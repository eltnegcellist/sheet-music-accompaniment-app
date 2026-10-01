import { afterEach, describe, expect, it } from "vitest";
import { desktopOmrEngine, saveDesktopOmrEngine } from "./desktopConfig";
import { configuredOmrEngine, saveServerConfig } from "./serverConfig";

afterEach(() => localStorage.clear());

describe("desktop engine preference", () => {
  it("defaults to Audiveris independently of Android settings", () => {
    saveServerConfig({ serverUrl: "https://omr.example.test", apiToken: "", omrEngine: "hybrid" });
    expect(desktopOmrEngine()).toBe("audiveris");
    saveDesktopOmrEngine("homr");
    expect(desktopOmrEngine()).toBe("homr");
    expect(configuredOmrEngine()).toBe("hybrid");
  });
});
