import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
const pdf = vi.hoisted(() => ({ render: vi.fn(), viewport: vi.fn() }));
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve({
    numPages: 12,
    getPage: async () => ({
      // Page 1 of the uploaded Mendelssohn PDF, in PDF points.
      getViewport: ({ scale }: { scale: number }) => {
        pdf.viewport(scale);
        return { width: 1408.25 * scale, height: 1926.25 * scale };
      },
      render: pdf.render,
    }),
  }) }),
}));
import { PdfViewer } from "./PdfViewer";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("fits an oversized PDF to the available width, then reflows on resize and zoom", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  let width = 700;
  let resize = () => {};
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(() => width);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ clearRect: vi.fn() } as unknown as CanvasRenderingContext2D);
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: () => void) { resize = callback; }
    observe() {} disconnect() {}
  });
  pdf.render.mockImplementation(() => ({ promise: Promise.resolve(), cancel: vi.fn() }));
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const file = new File(["pdf"], "Mendelssohn.pdf");
  const view = (zoomPct = 100) => <PdfViewer pdfFile={file} measures={[]} pageSizes={[]} currentMeasureIndex={null} zoomPct={zoomPct} />;
  try {
    await act(async () => { root.render(view()); });
    const canvas = host.querySelector("canvas")!;
    expect(canvas.width).toBe(700);
    expect(canvas.height).toBeCloseTo(957, -1);
    width = 500;
    await act(async () => { resize(); });
    expect(canvas.width).toBe(500);
    await act(async () => { root.render(view(160)); });
    expect(canvas.width).toBeCloseTo(800);
  } finally {
    await act(async () => { root.unmount(); });
    host.remove();
  }
});
