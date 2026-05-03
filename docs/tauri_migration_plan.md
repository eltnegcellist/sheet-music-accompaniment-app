# Tauri + Sidecar 移行 開発プラン

現状の Docker 構成（FastAPI バックエンド + Audiveris/Java + Tesseract + React/Vite フロント）を、Tauri デスクトップアプリ（ローカルサーバー同梱型）へ段階的に移行するための開発プラン。

## 0. 前提と現状確認

| 項目 | 現状 | 移行先 |
| --- | --- | --- |
| バックエンド | FastAPI / uvicorn (`backend/app/main.py:41`)、ポート 8000 | PyInstaller バイナリを Tauri Sidecar で起動 |
| OMR エンジン | Audiveris 5.10.2（Java 17） — `backend/app/omr/audiveris_runner.py:40-66` | Audiveris 同梱 + JRE は同梱 or 前提化 |
| OCR | Tesseract — `backend/app/ocr/tempo_ocr.py` | tessdata 同梱 / `TESSDATA_PREFIX` 解決 |
| 音楽処理 | music21（コーパス参照あり） | corpus を同梱 or 不要部分を除去 |
| フロント | React 18 + Vite + OSMD + pdfjs + Tone.js（5173） | Tauri WebView が静的ビルドを直接ロード |
| API ベース URL | `VITE_BACKEND_URL`（既定 `http://localhost:8000`） — `frontend/src/api/analyze.ts:3-5` | `127.0.0.1:<動的ポート>` を Tauri から injection |
| キャッシュ | `<APP_DATA_DIR>/cache/analyze`（`ANALYZE_CACHE_DIR` で上書き） | OS 標準のユーザーデータ領域へ |
| パラメータ | `backend/params/*.yaml`（`main.py:47` で `parents[1]/"params"`） | 同梱リソース（`sys._MEIPASS`）解決 |

ゴール: ユーザーが `.msi` / `.dmg` を 1 つインストールするだけで、Docker なしに同等のパイプライン（PDF → Audiveris → MusicXML → 伴奏抽出 → 再生）が動くこと。

---

## Step 1: バックエンド（Python）の単一実行ファイル化

ここが最大の山場。Audiveris/JRE/Tesseract の同梱方針を先に確定させる。

### 1-1. PyInstaller 化の準備
- `backend/app/main.py` を直接 ASGI エントリにせず、起動スクリプト `backend/app/server.py` を新設する想定。
  - 引数: `--port`（既定 0＝OS 任せ）、`--host 127.0.0.1`、`--app-data <path>`、`--ready-fd <fd>` など。
  - `uvicorn.run("app.main:app", host=host, port=port, log_config=...)` を呼ぶ。
  - 起動完了後に stdout に `READY {"port": N}` の 1 行を出して Tauri 側に通知する（後述 Step 4）。
- 既存の `backend/app/main.py:46` の `os.environ.get("PIPELINE_PARAM_SET", ...)` のような env 経由設定はそのまま維持。

### 1-2. リソースパスの抽象化
PyInstaller で固めると `__file__` 基準のパス解決が崩れるため、ヘルパを 1 つ追加して全箇所をそれ経由にする。

```python
# backend/app/runtime_paths.py（新規）
import sys, os
from pathlib import Path

def resource_root() -> Path:
    # PyInstaller onefile/onedir では _MEIPASS、それ以外は repo の backend/
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parents[1]

def app_data_root() -> Path:
    # Tauri から渡される --app-data を最優先、無ければ env、無ければ CWD
    if v := os.environ.get("APP_DATA_DIR"):
        return Path(v)
    return Path.cwd()
```

修正対象（最低限）:
- `backend/app/main.py:47` `_PARAMS_DIR = resource_root() / "params"`
- `backend/app/cache/analyze_cache.py:33` 付近のキャッシュルート解決
- `backend/app/pipeline/params_loader.py` の YAML 読み込み（`schema.json` 参照を含む）

### 1-3. PyInstaller spec 作成
`backend/pyinstaller.spec` を用意し、以下を `datas` で同梱する。

