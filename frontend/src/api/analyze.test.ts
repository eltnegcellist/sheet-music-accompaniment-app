import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { analyzePdf, getCacheList } from "./analyze";
import { saveServerConfig } from "./serverConfig";

// resolveBackendUrl is module-private, but every public client function
// reads through `backendUrl()` so we can pin the priority chain by
// stubbing fetch and asserting on the URL it was called with.

describe("backend URL resolution", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.clear();
    delete (window as { __BACKEND_URL__?: string }).__BACKEND_URL__;
    // import.meta.env is read-only at runtime under Vitest; we can't undo
    // a value Vite injected at build time. Each test that needs a
    // specific value sets / unsets `window.__BACKEND_URL__` instead,
    // which has higher priority than the env var.
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    delete (window as { __BACKEND_URL__?: string }).__BACKEND_URL__;
    vi.restoreAllMocks();
  });

  function captureFetchUrl(): { url: string | null } {
    const captured: { url: string | null } = { url: null };
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      captured.url = typeof input === "string" ? input : input.toString();
      return new Response("[]", { status: 200, headers: { "content-type": "application/json" } });
    }) as unknown as typeof fetch;
    return captured;
  }

  it("uses window.__BACKEND_URL__ when Tauri injects it", async () => {
    (window as { __BACKEND_URL__?: string }).__BACKEND_URL__ = "http://127.0.0.1:39871";
    const captured = captureFetchUrl();

    await getCacheList();

    expect(captured.url).toBe("http://127.0.0.1:39871/cache");
  });

  it("re-reads window.__BACKEND_URL__ on each call (late injection)", async () => {
    const captured = captureFetchUrl();

    // First call before injection — falls back to localhost:8000.
    await getCacheList();
    expect(captured.url).toBe("http://localhost:8000/cache");

    // Tauri-style late injection.
    (window as { __BACKEND_URL__?: string }).__BACKEND_URL__ = "http://127.0.0.1:50000";
    await getCacheList();
    expect(captured.url).toBe("http://127.0.0.1:50000/cache");
  });

  it("falls back to localhost:8000 when no override is set", async () => {
    const captured = captureFetchUrl();
    await getCacheList();
    // Either the localhost fallback or whatever VITE_BACKEND_URL was
    // baked in at test build time. Accept anything that ends with
    // /cache and starts with http(s) so the test is robust to env
    // overrides in CI.
    expect(captured.url).toMatch(/^https?:\/\/.+\/cache$/);
  });
});


describe("self-hosted OMR engine selection", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("sends the selected neural engine with Android/self-hosted analyze", async () => {
    saveServerConfig({
      serverUrl: "https://omr.example.test",
      apiToken: "token",
      omrEngine: "homr",
    });

    let requestBody: FormData | null = null;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            omr_engines: ["audiveris", "homr"],
            per_request_engine_selection: true,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockImplementationOnce(async (_input: RequestInfo | URL, init?: RequestInit) => {
        requestBody = init?.body as FormData;
        return new Response(
          JSON.stringify({
            music_xml: "<score-partwise/>",
            omr_engine: "homr",
            measures: [],
            warnings: [],
            page_sizes: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const pdf = new File(["pdf"], "score.pdf", { type: "application/pdf" });
    await analyzePdf(pdf);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "https://omr.example.test/capabilities",
      { headers: { Authorization: "Bearer token" } },
    );
    expect(requestBody?.get("omr_engine")).toBe("homr");
  });
});


  it("refuses neural analysis before upload when server capabilities are missing", async () => {
    saveServerConfig({
      serverUrl: "https://old.example.test",
      apiToken: "",
      omrEngine: "homr",
    });

    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("not found", { status: 404 }));

    const pdf = new File(["pdf"], "score.pdf", { type: "application/pdf" });

    await expect(analyzePdf(pdf)).rejects.toThrow("最新版");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
