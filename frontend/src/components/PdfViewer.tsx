import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import { useLang } from "../i18n";
import type { MeasureBox } from "../types";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;

interface Props {
  pdfFile: File | null;
  measures: MeasureBox[];
  pageSizes: [number, number][];
  currentMeasureIndex: number | null;
  /** Display zoom percentage (40–160). 100% maps to the baseline pdf.js scale. */
  zoomPct?: number;
  /** Controlled page index (0-based). When provided the parent owns paging. */
  pageIndex?: number;
  onPageChange?: (page: number) => void;
  onTotalPages?: (total: number) => void;
}

const BASE_SCALE = 1.4;

export function PdfViewer({
  pdfFile,
  measures,
  pageSizes,
  currentMeasureIndex,
  zoomPct = 100,
  pageIndex: pageIndexProp,
  onPageChange,
  onTotalPages,
}: Props) {
  const { T } = useLang();
  const pageCanvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [internalPage, setInternalPage] = useState(0);
  const pageIndex = pageIndexProp ?? internalPage;
  const setPage = (n: number) => {
    if (onPageChange) onPageChange(n);
    else setInternalPage(n);
  };
  const [renderSize, setRenderSize] = useState<{ w: number; h: number } | null>(
    null,
  );

  useEffect(() => {
    if (!pdfFile) {
      setPdf(null);
      onTotalPages?.(0);
      return;
    }
    let cancelled = false;
    pdfFile.arrayBuffer().then(async (buffer) => {
      const loaded = await pdfjsLib.getDocument({ data: buffer }).promise;
      if (!cancelled) {
        setPdf(loaded);
        setPage(0);
        onTotalPages?.(loaded.numPages);
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdfFile]);

  useEffect(() => {
    if (currentMeasureIndex == null) return;
    const m = measures.find((x) => x.index === currentMeasureIndex);
    if (m && m.page !== pageIndex) setPage(m.page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentMeasureIndex, measures, pageIndex]);

  useEffect(() => {
    if (!pdf || !pageCanvasRef.current) return;
    let cancelled = false;
    (async () => {
      const page = await pdf.getPage(pageIndex + 1);
      const viewport = page.getViewport({ scale: BASE_SCALE * (zoomPct / 100) });
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
  }, [pdf, pageIndex, zoomPct]);

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

    const pageDims = pageSizes[m.page];
    if (!pageDims) return;
    const [imgW, imgH] = pageDims;
    if (!imgW || !imgH) return;
    const scaleX = canvas.width / imgW;
    const scaleY = canvas.height / imgH;
    const [x, y, w, h] = m.bbox;
    ctx.fillStyle = "rgba(255, 198, 45, 0.28)";
    ctx.strokeStyle = "rgba(255, 198, 45, 0.85)";
    ctx.lineWidth = 1.5;
    ctx.fillRect(x * scaleX, y * scaleY, w * scaleX, h * scaleY);
    ctx.strokeRect(x * scaleX, y * scaleY, w * scaleX, h * scaleY);
  }, [currentMeasureIndex, measures, pageIndex, pageSizes, renderSize]);

  if (!pdfFile) return null;
  const totalPages = pdf?.numPages ?? 0;

  return (
    <>
      <div className="score-paper">
        <div className="score-paper__inner">
          <canvas ref={pageCanvasRef} />
          <canvas ref={overlayCanvasRef} className="pdf-overlay" />
        </div>
      </div>
      {totalPages > 1 && (
        <div className="pager">
          <button
            type="button"
            className="pager__btn"
            disabled={pageIndex === 0}
            onClick={() => setPage(Math.max(0, pageIndex - 1))}
          >
            {T.prevPage}
          </button>
          <span className="pager__info">
            {pageIndex + 1} / {totalPages}
          </span>
          <button
            type="button"
            className="pager__btn"
            disabled={pageIndex >= totalPages - 1}
            onClick={() => setPage(Math.min(totalPages - 1, pageIndex + 1))}
          >
            {T.nextPage}
          </button>
        </div>
      )}
    </>
  );
}
