# IMSLP Accompanist

IMSLP などのパブリックドメイン PDF 楽譜から **伴奏パート（ピアノ）** を抽出し、ブラウザで演奏する Web アプリのプロトタイプ。
器楽ソロ奏者がリハーサル・本番補助で「伴奏者代わり」に使うことを想定。

## 構成

| 層 | 技術 |
|---|---|
| フロントエンド | React + TypeScript + Vite |
| 譜面表示 | PDF.js（オーバーレイ Canvas で現在小節をハイライト） |
| 音声再生 | Tone.js + Salamander Grand Piano (SoundFont) |
| バックエンド | Python + FastAPI |
| OMR | Audiveris (CLI, Docker 同梱 / **単独運用**) |

## 主な機能（MVP）

- PDF アップロード → OMR で MusicXML + 小節バウンディングボックスを抽出
- 「2段譜のパート」を伴奏（ピアノ）と自動判定。Klavier / Pianoforte などの名称マッチもフォールバック
- ピアノ音源で伴奏を再生（テンポ調整 / 区間ループ / カウントイン / メトロノーム）
- 再生中の小節を元 PDF 上にハイライト
- 任意で同じ曲の MusicXML を一緒にアップロードすると、音符データはそちらを優先（OMR は座標取得のみ）

## OMR エンジン方針（2026-04 更新）

- 本リポジトリの OMR は **Audiveris のみ**を使用します。
- 過去に検証していた Oemer 連携は、実行負荷・運用コストの観点から削除済みです。
- そのため、バックエンドの解析フローは「PDF -> Audiveris -> MusicXML + レイアウト情報」に一本化されています。

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
3. 解析完了まで待つ（30秒〜1分程度）
4. 「再生」ボタンで伴奏ピアノが鳴り、PDF 上で現在小節がハイライトされる
5. テンポスライダーや「開始小節 / 終了小節 / ループ / カウントイン / メトロノーム」を試す

## テスト

```bash
# backend (pytest)
cd backend && pip install -e ".[dev]" && pytest

# frontend (vitest)
cd frontend && npm install && npm test
```

## 既知の制限

- Audiveris 単独運用のため、機械学習ベース OMR との自動融合は行いません。
- Audiveris の OMR 精度は印刷品質に強く依存。スキャン汚れの多い古い譜面では音符の取りこぼし／誤認が発生します。
- 反復記号（D.C., D.S., volta）は MVP では展開せず、楽譜を上から順に1回だけ演奏します。
- ピアノ音源は CDN（tonejs.github.io）から取得。オフライン運用には自前ホストへ差し替えてください。

## ディレクトリ

```
sandbox/
├── docker-compose.yml
├── frontend/                React + Vite (ブラウザ UI)
│   └── src/
│       ├── api/             バックエンド呼び出し
│       ├── audio/           Tone.js エンジン / スケジューラ / メトロノーム
│       ├── components/      PdfUploader / PdfViewer / PlaybackControls
│       └── music/           MusicXML パーサ
└── backend/                 FastAPI + Audiveris（OMR単独）
    └── app/
        ├── main.py          /analyze エンドポイント
        ├── omr/             Audiveris CLI ラッパ + .omr レイアウト解析
        └── music/           MusicXML マージ / 伴奏パート判定 / divisions 抽出
```
