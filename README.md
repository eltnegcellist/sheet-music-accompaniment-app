# IMSLP Accompanist

[English](#english) | [日本語](#日本語)

---

## English

macOS desktop app that extracts **accompaniment (piano) parts** from
public-domain sheet music PDFs (such as IMSLP) and plays them back
with score-following highlights, live tempo, looping, count-in, and a
karaoke-style solo mix.

### Download (macOS)

Grab the latest **`IMSLP-Accompanist-<version>.dmg`** from the
[Releases page](https://github.com/eltnegcellist/sheet-music-accompaniment-app/releases/latest).

#### System requirements
- macOS 13 (Ventura) or newer.
- Apple Silicon (M1 / M2 / M3 / M4). Intel Macs are not currently tested
  — see _Platform status_ below.
- Roughly 500 MB free disk space. The bundled JRE, Audiveris, Tesseract,
  and Poppler are fully self-contained, so you do **not** need Homebrew,
  a system Java, or any other external tools installed.

#### Install

1. Download the `.dmg` from Releases.
2. Open it and drag **IMSLP Accompanist.app** to **Applications**.
3. The app is unsigned (no Apple Developer ID). On first launch, macOS
   will refuse to open it ("Apple could not verify… is free of malware").
   Bypass Gatekeeper one of these ways:
   - **macOS Ventura / Sonoma**: right-click the app → **Open** →
     **Open** in the warning dialog.
   - **macOS Sequoia / Tahoe**: try to open it once (it gets blocked),
     then go to **System Settings → Privacy & Security**, scroll to the
     bottom and click **Open Anyway**.
   - If both fail, run this once in Terminal:
     ```sh
     xattr -dr com.apple.quarantine "/Applications/IMSLP Accompanist.app"
     ```

   See [docs/macos_unsigned_distribution.md](docs/macos_unsigned_distribution.md)
   for the full troubleshooting guide.

### What this app does

#### 1) Analyze score files
- Upload a PDF, run OMR with **Audiveris**, and extract MusicXML +
  measure bounding boxes.
- Auto-detect accompaniment parts (mainly two-staff piano parts).
- Auto-select a solo part from non-accompaniment parts using note-density
  heuristics.
- Detect tempo with multiple fallbacks (`<sound tempo>` → `<metronome>` →
  Italian tempo words → OCR on the PDF header → default 120 BPM).
- Detect title from MusicXML metadata, then fall back to OCR.
- Optionally upload your own MusicXML together with the PDF to prioritize
  that data and skip heavy OMR in many cases.
- MusicXML-only upload is also supported (without PDF-linked measure
  highlight).

#### 2) Playback support
- Play accompaniment with Salamander Grand Piano (Tone.js sampler).
- If a solo part is detected, play it simultaneously using a violin-like
  synth.
- Solo volume modes: normal / karaoke (lower) / mute.
- Accompaniment volume slider (0–120%) and live tempo slider (30–240 BPM).
- Start/end measure selection, loop playback, count-in (0–4 measures),
  metronome.
- Fermata-aware handling extends note duration and suppresses metronome
  clicks during the extension.

#### 3) Visual support
- **PDF view**: shows the source PDF and highlights the current measure
  during playback.
- **Sheet view**: renders MusicXML via OSMD and follows the current
  measure cursor.
- Built-in MusicXML sanitization for unstable OMR output (`time`,
  `divisions`, empty/invalid notes, missing measures, key consistency,
  etc.).
- Download the analyzed MusicXML for fast re-import next time.

### Accuracy notes (important)
- OMR quality depends heavily on **Audiveris** and source image quality.
- **Perfect recognition is difficult**, especially for noisy or old
  scanned sheets.
- For best results, prefer **clean, digitally engraved sheet music**
  over scanned paper images.

### Platform status
- **macOS (Apple Silicon)** — ✅ supported. DMG distributed via
  [Releases](https://github.com/eltnegcellist/sheet-music-accompaniment-app/releases/latest).
- **macOS (Intel)** — ⚠️ untested. The current build pipeline produces
  an aarch64-only DMG; an x86_64 build hasn't been wired up.
- **Windows** — ⏳ not yet officially supported / under verification.
  The runtime self-containment script (`scripts/fetch_runtime_windows.ps1`)
  exists but the end-to-end build, sign, and distribution flow is
  unverified.
- **Linux** — desktop app not packaged. Use the self-hosting options
  below if you want to run it on Linux.

---

## For developers / self-hosting

If you would rather run the FastAPI backend + Vite frontend yourself
instead of using the desktop app — for development, on Linux, or on a
shared server — three options:

### Option A: Docker Compose

```bash
docker compose up --build
```

- Frontend: <http://localhost:5173>
- Backend: <http://localhost:8000> (`GET /health`)

> First build may take time because Audiveris image assets are large.

### Option B: Run frontend / backend separately

```bash
# backend
cd backend
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# frontend
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

### Option C: Build the macOS desktop app from source

This is the same pipeline that produces the DMG attached to Releases.
See [docs/tauri_migration_plan.md](docs/tauri_migration_plan.md) for
design background and [docs/macos_unsigned_distribution.md](docs/macos_unsigned_distribution.md)
for the unsigned-distribution workflow.

Prerequisites: Rust toolchain (`rustup`), Python 3.11+, Node.js 20+,
Xcode Command Line Tools, and Homebrew with `tesseract` + `poppler`
installed (used as the source for the bundled, self-contained copies —
the produced `.app` no longer needs Homebrew on the end user's machine).

```bash
# 1. Stage the bundled JRE + Audiveris + Tesseract + Poppler under
#    frontend/src-tauri/resources/runtime/ (downloads / builds ~200 MB
#    the first time)
scripts/fetch_runtime_macos.sh

# 2. Build the Python sidecar binary into frontend/src-tauri/bin/
pip install pyinstaller
pip install -e backend
scripts/build_sidecar.sh

# 3. (one-time) Generate bundle icons from a 1024x1024 PNG source
cd frontend
npx @tauri-apps/cli icon path/to/source.png -o src-tauri/icons
cd ..

# 4. Run the desktop app in dev mode
npm install --prefix frontend
npm run tauri:dev --prefix frontend

# 5. Or build the .app + DMG for distribution
npm run tauri:build --prefix frontend
scripts/post_bundle_macos.sh    # restore JRE legal/ stripped by Tauri
scripts/sign_adhoc_macos.sh     # ad-hoc resign every embedded Mach-O
scripts/build_dmg_macos.sh      # → dist/IMSLP-Accompanist-<version>.dmg
```

### Tests

```bash
# backend
cd backend && pip install -e ".[dev]" && pytest

# frontend
cd frontend && npm install && npm test
```

---

## 日本語

macOS デスクトップアプリです。IMSLP などのパブリックドメイン楽譜 PDF
から**伴奏パート（主にピアノ）**を抽出し、譜面ハイライト・テンポ
スライダ・ループ・カウントイン・カラオケ風ソロミックス付きで再生
します。

### ダウンロード（macOS）

[Releases ページ](https://github.com/eltnegcellist/sheet-music-accompaniment-app/releases/latest)
から最新の `IMSLP-Accompanist-<version>.dmg` を取得してください。

#### 動作環境
- macOS 13 (Ventura) 以降
- Apple Silicon（M1 / M2 / M3 / M4）。Intel Mac は未検証。
- 空き容量 500 MB 程度。JRE / Audiveris / Tesseract / Poppler をすべて
  同梱しているため、Homebrew や Java の追加インストールは不要です。

#### インストール
1. Releases から `.dmg` をダウンロード。
2. 開いて **IMSLP Accompanist.app** を **Applications** にドラッグ。
3. 未署名アプリ（野良配布）のため、初回起動は Gatekeeper にブロック
   されます。下記いずれかで回避してください:
   - **Ventura / Sonoma**: アプリを右クリック → **開く** → 警告
     ダイアログの **開く** を押す。
   - **Sequoia / Tahoe**: 一度起動を試してブロックされたあと、
     **システム設定 → プライバシーとセキュリティ** の最下部にある
     **このまま開く** を押す。
   - どちらも通らない場合、ターミナルで:
     ```sh
     xattr -dr com.apple.quarantine "/Applications/IMSLP Accompanist.app"
     ```

   詳細なトラブルシューティングは
   [docs/macos_unsigned_distribution.md](docs/macos_unsigned_distribution.md)。

### 機能概要
- PDF を Audiveris で OMR し、MusicXML と小節バウンディングボックスを抽出。
- 伴奏（主に 2 段譜ピアノ）とソロパートを自動判定。
- テンポは MusicXML 優先、必要に応じて OCR で補完。
- 伴奏 + ソロ同時再生、テンポ / 音量 / ループ / カウントイン /
  メトロノーム対応。
- PDF ハイライト表示と OSMD 譜面ビューに対応。
- 解析済み MusicXML をダウンロードして次回高速再利用。

### 認識精度に関する重要事項
- 楽譜読み込み精度は **Audiveris（外部 OMR ソフトウェア）に強く依存**します。
- OMR の性質上、**常に正確な読み込みを保証することは難しい**です。
- 可能であれば、スキャン譜よりも**打ち込みの綺麗な楽譜（デジタル浄書譜）**
  を使うと精度が上がります。

### プラットフォーム状況
- **macOS (Apple Silicon)**: ✅ サポート対象。
- **macOS (Intel)**: ⚠️ 未検証。
- **Windows**: ⏳ 未対応 / 検証中。
- **Linux**: デスクトップアプリ未提供。Web 版（Docker / セルフ
  ホスト）で利用できます。
