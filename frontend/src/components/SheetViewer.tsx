import { useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

import { useLang } from "../i18n";
import { sanitizeForOsmd } from "../music/sanitize";

interface Props {
  musicXml: string | null;
  scoreTitle: string | null;
  currentMeasureIndex: number | null;
  isPlaying: boolean;
  isVisible: boolean;
  zoomPct?: number;
}

/**
 * Render the parsed MusicXML as SVG via OSMD and drive a cursor to the
 * currently-playing measure.
 *
 * We always sanitize before rendering so dropped/invalid OMR fragments can be
 * normalized consistently (including missing-measure padding), not only on
 * fatal render errors.
 */
export function SheetViewer({
  musicXml,
  scoreTitle,
  currentMeasureIndex,
  isPlaying,
  isVisible,
  zoomPct = 100,
}: Props) {
  const { T } = useLang();
  const tRef = useRef(T);
  tRef.current = T;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const lastSyncedMeasureRef = useRef<number | null>(null);
  const [status, setStatus] = useState<string>("");
  const debugEnabled =
    typeof window !== "undefined" &&
    Boolean((window as { __IMSLP_DEBUG__?: boolean }).__IMSLP_DEBUG__);

  // Create / reload OSMD whenever the source XML changes.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !musicXml) return;

    let cancelled = false;

    container.innerHTML = "";
    lastSyncedMeasureRef.current = null;
    setStatus(tRef.current.generatingSheet);

    const osmd = new OpenSheetMusicDisplay(container, {
      autoResize: true,
      backend: "svg",
      drawTitle: false,
      drawComposer: true,
      drawCredits: false,
      followCursor: true,
    });
    osmdRef.current = osmd;

    const tryLoad = async (xml: string): Promise<void> => {
      await osmd.load(xml);
      osmd.Zoom = zoomPct / 100;
      osmd.render();
    };

    (async () => {
      const sanitizedXml = sanitizeForOsmd(musicXml);
      try {
        await tryLoad(sanitizedXml);
        if (!cancelled) setStatus("");
      } catch (err) {
        if (cancelled) return;
        console.warn("[osmd] sanitized render failed, retrying raw xml", err);
        setStatus(tRef.current.generatingSheetRetry);
        try {
          // OSMD holds internal state from the failed attempt; discard it.
          container.innerHTML = "";
          await tryLoad(musicXml);
          if (!cancelled) {
            setStatus(tRef.current.sheetNoSanitize);
          }
        } catch (retryErr) {
          if (cancelled) return;
          console.error("[osmd] sanitized render also failed", retryErr);
          setStatus(tRef.current.sheetRenderFail((retryErr as Error).message));
        }
      }
    })();

    return () => {
      cancelled = true;
      osmdRef.current = null;
      lastSyncedMeasureRef.current = null;
    };
  }, [musicXml, zoomPct]);

  useEffect(() => {
    if (isPlaying) return;
    lastSyncedMeasureRef.current = null;
  }, [isPlaying]);

  // Re-render with updated zoom without requiring MusicXML reload.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!osmd) return;

    try {
      osmd.Zoom = zoomPct / 100;
      osmd.render();
    } catch (err) {
      console.warn("[osmd] zoom update failed", err);
    }
  }, [zoomPct]);

  // Drive the cursor to the current measure while playing.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!osmd) return;
    if (!isPlaying || currentMeasureIndex === null || !isVisible) {
      try {
        osmd.cursor.hide();
      } catch {
        /* OSMD may not be ready yet; ignore */
      }
      lastSyncedMeasureRef.current = null;
      return;
    }

    try {
      const targetMeasure = Math.max(1, currentMeasureIndex);
      const lastSyncedMeasure = lastSyncedMeasureRef.current;
      osmd.cursor.show();

      let advancedSteps = 0;
      if (lastSyncedMeasure === null || targetMeasure < lastSyncedMeasure) {
        osmd.cursor.reset();
      }

      // OSMD cursor.next() advances by timestamp (note/rest), not by measure.
      // Keep stepping until the iterator reaches the target measure.
      while (
        !osmd.cursor.iterator.EndReached &&
        osmd.cursor.iterator.CurrentMeasureIndex < targetMeasure - 1
      ) {
        osmd.cursor.next();
        advancedSteps += 1;
      }

      if (debugEnabled) {
        console.debug("[sheet-cursor]", {
          targetMeasure,
          lastSyncedMeasure,
          advancedSteps,
          currentMeasureIndex: osmd.cursor.iterator.CurrentMeasureIndex,
        });
      }

      lastSyncedMeasureRef.current = targetMeasure;
    } catch (err) {
      console.warn("[osmd] cursor advance failed", err);
    }
  }, [currentMeasureIndex, isPlaying, isVisible]);


  const maxW = `calc((100vw - 48px) * ${zoomPct / 100})`;

  if (!musicXml) {
    return (
      <div className="sheet-area">
        <div className="sheet-area__status">
          {T.sheetEmpty}
        </div>
      </div>
    );
  }

  return (
    <div className="sheet-area">
      {scoreTitle && <h3 className="sheet-area__title">{scoreTitle}</h3>}
      {status && <div className="sheet-area__status">{status}</div>}
      <div className="sheet-area__osmd" ref={containerRef} />
    </div>
  );
}