| バンドル対象 | ソース | 配置先（_MEIPASS 内） |
| --- | --- | --- |
| YAML パラメータ群 | `backend/params/*.yaml`、`schema.json` | `params/` |
| music21 コーパス（必要分のみ） | site-packages/music21/corpus | `music21/corpus/` |
| Tesseract 言語データ | `tessdata/eng.traineddata` 等 | `tessdata/` |
| 隠れ import | `lxml.etree`、`pkg_resources.py2_warn`、`uvicorn.lifespan.*` | `--hidden-import` |

ビルド: `pyinstaller --clean --noconfirm backend/pyinstaller.spec`

成果物: `dist/accompanist-server`（macOS/Linux）、`accompanist-server.exe`（Windows）。

### 1-4. Audiveris / JRE の同梱方針

**プランB（推奨）** を採る。理由: ユーザーに「Java を入れてください」と言わせると即座に脱落する。

- ディレクトリレイアウト（インストール後）:
  ```
  <Tauri app resources>/
    bin/
      accompanist-server[.exe]        ← PyInstaller 出力（=Sidecar）
    runtime/
      jre/                            ← Eclipse Temurin 17 JRE（OS 別、jlink で最小化）
      audiveris/                      ← Audiveris 5.10.2 配布物（lib/, bin/）
      tessdata/                       ← Tesseract 言語データ
    tesseract/
      tesseract[.exe]                 ← Tesseract バイナリ（OS 別）
  ```
- `backend/app/omr/audiveris_runner.py:40-66` の `_audiveris_command` を改修:
  - `shutil.which("Audiveris")` の前に `AUDIVERIS_LAUNCHER` env / Tauri から渡されたパスを優先。
  - JRE を `JAVA_HOME` として指定し、`audiveris/bin/Audiveris` のシェルラッパを使うか、`java -jar audiveris.jar` を直接組み立てる。
- Tesseract も同様に `pytesseract.pytesseract.tesseract_cmd` を起動時にセット、`TESSDATA_PREFIX` を環境変数で渡す。

注意点:
- macOS は **コード署名 + notarization** が必要。Audiveris/JRE 内の `.dylib` 全部に署名が要る。Tauri の `tauri.conf.json` で `bundle.macOS.signingIdentity` と外部 `entitlements.plist`（JIT 許可）を設定する。
- Windows Defender が PyInstaller バイナリを検疫することがあるので、Authenticode 署名を取得するのが安全。
- Linux は AppImage/deb を `tauri build` で出すが、Audiveris の deb 同梱は再配布ライセンスを確認（Audiveris は AGPL）。AGPL の取り扱いは法務確認が必要。

### 1-5. ヘルスチェック / シャットダウン
- 既存の `/health` エンドポイント（`backend/app/main.py` 内）を活用。
- `/shutdown`（POST、ローカル限定）を追加して Tauri 終了時の graceful stop に使う。受信時 `os.kill(os.getpid(), SIGTERM)` 相当。

**Step 1 完了条件**: `./dist/accompanist-server --port 18080 --app-data /tmp/x` を直叩きで起動し、別プロセスから `curl http://127.0.0.1:18080/health` が 200 を返し、PDF アップロードからの解析が完走すること。

---

## Step 2: フロントエンドのバックエンド接続改修

### 2-1. ベース URL 注入の経路を増やす
`frontend/src/api/analyze.ts:3-5` を修正:

```ts
function resolveBackendUrl(): string {
  // 1) Tauri からの注入（後述）
  const fromTauri = (window as any).__BACKEND_URL__;
  if (fromTauri) return fromTauri;
  // 2) Vite の env（dev サーバ用）
  const fromEnv = import.meta.env.VITE_BACKEND_URL as string | undefined;
  if (fromEnv) return fromEnv;
  // 3) フォールバック
  return "http://127.0.0.1:8000";
}
const BACKEND_URL = resolveBackendUrl();
```

API クライアントの一元化: `frontend/src/api/analyze.ts` 以外でも `fetch` 直書きがあれば、`apiUrl(path)` ヘルパに集約する。

