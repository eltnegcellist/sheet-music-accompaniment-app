# IMSLP Accompanist

IMSLP などのパブリックドメイン PDF 楽譜から **伴奏パート（ピアノ）** を抽出し、ブラウザで演奏する Web アプリのプロトタイプ。
器楽ソロ奏者がリハーサル・本番補助で「伴奏者代わり」に使うことを想定。

## 構成

| 層 | 技術 |
|---|---|
| フロントエンド | React + TypeScript + Vite |
| PDF 表示 | PDF.js（オーバーレイ Canvas で現在小節をハイライト） |
| 譜面表示 | OpenSheetMusicDisplay (OSMD)（SVG レンダリング + カーソル追従） |
| 音声再生 | Tone.js + Salamander Grand Piano (SoundFont) + バイオリン風 PolySynth |
| バックエンド | Python + FastAPI |
| OMR | Audiveris (CLI, Docker 同梱) |
| テンポ／タイトル OCR | pdf2image + Tesseract (ita+eng) |

## 主な機能

### 解析
- PDF アップロード → Audiveris で MusicXML + 小節バウンディングボックスを抽出
- 「2段譜のパート」を伴奏（ピアノ）と自動判定。Klavier / Pianoforte / ピアノ などの名称マッチもフォールバック
- ソロパートは非伴奏パートの中から音符密度で自動選定（OMR の余剰パート対策）
- テンポ検出は `<sound tempo>` → `<metronome>` → イタリア語テンポ語（Allegro, Andante…）→ PDF 上部の OCR フォールバック → 120 BPM デフォルト の 5 段階
- タイトルは MusicXML メタデータ → PDF 上部の OCR（中央配置スコアで最も「見出しらしい」行）にフォールバック
- 任意で同じ曲の MusicXML を一緒にアップロードすると、音符データはそちらを優先（有効なら Audiveris 自体をスキップして大幅高速化 / NPE 回避）
- MusicXML 単体アップロードでも解析可（PDF 連動ハイライトは不可）

### 再生
- ピアノ音源で伴奏を再生（Salamander Grand Piano、CDN 経由でロード）
- ソロパートが検出された場合はバイオリン風シンセ（AM + Sawtooth）で同時再生
- ソロ音量モード：`普通 / カラオケ(小さめ) / 無し`
- 伴奏音量スライダー（0–120%）、テンポスライダー（30–240 BPM、再生中でもリアルタイム変更可）
- 開始小節／終了小節指定、区間ループ、カウントイン（0–4 小節）、メトロノーム
- フェルマータを検出して音価を延長し、その間のメトロノームクリックを抑制

### 表示
- 「PDF」ビュー：元 PDF を表示し、再生中の小節を黄色でオーバーレイ・ハイライト。該当ページへ自動ページ送り
- 「譜面」ビュー：MusicXML を OSMD でレンダリングし、カーソルを現在小節まで追従
- MusicXML サニタイザ：不完全な `<time>` 除去、`<divisions>=0` 補正、`<octave-shift>` 除去、ゼロ長ノート除去、パート間の欠落小節を空小節で補填、調号の整合化（OSMD クラッシュ対策）
- 解析済み MusicXML をダウンロード可（次回アップロードすれば OMR をスキップ）

## 開発環境

```bash
docker compose up --build
```

- フロント: <http://localhost:5173>
- バックエンド: <http://localhost:8000>（`GET /health` で疎通確認）

初回ビルドは Audiveris（〜500MB）の取得に時間がかかります。

## エンドツーエンド動作確認

1. <http://localhost:5173> を開く
2. IMSLP からダウンロードした短い曲（数ページ）の PDF をドラッグ＆ドロップ
3. 解析完了まで待つ（30秒〜1分程度。長い楽譜ほど Audiveris に時間がかかる）
4. 「再生」ボタンで伴奏ピアノが鳴り、PDF 上で現在小節がハイライトされる
5. テンポスライダーや「開始小節 / 終了小節 / ループ / カウントイン / メトロノーム / 伴奏音量 / ソロ音量」を試す
6. 「譜面」タブで OSMD レンダリング + カーソル追従を確認
7. 「MusicXML をダウンロード」で保存すると、次回以降はその MusicXML と PDF を一緒にドロップするだけで OMR をスキップして即解析

## テスト

```bash
# backend (pytest)
cd backend && pip install -e ".[dev]" && pytest

# frontend (vitest)
cd frontend && npm install && npm test
```

## 既知の制限

- Audiveris の OMR 精度は印刷品質に強く依存。スキャン汚れの多い古い譜面では音符の取りこぼし／誤認が発生します。
- 反復記号（D.C., D.S., volta）は MVP では展開せず、楽譜を上から順に1回だけ演奏します。
- 拍子変更は検出するものの、メトロノーム UI は冒頭の拍子のみ表示します。
- ピアノ音源は CDN（tonejs.github.io）から取得。オフライン運用には自前ホストへ差し替えてください。
- バイオリンパートはサンプルではなくシンセ（PolySynth + AMSynth）で代用。音色は「ピアノと区別できること」を優先した簡易音源です。
- OCR フォールバック（pdf2image + Tesseract）はコンテナ同梱ですが、page 1 の上部 15% のみ走査するため、タイトルが下方にある譜面では検出できないことがあります。

## ディレクトリ

```
sandbox/
├── docker-compose.yml
├── frontend/                    React + Vite (ブラウザ UI)
│   └── src/
│       ├── api/                 バックエンド呼び出し (analyze.ts)
│       ├── audio/               Tone.js エンジン / スケジューラ / メトロノーム
│       │   ├── ToneEngine.ts    ピアノサンプラ + バイオリン風シンセのシングルトン
│       │   ├── Scheduler.ts     Tone.Transport への音符 / 小節コールバック登録
│       │   └── Metronome.ts     クリック音 + カウントイン + フェルマータ抑制
│       ├── components/          PdfUploader / PdfViewer / SheetViewer / PlaybackControls
│       └── music/               MusicXML パーサ + OSMD 向けサニタイザ
└── backend/                     FastAPI + Audiveris + Tesseract
    └── app/
        ├── main.py              /analyze エンドポイント
        ├── schemas.py           Pydantic レスポンスモデル
        ├── omr/                 Audiveris CLI ラッパ + .omr レイアウト解析
        ├── music/               伴奏パート判定 / MusicXML マージ / テンポ・拍子抽出
        └── ocr/                 Tesseract によるテンポ・タイトル OCR フォールバック
```
