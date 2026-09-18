import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  authHeaders,
  configuredServerUrl,
  getServerConfig,
  saveServerConfig,
  testServerConnection,
} from "./serverConfig";

describe("OMR server config", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("stores a normalized server URL and token", () => {
    saveServerConfig({
      serverUrl: " https://example.test/// ",
      apiToken: " secret ",
    });

    expect(getServerConfig()).toEqual({
      serverUrl: "https://example.test",
      apiToken: "secret",
    });
    expect(configuredServerUrl()).toBe("https://example.test");
    expect(authHeaders()).toEqual({ Authorization: "Bearer secret" });
  });

  it("tests both health and authenticated endpoint", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response('{"status":"ok"}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{"status":"ok"}', { status: 200 }));

    const result = await testServerConnection({
      serverUrl: "https://example.test/",
      apiToken: "abc",
    });

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "https://example.test/health",
      { headers: { Authorization: "Bearer abc" } },
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://example.test/auth/check",
      { headers: { Authorization: "Bearer abc" } },
    );
  });
});
