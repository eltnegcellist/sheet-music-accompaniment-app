import { useCallback, useRef, useState } from "react";

interface Props {
  disabled?: boolean;
  onSelect: (pdf?: File, musicXml?: File, soloPdf?: File) => void;
}

const SOLO_NAME_RE = /(solo|独奏|ソロ|violin|vln|vn|cello|vc|flute|fl|ob|oboe|clarinet|cl|sax|trumpet|tp)/i;

export function PdfUploader({ disabled, onSelect }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const pickFromList = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
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
        // Heuristic: a file whose name contains "solo" / instrument name is the
        // solo-only score; the other is the full score with accompaniment.
        const soloIdx = pdfs.findIndex((f) => SOLO_NAME_RE.test(f.name));
        if (soloIdx >= 0) {
          soloPdf = pdfs[soloIdx];
          pdf = pdfs.find((_, i) => i !== soloIdx);
        } else {
          // Fall back to "smaller file is the solo" — solo-only PDFs are
          // almost always thinner than the full accompaniment score.
          const sorted = [...pdfs].sort((a, b) => b.size - a.size);
          pdf = sorted[0];
          soloPdf = sorted[1];
        }
      }
      if (pdf || xml) onSelect(pdf, xml, soloPdf);
    },
    [onSelect],
  );

  return (
    <div className="uploader">
      <div
        className={`uploader__drop${dragActive ? " uploader__drop--active" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          pickFromList(e.dataTransfer.files);
        }}
      >
        PDF / MusicXML をドロップ、またはクリックして選択
        <br />
        <small>
          (MusicXMLのみでも再生できます。PDF同時指定でハイライト対応 /
          ソロ専用PDFを同時に投入するとソロ認識が向上します)
        </small>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.xml,.musicxml,.mxl"
        multiple
        hidden
        disabled={disabled}
        onChange={(e) => pickFromList(e.target.files)}
      />
    </div>
  );
}