### 2-2. 動的ポート受け渡し
- Sidecar が `0.0.0.0` ではなく `127.0.0.1` で **ポート 0** を listen → 実ポートを stdout に `READY {"port": N}` で出力。
- Tauri（Rust 側）が stdout を読み取り、`__BACKEND_URL__` を Tauri の `setup()` 内で `WindowBuilder` の `initialization_script` で WebView に注入する。
- フォールバックとして固定ポート（例: 39871）を Sidecar に渡せるようにしておく（CI / 開発時の安定化）。

### 2-3. CORS / origin
Tauri の WebView origin は `tauri://localhost`（macOS は `https://tauri.localhost`）。`backend/app/main.py:74-79` の `allow_origins=["*"]` のままでも動くが、リリース時は `["tauri://localhost", "https://tauri.localhost", "http://localhost:5173"]` に絞る。

### 2-4. ファイル選択の Tauri 化（オプション）
将来的には `<input type="file">` を `@tauri-apps/api/dialog` の `open()` に置き換え、選択した `path` を multipart ではなく JSON でバックに渡す改修も可能。Step 1 段階では既存の multipart/form-data のままで良い。

**Step 2 完了条件**: `npm run dev` 状態で `VITE_BACKEND_URL` を変えると接続先が切り替わる。`window.__BACKEND_URL__` をコンソールで手動セットしても動く。

---

## Step 3: Tauri プロジェクトの初期化とフロント統合

### 3-1. Rust ツールチェーン
- 各 OS に `rustup` で stable を入れる。CI（GitHub Actions）も `dtolnay/rust-toolchain@stable` を使う。
- macOS: Xcode CLT / Windows: Visual Studio Build Tools / Linux: `webkit2gtk` 系の dev パッケージ。

### 3-2. 既存 frontend に Tauri を追加
ルートではなく `frontend/` を Tauri の base にする（Vite 設定とビルド出力をそのまま活かす）。

```bash
cd frontend
npm install --save-dev @tauri-apps/cli
npx tauri init
# - app name: imslp-accompanist
# - window title: IMSLP Accompanist
# - dev path: http://localhost:5173
# - dist dir: ../frontend/dist  （= Vite の build 出力）
# - dev command: npm run dev
# - build command: npm run build
```

`frontend/src-tauri/tauri.conf.json` のキー設定:

```jsonc
{
  "build": {
    "beforeDevCommand": "npm run dev",
    "beforeBuildCommand": "npm run build",
    "devPath": "http://localhost:5173",
    "distDir": "../dist"
  },
  "tauri": {
    "bundle": {
      "identifier": "app.imslp.accompanist",
      "resources": ["resources/**/*"],
      "externalBin": ["bin/accompanist-server"]
    },
    "allowlist": {
      "shell": { "sidecar": true, "scope": [{ "name": "bin/accompanist-server", "sidecar": true }] },
      "fs": { "all": false, "scope": ["$APPDATA/**", "$APPLOCALDATA/**"] },
      "dialog": { "open": true, "save": true }
    }
  }
}
```

### 3-3. リソース配置規約
- Sidecar 実行ファイル: `frontend/src-tauri/bin/accompanist-server-<target-triple>[.exe]`
  - 例: `accompanist-server-x86_64-apple-darwin`、`accompanist-server-aarch64-apple-darwin`、`accompanist-server-x86_64-pc-windows-msvc.exe`、`accompanist-server-x86_64-unknown-linux-gnu`
- 付随リソース: `frontend/src-tauri/resources/runtime/{jre,audiveris,tessdata}/...`
- Tauri は `resources` で指定したものをアプリバンドル内に展開する。実行時の絶対パスは `tauri::api::path::resource_dir()` で解決。

**Step 3 完了条件**: `npm run tauri dev` で空っぽの Tauri ウィンドウ内に既存の React UI が描画される（API は動かなくて OK）。

---

## Step 4: Sidecar 連携（プロセスライフサイクル）

### 4-1. Rust 側の起動・停止コード
`frontend/src-tauri/src/main.rs` に以下を追加（要点のみ）:

