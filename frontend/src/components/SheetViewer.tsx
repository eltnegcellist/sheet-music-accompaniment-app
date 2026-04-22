import { useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

import { sanitizeForOsmd } from "../music/sanitize";

interface Props {
  musicXml: string | null;
  scoreTitle: string | null;
  currentMeasureIndex: number | null;
  isPlaying: boolean;
  isVisible: boolean;
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
}: Props) {
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
    setStatus("譜面を生成中…");

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
        setStatus("譜面を生成中… (元XMLでリトライ)");
        try {
          // OSMD holds internal state from the failed attempt; discard it.
          container.innerHTML = "";
          await tryLoad(musicXml);
          if (!cancelled) {
            setStatus(
              "サニタイズなしで表示しました (詳細はコンソール参照)",
            );
          }
        } catch (retryErr) {
          if (cancelled) return;
          console.error("[osmd] sanitized render also failed", retryErr);
          setStatus(
            `譜面のレンダリングに失敗しました: ${
              (retryErr as Error).message
            }`,
          );
        }
      }
    })();

    return () => {
      cancelled = true;
      osmdRef.current = null;
      lastSyncedMeasureRef.current = null;
    };
  }, [musicXml]);

  useEffect(() => {
    if (isPlaying) return;
    lastSyncedMeasureRef.current = null;
  }, [isPlaying]);

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
      {scoreTitle && <h3 className="sheet-viewer__title">{scoreTitle}</h3>}
      {status && <div className="sheet-viewer__status">{status}</div>}
      <div ref={containerRef} />
    </div>
  );
}
