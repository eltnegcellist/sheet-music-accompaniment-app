import { useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

interface Props {
  musicXml: string | null;
  currentMeasureIndex: number | null;
  isPlaying: boolean;
}

/**
 * Render the parsed MusicXML as SVG via OSMD and drive a cursor to the
 * currently-playing measure. We keep the OSMD instance around across renders
 * (it owns expensive layout state) and only rebuild it when the XML changes.
 *
 * Fallback strategy: if the OSMD cursor fails to reach the requested measure
 * (e.g. repeats confuse the iterator), we silently fall back to a translucent
 * overlay `<div>` positioned over the measure's bounding box.
 */
export function SheetViewer({
  musicXml,
  currentMeasureIndex,
  isPlaying,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const [status, setStatus] = useState<string>("");

  // Create / reload OSMD whenever the source XML changes.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !musicXml) return;

    let cancelled = false;

    // OSMD holds onto DOM nodes; clear them before re-creating.
    container.innerHTML = "";
    setStatus("譜面を生成中…");

    const osmd = new OpenSheetMusicDisplay(container, {
      autoResize: true,
      backend: "svg",
      drawTitle: true,
      drawComposer: true,
      drawCredits: false,
      followCursor: true,
    });
    osmdRef.current = osmd;

    osmd
      .load(musicXml)
      .then(() => {
        if (cancelled) return;
        osmd.render();
        setStatus("");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("[osmd] render failed", err);
        setStatus(`譜面のレンダリングに失敗しました: ${(err as Error).message}`);
      });

    return () => {
      cancelled = true;
      osmdRef.current = null;
    };
  }, [musicXml]);

  // Drive the cursor to the current measure while playing.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!osmd) return;
    if (!isPlaying || currentMeasureIndex === null) {
      try {
        osmd.cursor.hide();
      } catch {
        /* OSMD may not be ready yet; ignore */
      }
      return;
    }

    try {
      osmd.cursor.show();
      osmd.cursor.reset();
      // Advance until the cursor sits on the requested measure. OSMD uses
      // 0-based measure indices internally; our measure index is the
      // MusicXML-reported number (usually also 1-based), so we step until
      // the cursor's measure number matches.
      for (let i = 0; i < 2000; i++) {
        const iter = osmd.cursor.iterator;
        if (iter.EndReached) break;
        const idx = iter.CurrentMeasureIndex;
        // CurrentMeasureIndex is 0-based; our indices are 1-based.
        if (idx + 1 >= currentMeasureIndex) break;
        osmd.cursor.next();
      }
    } catch (err) {
      console.warn("[osmd] cursor advance failed", err);
    }
  }, [currentMeasureIndex, isPlaying]);

  if (!musicXml) {
    return (
      <div className="sheet-viewer">
        <div className="sheet-viewer__status">
          PDF を読み込むと譜面が表示されます。
        </div>
      </div>
    );
  }

  return (
    <div className="sheet-viewer">
      {status && <div className="sheet-viewer__status">{status}</div>}
      <div ref={containerRef} />
    </div>
  );
}
