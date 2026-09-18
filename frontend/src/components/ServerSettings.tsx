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
            ? "Android版ではPDFの楽譜認識だけを、あなた自身が用意したAudiverisサーバーで実行します。解析後はPDFと解析結果を端末に保存するため、過去の曲はサーバーなしでも開けます。"
            : "Android sends only PDF recognition to your own Audiveris server. Completed analyses and PDFs are cached on-device so previously opened scores remain available without the server."}
        </p>

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