```rust
use tauri::api::process::{Command, CommandEvent};
use tauri::Manager;
use std::sync::Mutex;

struct SidecarState {
    child: Mutex<Option<tauri::api::process::CommandChild>>,
    backend_url: Mutex<Option<String>>,
}

fn main() {
    tauri::Builder::default()
        .manage(SidecarState { child: Mutex::new(None), backend_url: Mutex::new(None) })
        .setup(|app| {
            let resource_dir = app.path_resolver().resource_dir().unwrap();
            let app_data = app.path_resolver().app_data_dir().unwrap();
            std::fs::create_dir_all(&app_data).ok();

            let (mut rx, child) = Command::new_sidecar("accompanist-server")?
                .args([
                    "--host", "127.0.0.1",
                    "--port", "0",
                    "--app-data", app_data.to_string_lossy().as_ref(),
                ])
                .envs([
                    ("AUDIVERIS_LAUNCHER", resource_dir.join("runtime/audiveris/bin/Audiveris").to_string_lossy().to_string()),
                    ("JAVA_HOME",         resource_dir.join("runtime/jre").to_string_lossy().to_string()),
                    ("TESSDATA_PREFIX",   resource_dir.join("runtime/tessdata").to_string_lossy().to_string()),
                    ("PIPELINE_PARAM_SET", "v5_real_pdf".into()),
                ])
                .spawn()?;

            let state = app.state::<SidecarState>();
            *state.child.lock().unwrap() = Some(child);

            let app_handle = app.handle();
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    if let CommandEvent::Stdout(line) = event {
                        // READY {"port": 39871}
                        if let Some(rest) = line.strip_prefix("READY ") {
                            if let Ok(json) = serde_json::from_str::<serde_json::Value>(rest) {
                                if let Some(port) = json["port"].as_u64() {
                                    let url = format!("http://127.0.0.1:{}", port);
                                    let st = app_handle.state::<SidecarState>();
                                    *st.backend_url.lock().unwrap() = Some(url.clone());
                                    if let Some(w) = app_handle.get_window("main") {
                                        let _ = w.eval(&format!("window.__BACKEND_URL__ = {:?};", url));
                                    }
                                }
                            }
                        } else {
                            eprintln!("[sidecar] {line}");
                        }
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|event| {
            if let tauri::WindowEvent::Destroyed = event.event() {
                let state = event.window().state::<SidecarState>();
                if let Some(child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### 4-2. WebView 側の同期
- 起動直後はまだ `__BACKEND_URL__` が未注入の可能性がある。`frontend/src/api/analyze.ts` の `resolveBackendUrl()` をコール時遅延評価にする、またはアプリ起動シーケンスに「バックエンド READY 待ち」スプラッシュを 1 枚挟む。
- Tauri の `event.emit("backend-ready", url)` を使い、フロントは `listen("backend-ready", ...)` で受け取る方式の方が堅牢。

### 4-3. 強制終了対策
- ユーザーが Tauri アプリを強制終了したとき、PyInstaller バイナリと Audiveris の Java 子プロセスが残ると次回起動でポート競合する。
- 対策:
  - 起動時に `pidfile`（`<app-data>/server.pid`）を書き、既存 PID が生きていれば kill してから起動。
  - Audiveris の長時間実行中（最大 1800 秒、`audiveris_runner.py:101`）に親が死んだ場合の Java プロセス処理は OS ごとに対応（Windows は Job Object、Linux は `prctl(PR_SET_PDEATHSIG)`、macOS は親プロセス監視スレッド）。

### 4-4. 大きな PDF の解析中 UX
現状 30 分タイムアウト。Tauri ウィンドウを閉じる動作は「最小化」相当に変えるか、解析中はウィンドウクローズに確認ダイアログを出す（`@tauri-apps/api/event` の `tauri://close-requested`）。

**Step 4 完了条件**: `tauri dev` で起動 → 自動でバックが立ち上がり、PDF 解析の往復が完走 → アプリを閉じると Python/Java プロセスが OS から消えている。

---

## Step 5: テストとインストーラビルド

### 5-1. 段階的テストマトリクス

| レイヤ | テスト | 手段 |
| --- | --- | --- |
| Python 単体 | 既存 `backend/tests/` | `pytest`（PyInstaller 化前後の両方） |
| バイナリ単体 | `accompanist-server --help` / `/health` / `/analyze` | curl + 既存サンプル PDF |
| Audiveris 連携 | `backend/tests/` 内 OMR 系 + フィクスチャ PDF | 同梱 JRE+Audiveris 経由 |
| Tauri dev | `npm run tauri dev` で UI→解析→再生 | 手動 E2E |
| Tauri build | `npm run tauri build` 成果物起動 | 各 OS 実機 |
| 後方互換 | キャッシュ互換 (`backend/app/cache/analyze_cache.py`) が Docker 版生成データを読めるか | キャッシュコピーで検証 |

