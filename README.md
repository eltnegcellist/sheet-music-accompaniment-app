# IMSLP Accompanist

[English](#english) | [日本語](#日本語)

---

## English

Web application prototype that extracts **accompaniment (piano) parts** from public-domain sheet music PDFs (such as IMSLP) and plays them in the browser.

> Full Japanese document: [README.ja.md](./README.ja.md)

### What this app does

#### 1) Analyze score files
- Upload a PDF, run OMR with **Audiveris**, and extract MusicXML + measure bounding boxes.
- Auto-detect accompaniment parts (mainly two-staff piano parts).
- Auto-select a solo part from non-accompaniment parts using note-density heuristics.
- Detect tempo with multiple fallbacks (`<sound tempo>` -> `<metronome>` -> Italian tempo words -> OCR on the PDF header -> default 120 BPM).
- Detect title from MusicXML metadata, then fallback to OCR.
- Optionally upload your own MusicXML together with PDF to prioritize that data and skip heavy OMR in many cases.
- MusicXML-only upload is also supported (without PDF-linked measure highlight).

#### 2) Playback support
- Play accompaniment with Salamander Grand Piano (Tone.js sampler).
- If a solo part is detected, play it simultaneously using a violin-like synth.
- Solo volume modes: normal / karaoke (lower) / mute.
- Accompaniment volume slider (0-120%) and live tempo slider (30-240 BPM).
- Start/end measure selection, loop playback, count-in (0-4 measures), metronome.
- Fermata-aware handling to extend note duration and suppress metronome clicks during the extension.

#### 3) Visual support
- **PDF view**: shows source PDF and highlights the current measure during playback.
- **Sheet view**: renders MusicXML via OSMD and follows the current measure cursor.
- Built-in MusicXML sanitization for unstable OMR output (`time`, `divisions`, empty/invalid notes, missing measures, key consistency, etc.).
- Download analyzed MusicXML for future fast re-import.

### How to run

#### Option A (recommended): Docker Compose

```bash
docker compose up --build
```

- Frontend: <http://localhost:5173>
- Backend: <http://localhost:8000> (`GET /health`)

> First build may take time because Audiveris image assets are large.

#### Option B: Run frontend/backend separately

##### Backend
```bash
cd backend
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

##### Frontend
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

### Accuracy notes (important)
- OMR quality depends heavily on **Audiveris** and source image quality.
- **Perfect recognition is difficult**, especially for noisy/old scanned sheets.
- If possible, use **clean, digitally engraved sheet music** rather than scanned paper images for better accuracy.

---

## 日本語

IMSLP などのパブリックドメイン楽譜 PDF から**伴奏パート（主にピアノ）**を抽出し、ブラウザで再生できる Web アプリのプロトタイプです。

> 日本語の完全版: [README.ja.md](./README.ja.md)

### 主な機能
- PDF を Audiveris で解析し、MusicXML と小節位置を抽出。
- 伴奏（主に 2 段譜ピアノ）とソロパートを自動判定。
- テンポ・タイトルを MusicXML 優先、必要に応じて OCR で補完。
- 伴奏再生、ソロ同時再生、テンポ/音量/ループ/カウントイン/メトロノーム対応。
- PDF ハイライト表示と譜面ビュー（OSMD）に対応。

### 起動方法

#### 方法 A（推奨）: Docker Compose

```bash
docker compose up --build
```

- フロントエンド: <http://localhost:5173>
- バックエンド: <http://localhost:8000>（`GET /health`）

#### 方法 B: 個別起動

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

### 認識精度に関する重要事項
- 楽譜読み込み精度は **Audiveris（外部ソフトウェア）に強く依存**します。
- OMR の性質上、**常に正確な読み込みを保証することは難しい**です。
- 可能であればスキャン譜よりも**打ち込みの綺麗な楽譜（デジタル浄書譜）**を使うと精度が上がります。
