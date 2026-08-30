import { useState } from "react";
import { open } from "@tauri-apps/api/shell";

import { useLang } from "../i18n";

const RELEASE_TAG = "v0.1.1";
const REPOSITORY = "https://github.com/eltnegcellist/sheet-music-accompaniment-app";
const RELEASE_SOURCE = `${REPOSITORY}/tree/${RELEASE_TAG}`;
const RELEASE_ARCHIVE = `${REPOSITORY}/archive/refs/tags/${RELEASE_TAG}.tar.gz`;
const AUDIVERIS_SOURCE = "https://github.com/Audiveris/audiveris/tree/5.10.2";

async function openExternal(url: string) {
  try {
    await open(url);
  } catch {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

export function LegalNotice() {
  const { T } = useLang();
  const [visible, setVisible] = useState(false);

  return (
    <>
      <button className="legal-trigger" type="button" onClick={() => setVisible(true)}>
        {T.legalButton}
      </button>
      {visible && (
        <div className="legal-backdrop" role="presentation" onMouseDown={() => setVisible(false)}>
          <section
            className="legal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="legal-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button className="legal-dialog__close" type="button" aria-label={T.close} onClick={() => setVisible(false)}>×</button>
            <h2 id="legal-title">{T.legalTitle}</h2>
            <p>IMSLP Accompanist 0.1.1</p>
            <p>Copyright © 2026 Hidetaka Ito and contributors.</p>
            <p>{T.legalAgpl}</p>
            <div className="legal-dialog__links">
              <button type="button" onClick={() => void openExternal(`${REPOSITORY}/blob/${RELEASE_TAG}/LICENSE`)}>AGPL-3.0</button>
              <button type="button" onClick={() => void openExternal(RELEASE_SOURCE)}>{T.legalSource}</button>
              <button type="button" onClick={() => void openExternal(RELEASE_ARCHIVE)}>{T.legalDownload}</button>
            </div>
            <p>{T.legalAudiveris}</p>
            <button className="legal-dialog__text-link" type="button" onClick={() => void openExternal(AUDIVERIS_SOURCE)}>Audiveris 5.10.2 source</button>
            <p>{T.legalSamples}</p>
            <p className="legal-dialog__warranty">{T.legalWarranty}</p>
          </section>
        </div>
      )}
    </>
  );
}
