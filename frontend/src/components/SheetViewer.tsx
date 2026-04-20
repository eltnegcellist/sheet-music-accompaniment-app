import { useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

import { sanitizeForOsmd } from "../music/sanitize";

interface Props {
  musicXml: string | null;
  currentMeasureIndex: number | null;
  isPlaying: boolean;
}

/**
 * Render the parsed MusicXML as SVG via OSMD and drive a cursor to the
 * currently-playing measure.
 *
 * Failure recovery: if OSMD fails on the raw MusicXML (typically with a
 * `realValue` / Fraction error when Audiveris emits an incomplete element),
 * we retry once against a sanitized copy of the XML. This means a flaky
 * first render gives the user a usable second render rather than a blank
 * tab, at the cost of silently dropping known-broken fragments.
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

    const tryLoad = async (xml: string): Promise<void> => {
      await osmd.load(xml);
      osmd.render();
    };

    (async () => {
      try {
        await tryLoad(musicXml);
        if (!cancelled) setStatus("");
      } catch (err) {
        if (cancelled) return;
        console.warn("[osmd] initial render failed, retrying sanitized", err);
        setStatus("譜面を生成中… (サニタイズ後リトライ)");
        try {
          // OSMD holds internal state from the failed attempt; discard it.
          container.innerHTML = "";
          await tryLoad(sanitizeForOsmd(musicXml));
          if (!cancelled) {
            setStatus(
              "一部の要素を修正して表示しました (詳細はコンソール参照)",
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
      for (let i = 0; i < 2000; i++) {
        const iter = osmd.cursor.iterator;
        if (iter.EndReached) break;
        const idx = iter.CurrentMeasureIndex;
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
