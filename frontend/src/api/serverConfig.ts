export interface OmrServerConfig {
  serverUrl: string;
  apiToken: string;
}

const STORAGE_KEY = "imslp-accompanist.omr-server.v1";

function normalizeServerUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

export function getServerConfig(): OmrServerConfig {
  if (typeof window === "undefined") return { serverUrl: "", apiToken: "" };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { serverUrl: "", apiToken: "" };
    const parsed = JSON.parse(raw) as Partial<OmrServerConfig>;
    return {
      serverUrl: normalizeServerUrl(parsed.serverUrl ?? ""),
      apiToken: parsed.apiToken ?? "",
    };
  } catch {
    return { serverUrl: "", apiToken: "" };
  }
}

export function saveServerConfig(config: OmrServerConfig): void {
  const normalized: OmrServerConfig = {
    serverUrl: normalizeServerUrl(config.serverUrl),
    apiToken: config.apiToken.trim(),
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
}

export function hasConfiguredServer(): boolean {
  return getServerConfig().serverUrl.length > 0;
}

export function configuredServerUrl(): string | null {
  const url = getServerConfig().serverUrl;
  return url || null;
}

export function authHeaders(): Record<string, string> {
  const token = getServerConfig().apiToken.trim();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function isAndroidApp(): boolean {
  if (typeof navigator === "undefined") return false;
  return navigator.userAgent.includes("IMSLPAccompanistAndroid/");
}

export async function testServerConnection(
  config: OmrServerConfig,
): Promise<{ ok: boolean; message: string }> {
  const serverUrl = normalizeServerUrl(config.serverUrl);
  if (!serverUrl) return { ok: false, message: "サーバーURLを入力してください。" };

  const headers: Record<string, string> = {};
  const token = config.apiToken.trim();
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const health = await fetch(`${serverUrl}/health`, { headers });
    if (!health.ok) {
      return { ok: false, message: `/health: HTTP ${health.status}` };
    }

    const auth = await fetch(`${serverUrl}/auth/check`, { headers });
    if (auth.status === 401) {
      return { ok: false, message: "APIトークンが一致しません。" };
    }
    if (!auth.ok) {
      return { ok: false, message: `/auth/check: HTTP ${auth.status}` };
    }
    return { ok: true, message: "接続できました。OMRサーバーを利用できます。" };
  } catch (error) {
    return {
      ok: false,
      message: `接続できません: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}
