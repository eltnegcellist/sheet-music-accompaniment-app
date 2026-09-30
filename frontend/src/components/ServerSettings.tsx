import { useEffect, useState } from "react";

import {
  getServerConfig,
  saveServerConfig,
  testServerConnection,
  type OmrServerConfig,
} from "../api/serverConfig";
import { useLang } from "../i18n";

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export function ServerSettings({ open, onClose, onSaved }: Props) {
  const { lang } = useLang();
  const [draft, setDraft] = useState<OmrServerConfig>({
    serverUrl: "",
    apiToken: "",
    omrEngine: "audiveris",
  });
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(
    null,
  );

  useEffect(() => {
    if (open) {
      setDraft(getServerConfig());
      setResult(null);
    }
  }, [open]);

  if (!open) return null;

  const ja = lang === "ja";

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      setResult(await testServerConnection(draft));
    } finally {
      setTesting(false);
    }
  };

  const save = () => {
    saveServerConfig(draft);
    window.AndroidBridge?.setAllowHttpOmr(
      draft.serverUrl.trim().toLowerCase().startsWith("http://"),
    );
    onSaved?.();
    onClose();
  };

  return (
    <div className="server-settings-backdrop" role="presentation">
      <section
        className="server-settings"
        role="dialog"
        aria-modal="true"
        aria-labelledby="server-settings-title"
      >
        <div className="server-settings__head">
          <div>
            <div className="server-settings__eyebrow">SELF-HOSTED OMR</div>
            <h2 id="server-settings-title">
              {ja ? "OMRサーバー設定" : "OMR server settings"}
            </h2>
          </div>
          <button
            type="button"
            className="server-settings__close"
            onClick={onClose}
            aria-label={ja ? "閉じる" : "Close"}
          >
            ×
          </button>
        </div>

        <p className="server-settings__lead">
          {ja
            ? "Android版ではPDFの楽譜認識だけを、あなた自身が用意したOMRサーバーで実行します。Audiveris、homr、両者を自動で使い分けるハイブリッドを選択できます。解析後はPDFと解析結果を端末に保存します。"
            : "Android sends PDF recognition to your own OMR server. Choose Audiveris, neural homr, or the confidence-gated hybrid that automatically combines both."}
        </p>

        <label className="server-settings__field">
          <span>{ja ? "楽譜認識エンジン" : "Recognition engine"}</span>
          <select
            value={draft.omrEngine}
            onChange={(e) =>
              setDraft((d) => ({
                ...d,
                omrEngine:
                  e.target.value === "homr" || e.target.value === "hybrid"
                    ? e.target.value
                    : "audiveris",
              }))
            }
          >
            <option value="hybrid">
              {ja
                ? "ハイブリッド（推奨・試験運用）"
                : "Hybrid (recommended, experimental)"}
            </option>
            <option value="audiveris">
              {ja ? "Audiveris（従来方式）" : "Audiveris (classic)"}
            </option>
            <option value="homr">
              {ja ? "homr（ニューラルOMR・試験運用）" : "homr (neural OMR, experimental)"}
            </option>
          </select>
          <small className="server-settings__hint">
            {draft.omrEngine === "hybrid"
              ? ja
                ? "Audiverisの構造認識とhomrのニューラル認識を自動で比較し、崩れた場合はフォールバック、安全に対応できる音高だけ融合します。"
                : "Compares Audiveris structure with neural homr, falls back when one collapses, and fuses pitch only when correspondence is safe."
              : draft.omrEngine === "homr"
                ? ja
                  ? "深層学習で音高・リズム・大譜表を認識します。PDF上の小節ハイライトは利用できません。"
                  : "Uses deep learning for pitch, rhythm and grand-staff recognition. PDF measure highlighting is unavailable."
                : ja
                  ? "従来方式です。PDF上の小節位置も取得できます。"
                  : "Classic engine. It also provides PDF measure positions."}
          </small>
        </label>

        <label className="server-settings__field">
          <span>{ja ? "サーバーURL" : "Server URL"}</span>
          <input
            value={draft.serverUrl}
            onChange={(e) =>
              setDraft((d) => ({ ...d, serverUrl: e.target.value }))
            }
            placeholder="https://omr.example.com"
            inputMode="url"
            autoCapitalize="none"
            autoCorrect="off"
          />
        </label>

        {draft.serverUrl.trim().toLowerCase().startsWith("http://") && (
          <div className="server-settings__http-warning">
            {ja
              ? "HTTPではURLとAPIトークンが暗号化されません。自宅LAN内だけで使用し、インターネットには公開しないでください。"
              : "HTTP does not encrypt the URL or API token. Use it only on a trusted private LAN and never expose it directly to the Internet."}
          </div>
        )}

        <label className="server-settings__field">
          <span>{ja ? "APIトークン（推奨）" : "API token (recommended)"}</span>
          <input
            value={draft.apiToken}
            onChange={(e) =>
              setDraft((d) => ({ ...d, apiToken: e.target.value }))
            }
            placeholder={ja ? "サーバー側の API_TOKEN と同じ値" : "Same value as server API_TOKEN"}
            type="password"
            autoCapitalize="none"
            autoCorrect="off"
          />
        </label>

        <div className="server-settings__actions">
          <button
            type="button"
            className="server-settings__test"
            onClick={test}
            disabled={testing || !draft.serverUrl.trim()}
          >
            {testing
              ? ja
                ? "確認中…"
                : "Testing…"
              : ja
                ? "接続テスト"
                : "Test connection"}
          </button>
          <button
            type="button"
            className="server-settings__save"
            onClick={save}
            disabled={!draft.serverUrl.trim()}
          >
            {ja ? "保存" : "Save"}
          </button>
        </div>

        {result && (
          <div
            className={
              "server-settings__result " +
              (result.ok
                ? "server-settings__result--ok"
                : "server-settings__result--error")
            }
          >
            {result.ok ? "✓ " : "⚠ "}
            {result.message}
          </div>
        )}

        <details className="server-settings__guide">
          <summary>{ja ? "サーバーの用意方法" : "How to set up the server"}</summary>
          <div>
            <p>
              {ja
                ? "このGitHubリポジトリをサーバーへ置き、付属のセットアップスクリプトを実行すると、APIトークン生成とDocker起動まで自動で行います。"
                : "Clone this repository on your server and run the included setup script to generate an API token and start Docker automatically."}
            </p>
            <code>sh scripts/setup_omr_server.sh</code>
            <p>
              {ja
                ? "インターネット越しに使う場合はHTTPSを推奨します。自宅LAN内のHTTPサーバーもAndroid版では利用できます。"
                : "HTTPS is recommended over the internet. HTTP servers on your home LAN are also supported by the Android build."}
            </p>
          </div>
        </details>
      </section>
    </div>
  );
}