### 5-2. ビルド対象とアーティファクト
- macOS: `.app` / `.dmg`（Apple Silicon と Intel の universal、または別々）
- Windows: `.msi`（WiX）+ `.exe`（NSIS）
- Linux: `.AppImage` / `.deb`（Audiveris 同梱の AGPL 影響に注意）

### 5-3. CI（GitHub Actions）
- マトリクス: `macos-14`, `windows-latest`, `ubuntu-22.04`
- ステップ: Python セットアップ → `pyinstaller` → `tauri build` → 署名 → `actions/upload-artifact`
- 実行ファイル名は **必ず target triple 付き**（Tauri の sidecar 規約）。

### 5-4. リリース時のチェックリスト
- [ ] PyInstaller の `--onedir` で起動秒数 < 5 秒（onefile は遅いので避ける）
- [ ] 同梱 JRE が jlink 最小化されている（`java.base,java.desktop,java.logging,java.sql,jdk.unsupported` 等）
- [ ] Tesseract `eng.traineddata` 同梱、`TESSDATA_PREFIX` がアプリ内を指している
- [ ] `params/v5_real_pdf.yaml` および `schema.json` が `_MEIPASS` 経由で読める
- [ ] キャッシュ書き込み先が OS 標準の app data（`%APPDATA%`、`~/Library/Application Support/`、`~/.local/share/`）
- [ ] アプリ強制終了後に Java/Python プロセスが残らない
- [ ] macOS: Hardened Runtime + JIT 許容 entitlements、notarization 通過
- [ ] Windows: SmartScreen を回避するための Authenticode 署名
- [ ] AGPL（Audiveris）/その他 OSS ライセンスの NOTICE をアプリに同梱

---

## 付録 A: ファイル別の改修サマリ

| ファイル | 主な変更 |
| --- | --- |
| `backend/app/server.py`（新規） | uvicorn 起動エントリ。`--port`/`--app-data`/`READY` 出力 |
| `backend/app/runtime_paths.py`（新規） | `_MEIPASS` 対応のパス解決ヘルパ |
| `backend/app/main.py:46-47` | `_PARAMS_DIR` を `runtime_paths.resource_root()` 経由に |
| `backend/app/main.py:74-79` | CORS を Tauri origin に絞る |
| `backend/app/cache/analyze_cache.py:33` 付近 | `app_data_root()` 経由に |
| `backend/app/omr/audiveris_runner.py:40-66` | `AUDIVERIS_LAUNCHER` env を最優先、JRE/JAVA_HOME を考慮 |
| `backend/app/ocr/tempo_ocr.py` | `pytesseract.tesseract_cmd` をランタイム同梱バイナリに固定 |
| `backend/pyinstaller.spec`（新規） | datas / hiddenimports / binaries 定義 |
| `frontend/src/api/analyze.ts:3-5` | `__BACKEND_URL__` 注入を最優先 |
| `frontend/src-tauri/`（新規） | Tauri プロジェクト一式、Sidecar spawn コード |
| `docker-compose.yml` | 開発用に残置（CI と既存ユーザー向けの当面の互換） |

## 付録 B: マイルストーンと粗い見積もり

| Step | 想定工数 | リスク |
| --- | --- | --- |
| 1. PyInstaller + Audiveris 同梱 | 5–8 日 | Audiveris の Java 依存解決、ライセンス確認 |
| 2. フロント API 改修 | 0.5–1 日 | 低 |
| 3. Tauri 初期化 | 1–2 日 | webkit2gtk 周りの環境構築 |
| 4. Sidecar 連携 | 2–3 日 | プロセス孤児化、ポート同期 |
| 5. CI / 署名 / インストーラ | 5–10 日 | macOS notarization、Windows コード署名証明書取得 |

合計: 順調なら 2〜3 週間、署名証明書の手配がボトルネック。
