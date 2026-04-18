import { useCallback, useRef, useState } from "react";

interface Props {
  disabled?: boolean;
  onSelect: (pdf: File, musicXml?: File) => void;
}

export function PdfUploader({ disabled, onSelect }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const pickFromList = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      let pdf: File | undefined;
      let xml: File | undefined;
      for (const f of Array.from(files)) {
        if (/\.pdf$/i.test(f.name)) pdf = f;
        else if (/\.(xml|musicxml|mxl)$/i.test(f.name)) xml = f;
      }
      if (pdf) onSelect(pdf, xml);
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
        PDFをドロップ、またはクリックして選択
        <br />
        <small>(オプション: 同じ曲の MusicXML も同時に渡せます)</small>
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
