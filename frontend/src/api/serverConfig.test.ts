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

  it("stores a normalized server URL, token and engine", () => {
    saveServerConfig({
      serverUrl: " https://example.test/// ",
      apiToken: " secret ",
      omrEngine: "homr",
    });

    expect(getServerConfig()).toEqual({
      serverUrl: "https://example.test",
      apiToken: "secret",
      omrEngine: "homr",
    });
    expect(configuredServerUrl()).toBe("https://example.test");
    expect(authHeaders()).toEqual({ Authorization: "Bearer secret" });
  });

  it("migrates old saved config to Audiveris by default", () => {
    localStorage.setItem(
      "imslp-accompanist.omr-server.v1",
      JSON.stringify({ serverUrl: "http://lan.test:8000", apiToken: "old" }),
    );

    expect(getServerConfig().omrEngine).toBe("audiveris");
  });

  it("tests health, auth and server capabilities", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response('{"status":"ok"}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{"status":"ok"}', { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          '{"omr_engines":["audiveris","homr"],"per_request_engine_selection":true}',
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );

    const result = await testServerConnection({
      serverUrl: "https://example.test/",
      apiToken: "abc",
      omrEngine: "audiveris",
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
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "https://example.test/capabilities",
      { headers: { Authorization: "Bearer abc" } },
    );
  });

  it("rejects homr selection when the server cannot confirm neural support", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response('{"status":"ok"}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{"status":"ok"}', { status: 200 }))
      .mockResolvedValueOnce(new Response("not found", { status: 404 }));

    const result = await testServerConnection({
      serverUrl: "https://old.example.test",
      apiToken: "",
      omrEngine: "homr",
    });

    expect(result.ok).toBe(false);
    expect(result.message).toContain("最新版");
  });

  it("accepts homr when the server advertises per-request neural support", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response('{"status":"ok"}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{"status":"ok"}', { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          '{"omr_engines":["audiveris","homr"],"per_request_engine_selection":true}',
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );

    const result = await testServerConnection({
      serverUrl: "https://new.example.test",
      apiToken: "",
      omrEngine: "homr",
    });

    expect(result.ok).toBe(true);
  });
});
