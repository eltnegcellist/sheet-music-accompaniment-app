import { useCallback, useImperativeHandle, useRef, useState, forwardRef } from "react";

import { useLang } from "../i18n";

interface Props {
  disabled?: boolean;
  onSelect: (pdf?: File, musicXml?: File, soloPdf?: File) => void;
  /** When true, render only a hidden input — the parent draws its own UI and
   *  triggers the picker via the imperative ref. */
  hidden?: boolean;
}

export interface PdfUploaderHandle {
  open: () => void;
}

const SOLO_NAME_RE =
  /(solo|独奏|ソロ|violin|vln|vn|cello|vc|flute|fl|ob|oboe|clarinet|cl|sax|trumpet|tp)/i;

// Tauri's WKWebView opens HTML <input type="file"> as a window-attached
// sheet that can render behind the main window on macOS Tahoe. Detect
// the Tauri runtime so we can route through @tauri-apps/api/dialog,
// which always brings the picker to the front.
const isTauri =
  typeof window !== "undefined" &&
  typeof (window as { __TAURI__?: unknown }).__TAURI__ !== "undefined";

async function pickViaTauri(): Promise<File[]> {
  const [{ open }, { convertFileSrc }] = await Promise.all([
    import("@tauri-apps/api/dialog"),
    import("@tauri-apps/api/tauri"),
  ]);
  const selected = await open({
    multiple: true,
    filters: [
      { name: "Score", extensions: ["pdf", "xml", "musicxml", "mxl"] },
    ],
  });
  if (!selected) return [];
  const paths = Array.isArray(selected) ? selected : [selected];
  const files = await Promise.all(
    paths.map(async (path) => {
      const resp = await fetch(convertFileSrc(path));
      const blob = await resp.blob();
      const name = path.split(/[\\/]/).pop() ?? "file";
      return new File([blob], name, {
        type: blob.type || "application/octet-stream",
      });
    }),
  );
  return files;
}

/** Picks accompaniment PDF / MusicXML / solo PDF from a flat FileList using
 *  filename heuristics. Multiple PDFs → the one matching the solo regex (or
 *  the smaller file) is the solo-only score. */
function pickFiles(files: ArrayLike<File> | null | undefined): {
  pdf?: File;
  xml?: File;
  soloPdf?: File;
} {
  if (!files || files.length === 0) return {};
  const pdfs: File[] = [];
  let xml: File | undefined;
  for (const f of Array.from(files)) {
    if (/\.pdf$/i.test(f.name)) pdfs.push(f);
    else if (/\.(xml|musicxml|mxl)$/i.test(f.name)) xml = f;
  }

  let pdf: File | undefined;
  let soloPdf: File | undefined;
  if (pdfs.length === 1) {
    pdf = pdfs[0];
  } else if (pdfs.length >= 2) {
    const soloIdx = pdfs.findIndex((f) => SOLO_NAME_RE.test(f.name));
    if (soloIdx >= 0) {
      soloPdf = pdfs[soloIdx];
      pdf = pdfs.find((_, i) => i !== soloIdx);
    } else {
      const sorted = [...pdfs].sort((a, b) => b.size - a.size);
      pdf = sorted[0];
      soloPdf = sorted[1];
    }
  }
  return { pdf, xml, soloPdf };
}

export const PdfUploader = forwardRef<PdfUploaderHandle, Props>(
  function PdfUploader({ disabled, onSelect, hidden }, ref) {
    const inputRef = useRef<HTMLInputElement>(null);
    const [drag, setDrag] = useState(false);
    const { T } = useLang();

    const handleFiles = useCallback(
      (files: ArrayLike<File> | null | undefined) => {
        const { pdf, xml, soloPdf } = pickFiles(files);
        if (pdf || xml) onSelect(pdf, xml, soloPdf);
      },
      [onSelect],
    );

    const openPicker = useCallback(() => {
      if (disabled) return;
      if (isTauri) {
        pickViaTauri()
          .then((files) => handleFiles(files))
          .catch((err) => {
            console.error("[PdfUploader] tauri dialog failed", err);
          });
      } else {
        inputRef.current?.click();
      }
    }, [disabled, handleFiles]);

    useImperativeHandle(ref, () => ({ open: openPicker }), [openPicker]);

    const input = (
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.xml,.musicxml,.mxl"
        multiple
        hidden
        disabled={disabled}
        onChange={(e) => {
          handleFiles(e.target.files);
          // Allow selecting the same file again later.
          e.target.value = "";
        }}
      />
    );

    if (hidden) return input;

    return (
      <div className="upload">
        <div
          className={`drop-card${drag ? " drop-card--drag" : ""}`}
          onClick={openPicker}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            handleFiles(e.dataTransfer.files);
          }}
        >
          <div className="drop-card__bg">
            {[
              { s: 90, x: "5%", y: "8%", o: 0.07 },
              { s: 70, x: "70%", y: "12%", o: 0.05 },
              { s: 55, x: "80%", y: "55%", o: 0.04 },
              { s: 40, x: "8%", y: "65%", o: 0.04 },
            ].map((c, i) => (
              <span
                key={i}
                className="drop-card__clef"
                style={{ fontSize: c.s, left: c.x, top: c.y, opacity: c.o }}
              >
                𝄞
              </span>
            ))}
            <svg
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                opacity: 0.06,
              }}
              viewBox="0 0 460 200"
              preserveAspectRatio="none"
            >
              {[60, 68, 76, 84, 92, 130, 138, 146, 154, 162].map((y, i) => (
                <line
                  key={i}
                  x1="20"
                  y1={y}
                  x2="440"
                  y2={y}
                  stroke="white"
                  strokeWidth="1.2"
                />
              ))}
            </svg>
          </div>
          <div
            className="drop-card__icon"
            style={{ position: "relative", zIndex: 1 }}
          >
            𝄞
          </div>
          <div className="drop-card__title">{T.dropTitle}</div>
          <div className="drop-card__sub" style={{ marginTop: 8 }}>
            {T.clickToSelect}
            <br />
            <em>.pdf</em> {T.pdfOnly} <em>.pdf + .musicxml</em>{T.skipOmr}
          </div>
        </div>
        <div className="upload__hint">{T.uploaderHint}</div>
        {input}
      </div>
    );
  },
);
