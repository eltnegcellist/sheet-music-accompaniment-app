import { useEffect, useState } from "react";
import { desktopOmrEngine, saveDesktopOmrEngine } from "../api/desktopConfig";
import type { OmrEngine } from "../api/serverConfig";
import { useLang } from "../i18n";

export function DesktopOmrSettings({ open, onClose }: {
  open: boolean;
  onClose: () => void;
}) {
  const { lang } = useLang();
  const ja = lang === "ja";
  const [engine, setEngine] = useState<OmrEngine>("audiveris");
  useEffect(() => { if (open) setEngine(desktopOmrEngine()); }, [open]);
  if (!open) return null;
  return (
    <div className="server-settings-backdrop" role="presentation">
      <section className="server-settings" role="dialog" aria-modal="true"
        aria-labelledby="desktop-omr-title">
        <div className="server-settings__head">
          <div>
            <div className="server-settings__eyebrow">LOCAL OMR</div>
            <h2 id="desktop-omr-title">{ja ? "楽譜認識の設定" : "Recognition settings"}</h2>
          </div>
          <button type="button" className="server-settings__close" onClick={onClose}
            aria-label={ja ? "閉じる" : "Close"}>×</button>
        </div>
        <p className="server-settings__lead">
          {ja ? "PDFの楽譜認識をこのコンピューター内で実行します。OMRサーバーの設定は不要です。"
            : "PDF recognition runs on this computer. No OMR server setup is needed."}
        </p>
        <label className="server-settings__field">
          <span>{ja ? "楽譜認識エンジン" : "Recognition engine"}</span>
          <select value={engine} onChange={(e) => setEngine(e.target.value as OmrEngine)}>
            <option value="audiveris">Audiveris</option>
            <option value="homr">homr</option>
            <option value="hybrid">{ja ? "ハイブリッド" : "Hybrid"}</option>
          </select>
          <small className="server-settings__hint">
            {engine === "hybrid"
              ? ja ? "両方式を比較し、安全に対応する音高を融合します。処理時間は長くなります。"
                : "Compares both engines and safely fuses corresponding pitches. Takes longer to process."
              : engine === "homr"
                ? ja ? "ニューラルOMRです。Apple SiliconではCoreMLを利用します。初回はモデルの準備に時間がかかります。PDF上の小節ハイライトは利用できません。"
                  : "Neural OMR uses CoreML on Apple Silicon. First use takes extra time to prepare models. PDF measure highlighting is unavailable."
                : ja ? "既定の方式です。PDF上の小節位置も取得します。"
                  : "Default engine. Also detects PDF measure positions."}
          </small>
        </label>
        <div className="server-settings__actions">
          <button type="button" className="server-settings__save" onClick={() => {
            saveDesktopOmrEngine(engine); onClose();
          }}>{ja ? "保存" : "Save"}</button>
        </div>
      </section>
    </div>
  );
}
