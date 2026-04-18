import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import type { MeasureBox } from "../types";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;

interface Props {
  pdfFile: File | null;
  measures: MeasureBox[];
  /** Page sizes in PDF points reported by the backend; used to map Audiveris
   * pixel coordinates onto the rendered canvas. */
  pageSizes: [number, number][];
  currentMeasureIndex: number | null;
  zoom?: number;
}

export function PdfViewer({
  pdfFile,
  measures,
  pageSizes,
  currentMeasureIndex,
  zoom = 1.4,
}: Props) {
  const pageCanvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [renderSize, setRenderSize] = useState<{ w: number; h: number } | null>(
    null,
  );

  // Load PDF when file changes.
  useEffect(() => {
    if (!pdfFile) {
      setPdf(null);
      return;
    }
    let cancelled = false;
    pdfFile.arrayBuffer().then(async (buffer) => {
      const loaded = await pdfjsLib.getDocument({ data: buffer }).promise;
      if (!cancelled) {
        setPdf(loaded);
        setPageIndex(0);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [pdfFile]);

  // Auto-flip pages so the current measure is visible.
  useEffect(() => {
    if (currentMeasureIndex == null) return;
    const m = measures.find((x) => x.index === currentMeasureIndex);
    if (m && m.page !== pageIndex) setPageIndex(m.page);
  }, [currentMeasureIndex, measures, pageIndex]);

  // Render current page.
  useEffect(() => {
    if (!pdf || !pageCanvasRef.current) return;
    let cancelled = false;
    (async () => {
      const page = await pdf.getPage(pageIndex + 1);
      const viewport = page.getViewport({ scale: zoom });
      const canvas = pageCanvasRef.current!;
      const context = canvas.getContext("2d")!;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      if (cancelled) return;
      await page.render({ canvasContext: context, viewport }).promise;
      setRenderSize({ w: viewport.width, h: viewport.height });
    })();
    return () => {
      cancelled = true;
    };
  }, [pdf, pageIndex, zoom]);

  // Draw highlight overlay.
  useEffect(() => {
    const canvas = overlayCanvasRef.current;
    if (!canvas || !renderSize) return;
    canvas.width = renderSize.w;
    canvas.height = renderSize.h;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (currentMeasureIndex == null) return;
    const m = measures.find((x) => x.index === currentMeasureIndex);
    if (!m || m.page !== pageIndex) return;

    // Map Audiveris pixel coordinates to the rendered canvas.
    const pageDims = pageSizes[m.page];
    if (!pageDims) return;
    const [imgW, imgH] = pageDims;
    if (!imgW || !imgH) return;
    const scaleX = canvas.width / imgW;
    const scaleY = canvas.height / imgH;
    const [x, y, w, h] = m.bbox;
    ctx.fillStyle = "rgba(255, 220, 80, 0.35)";
    ctx.strokeStyle = "rgba(255, 220, 80, 0.9)";
    ctx.lineWidth = 2;
    ctx.fillRect(x * scaleX, y * scaleY, w * scaleX, h * scaleY);
    ctx.strokeRect(x * scaleX, y * scaleY, w * scaleX, h * scaleY);
  }, [currentMeasureIndex, measures, pageIndex, pageSizes, renderSize]);

  if (!pdfFile) {
    return <div className="status">PDFを読み込むとここに表示されます。</div>;
  }
  const totalPages = pdf?.numPages ?? 0;

  return (
    <div>
      <div className="pdf-viewer">
        <canvas ref={pageCanvasRef} className="pdf-viewer__page" />
        <canvas ref={overlayCanvasRef} className="pdf-viewer__overlay" />
      </div>
      {totalPages > 1 && (
        <div className="pdf-viewer__pager">
          <button
            type="button"
            disabled={pageIndex === 0}
            onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
          >
            前のページ
          </button>
          <span>
            {pageIndex + 1} / {totalPages}
          </span>
          <button
            type="button"
            disabled={pageIndex >= totalPages - 1}
            onClick={() =>
              setPageIndex((i) => Math.min(totalPages - 1, i + 1))
            }
          >
            次のページ
          </button>
        </div>
      )}
    </div>
  );
}
