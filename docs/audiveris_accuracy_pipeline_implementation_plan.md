# Audiveris精度向上パイプライン 実装プラン（優先度順）

対象: **Audiveris完全自動・人手修正なし** での認識精度向上

---

## 目的と成功指標（最初に固定）

- 目的:
  - 壊れたMusicXMLの排除
  - リズム破綻の最小化
  - 和音/voiceの再現性向上
- 主要KPI:
  - `有効XML率`（破損でないXMLの割合）
  - `小節拍整合率`（拍数が一致する小節割合）
  - `音域逸脱率`（楽器音域外ノート割合）
  - `最終採択スコア平均`（評価フェーズの総合点）

---

## 優先順位（効き × 依存関係）

1. **基盤設計（再現性/比較可能性）**
2. **五線基準の前処理（解像度・整列） + 品質ゲート**
3. **マルチ試行 + スコア選択**
4. **拍数補正（リズム強制）**
5. **和音・voice再構成**
6. 音高/タイミング/構造の補正
7. フィードバックループで自動改善

---

## フェーズ別実装

## Phase 0（最優先）: 基盤設計

> 現行 `backend/app/main.py` は `run_audiveris` を一発で呼ぶ直列構造。
> Phase 0 ではこれを「ステージ契約 + 実行計画 + 実行ログ」に再構成する。

### 0-1. パイプライン制御

#### 0-1-a. モジュール配置（追加予定）
```
backend/app/pipeline/
  __init__.py
  contracts.py          # StageInput / StageOutput / StageMetrics
  controller.py         # Pipeline 本体（DAG 実行）
  registry.py           # ステージ登録・解決
  stages/
    __init__.py
    preprocess.py       # Phase 1
    omr.py              # Phase 2（Audiveris 実行・マルチ試行）
    postprocess.py      # Phase 3
    evaluate.py         # Phase 4
  artifacts.py          # 中間生成物の保存/読出し（image, xml, omr）
  debug.py              # デバッグモードの出力先・タグ付け
```

既存 `backend/app/omr/audiveris_runner.py` は `stages/omr.py` から呼び出す
内部ドライバに格下げし、CLI 構築・プロセス監視・出力サルベージはそのまま再利用する。

#### 0-1-b. ステージ契約（`contracts.py` 抜粋スケッチ）
```python
@dataclass(frozen=True)
class StageInput:
    job_id: str                 # 同一 PDF/リクエストで共通
    image_id: str               # ページ or system 単位の一意ID
    page_no: int | None
    params: ParamSet            # 後述 0-2
    artifacts: ArtifactStore    # 前段出力の参照
    trace: TraceContext         # 後述 0-3-c

@dataclass
class StageMetrics:
    duration_ms: int
    cpu_ms: int | None = None
    # ステージ固有の指標（例: staff_detection_rate, valid_xml=True）
    fields: dict[str, float | int | str | bool] = field(default_factory=dict)

@dataclass
class StageOutput:
    status: Literal["ok", "retryable", "failed", "skipped"]
    artifact_refs: list[ArtifactRef]   # (type, path, meta)
    metrics: StageMetrics
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
```

- ステージ関数は `(StageInput) -> StageOutput` のみを契約とする。
- 入力の `params` と出力の `metrics.fields` は **キーを全ステージで名前空間分離**
  （例: `preprocess.binarize.method`, `omr.audiveris.timeout_sec`）。
- 戻り値の `status` は `ok | retryable | failed | skipped` の 4 値に限定し、
  `retryable` のみ自動リトライ対象、`failed` は即打切り。

#### 0-1-c. デバッグモード仕様
- 有効化: 環境変数 `PIPELINE_DEBUG=1` または `params.debug.enabled: true`
- 保存先: `artifacts/{job_id}/{stage}/{image_id}/...`
- 保存対象:
  - 前処理: `raw.png`, `deskew.png`, `binary.png`, `staff_overlay.png`
  - OMR: `audiveris_stdout.log`, `*.omr`, `*.mxl`, `*.xml`
  - 後処理: `pre_fix.musicxml`, `post_fix.musicxml`, `diff.json`
- リリース時は `retention_hours`（既定 24h）経過で非同期GC。

### 0-2. パラメータセット管理

#### 0-2-a. ファイル配置
```
backend/params/
  v1_baseline.yaml       # 現行相当（Audiveris そのまま）
  v2_staff_norm.yaml     # 五線正規化 + 品質ゲート導入
  v3_multi_trial.yaml    # 二値化パラメータのマトリクス試行
  schema.json            # JSON Schema（CIで検証）
```

#### 0-2-b. YAML スキーマ（抜粋）
```yaml
meta:
  id: v2_staff_norm                 # param_set_id（ログ必須フィールド）
  version: 2
  parent: v1_baseline               # 差分のみ書きたい場合の継承元
  description: "五線正規化+品質ゲート導入"

preprocess:
  staff_norm:
    enabled: true
    target_staff_space_px: 22       # 20〜25 の中央値
    tolerance_px: 3
  binarize:
    method: sauvola                 # sauvola | otsu | adaptive_mean
    window: 25
    k: 0.2
  quality_gate:
    min_staff_detection_rate: 0.85
    max_noise_density: 0.04
    on_fail: retry_alt_params       # retry_alt_params | drop

omr:
  audiveris:
    timeout_sec: 1800
    jvm_xmx: "2g"
    plugins_disabled: [ocr, lyrics, chord]
  multi_trial:
    enabled: false
    matrix:
      binarize.method: [sauvola, adaptive_mean]
      binarize.k:      [0.15, 0.2, 0.25]

postprocess:
  rhythm_fix:
    snap_durations: [1, 2, 4, 8, 16]
    max_edits_per_measure: 4
  voice_rebuild:
    enabled: false

scoring:
  weights:
    measure_duration_match: 0.35
    in_range: 0.15
    density: 0.10
    key_consistency: 0.15
    structure_consistency: 0.25

debug:
  enabled: false
  retention_hours: 24
```

- `parent` で継承、差分のみ記述可能（`controller.py` で deep-merge）。
- `schema.json` で key 名と列挙値を縛り、CI（`pytest -k params_schema`）で検証。
- 実行時は解決済み最終 YAML を `artifacts/{job_id}/resolved_params.yaml`
  に保存し、ログに `param_set_id=v2_staff_norm@sha=abcd…` を出す。

#### 0-2-c. パラメータ探索のトリガ
- 手動: API `POST /analyze?param_set=v2_staff_norm`
- 自動 A/B: `param_set=auto` で既定の候補集合を並列実行し Phase 4 で選抜
- 再現: ログの `param_set_id` と `input_sha256` で完全再実行を保証

### 0-3. ジョブ管理

#### 0-3-a. ジョブ階層
```
Job  (1 PDF / 1 /analyze リクエスト)
 └─ Page  (PDF のページ単位、並列の最小単位)
     └─ Trial (param variant; マルチ試行 1 組 = 1 Trial)
```
- `Job.id = uuid4()`、`Page.id = f"{job_id}:p{n}"`、`Trial.id = f"{page_id}:t{k}"`
- 各レベルで独立に `status` を持ち、上位 status は下位の集約ルールで決定:
  - Job.ok ⇔ 1 ページ以上が ok
  - Page.ok ⇔ 1 Trial 以上が ok（ok の中から Phase 4 で選抜）

#### 0-3-b. 非同期化とバックプレッシャ
- 実装は asyncio + `anyio.Semaphore`（`max_concurrent_pages` 既定 4, `max_concurrent_trials` 既定 2）。
- Audiveris は JVM 常駐プロセスが重いので **ページ並列 > Trial 並列** の優先度。
- 将来 Celery/RQ 化が必要になるまでは in-process のタスクプールに留める。

#### 0-3-c. リトライ・タイムアウト・サーキットブレーカ
| 対象          | タイムアウト既定 | リトライ             | ブレーカ発動                         |
|---------------|-----------------|---------------------|--------------------------------------|
| preprocess    | 60 s            | 1 回（別 params）   | 連続 10 Page 失敗で 5 分停止          |
| omr.audiveris | 1800 s          | 0 回（長時間のため） | 連続 5 ページ NPE で 15 分停止         |
| postprocess   | 30 s            | 2 回（冪等前提）    | 連続 20 件失敗で 5 分停止             |
| evaluate      | 10 s            | 1 回                 | 失敗時は `ok` 維持（評価は補助扱い）   |

- ブレーカは `backend/app/pipeline/breaker.py` に `CircuitBreaker` を実装、
  状態は `closed | open | half_open` の 3 値。half_open 時は 1 リクエストだけ通す。

#### 0-3-d. トレースログ（構造化）
- 既定フォーマット: JSON Lines、1 行 1 イベント
- 必須フィールド:
  - `ts`, `level`, `event`（`stage.start` / `stage.end` / `stage.retry` / `stage.failed`）
  - `job_id`, `page_id`, `trial_id`, `stage`, `param_set_id`, `input_sha256`
  - `duration_ms`, `status`, `warnings[]`, `error`
- サンプル:
```json
{"ts":"2026-04-24T09:12:03Z","event":"stage.end","job_id":"…","page_id":"…:p2",
 "trial_id":"…:p2:t0","stage":"omr.audiveris","status":"ok",
 "param_set_id":"v2_staff_norm","duration_ms":184320,
 "metrics":{"valid_xml":true,"measure_count":72}}
```

### 0-4. 再現性テスト（CI 必須）
- `tests/pipeline/test_determinism.py`:
  - 固定サンプル 3 本を 2 回実行し、全ステージの `metrics.fields` の主要キーが一致する
    （許容: `duration_ms` は ±20%、それ以外は完全一致）。
- `tests/pipeline/test_params_schema.py`:
  - `params/*.yaml` を JSON Schema で検証、継承解決後のキーが網羅されていること。
- `tests/pipeline/test_circuit_breaker.py`:
  - 擬似的に連続失敗させ、ブレーカが `open` に遷移し half_open で復帰することを検証。

### 完了条件
- 同一入力を 2 回流して各ステージ `metrics.fields` が許容範囲で一致する
- 任意の失敗ジョブについて `job_id` 1 つからログ追跡で失敗ステージ・params・入力ハッシュが特定できる
- `param_set_id` を指定するだけで過去実行を再現できる

---

## Phase 1: 前処理（五線中心）

> 実装は `backend/app/pipeline/stages/preprocess.py` に集約。
> 依存: `pdf2image`（PDF→PNG）, `opencv-python`（幾何補正/二値化）,
> `scikit-image`（Sauvola, regionprops）, `Pillow`（保存・メタ）。

### 1-1. 入力正規化

#### 1-1-a. PDF → 画像
- ツール: `pdf2image.convert_from_path`（poppler）
- 既定 DPI: 300（小さい楽譜は 400 にブースト、巨大スコアは 250 へフォールバック）
- 出力: 16bit グレースケール PNG（階調維持）
- 例外: 埋め込み JPEG のみの PDF は `pdfimages -j` で直接抽出して DPI を再計算

#### 1-1-b. コントラスト正規化
- 処理順: `dtype→float32/255` → CLAHE (clipLimit=2.0, tileGridSize=8×8) → min-max 正規化
- アンチエイリアス抑制: `cv2.GaussianBlur(3×3, σ=0.6)` の後に
  `np.where(img > 0.6, 1, np.where(img < 0.4, 0, img))` で中間トーンを潰す
  （二値化前のソフトな2段階化、ステム保全のため閾値は広め）

#### 1-1-c. 余白トリミング
- 水平/垂直投影ヒストグラムで非ゼロ領域の bbox を取得
- 余白側に **staff_space_estimate × 2** の安全マージンを残す（クロップしすぎると後段の Hough が狂う）

### 1-2. 五線ベース正規化（重要）

#### 1-2-a. staff space 推定
1. 水平ライン検出（`cv2.HoughLinesP` or 形態学 + `reduce(axis=1)`）で候補行を抽出
2. 行間距離のヒストグラム → 最頻ビン × 4 / 5 で **staff_height** と **staff_space** を同時推定
3. 補強: 縦方向の輝度プロファイルを FFT し基本周波数の逆数から staff space を独立推定。
   両推定値の乖離が 20% 以上なら **低信頼** フラグ → 品質ゲート対象

#### 1-2-b. スケーリング
- 目標 staff space: `params.preprocess.staff_norm.target_staff_space_px`（既定 22px）
- スケール係数 `s = target / estimated`、`s ∉ [0.3, 3.0]` なら異常としてフラグ
- リサンプリングは `cv2.INTER_AREA`（縮小）/ `INTER_CUBIC`（拡大）の自動選択

#### 1-2-c. 五線 Y 座標整列
- 各 staff line について中心 Y を多項式フィット（次数 2）で推定
- 同一 system 内で 5 本の Y が等間隔になるよう「行単位 warp」を適用
  （OpenCV の `remap` で y 座標のみ微調整、x は不変）

#### 1-2-d. 本数チェック
- system ごとに staff line 本数をカウント。5 の倍数でない system は
  `preprocess.staff_norm.line_count_anomaly=true` を metrics に記録。
- 異常 system のみ二値化前後の画像を `artifacts/…/staff_anomaly/` に保存。

### 1-3. 幾何補正

#### 1-3-a. 傾き補正（ページ全体）
- Hough 直線検出で staff lines を抽出 → 角度ヒストグラム → 中央値 θ_page
- |θ_page| < 0.05° なら skip、それ以外は `cv2.getRotationMatrix2D` で回転
- 回転後の境界はパディングで保持（黒帯を入れず白で埋める）

#### 1-3-b. 局所歪み補正（行単位）
- system ごとに θ_system を計算し `|θ_system - θ_page| > 0.3°` なら局所 warp
- 適用は 1-2-c と同じ `remap` で y のみ補正（二重適用回避のため 1-2 と統合実装）

#### 1-3-c. ページ湾曲補正（写真入力）
- `params.preprocess.geometry.photo_mode: true` のときのみ有効
- 方法: staff lines を 2 次多項式フィット → `cv2.remap` で直線化
- PDF 入力ではデフォルト無効（副作用でスキャン品質が劣化するため）

### 1-4. 二値化・ノイズ制御

#### 1-4-a. Sauvola 二値化
- ウィンドウ半径 `w = max(15, round(staff_space * 1.1))`（staff space 連動）
- `k = params.preprocess.binarize.k`（既定 0.2、範囲 0.15–0.25）
- 実装: `skimage.filters.threshold_sauvola`（GPU 不要、CPU で数秒/ページ）

#### 1-4-b. 背景推定→減算→再二値化
- 背景: `cv2.morphologyEx(gray, MORPH_CLOSE, kernel=staff_space*4)`
- 差分: `gray - background`、負値は 0 にクリップ
- 再二値化: 上の Sauvola を差分画像に再適用
- この 2 段階は「日焼け紙」「影」スキャンで効く。スコアが改善しない入力は skip

#### 1-4-c. 小物体除去
- `skimage.measure.regionprops` で面積と円形度を取得
- 除去条件: `area < staff_space^2 * 0.1` **かつ** `circularity > 0.8`
  （記号（符頭・クレフ）の誤消去を避けるため両条件の AND）

#### 1-4-d. 軽いクロージング（ステム保全）
- 縦方向 1×3 の構造要素で `MORPH_CLOSE` を 1 回のみ
- 横方向は適用しない（五線の誤融合を防ぐ）

### 1-5. 品質ゲート（必須）

#### 1-5-a. 計測指標（`stage.metrics.fields` へ記録）
| 指標                         | 定義                                                      | 既定閾値         |
|------------------------------|-----------------------------------------------------------|-----------------|
| staff_detection_rate         | 期待 system 数に対する検出成功 system 数の比              | ≥ 0.85           |
| staff_space_confidence       | 投影ヒストと FFT の staff_space 乖離率（0=一致, 1=最悪）  | ≤ 0.20           |
| noise_density                | 小物体除去前の「非五線・非記号」画素比                    | ≤ 0.04           |
| skew_after_deg               | 補正後の Hough θ 中央値の絶対値                            | ≤ 0.10           |
| contrast_p5_p95              | 正規化後の 5/95 パーセンタイル差                          | ≥ 0.45           |

#### 1-5-b. ゲート判定ロジック
```python
def quality_gate(metrics: StageMetrics, params) -> Literal["pass", "retry", "drop"]:
    fails = [k for k, th in params.thresholds.items()
             if not metrics.fields[k] meets th]
    if not fails:
        return "pass"
    if params.on_fail == "retry_alt_params" and metrics.retry_count < 1:
        return "retry"
    return "drop"
```
- リトライ時は二値化 method を切り替え（sauvola ↔ adaptive_mean）
- 2 回連続で drop した page は Phase 2 に流さず Phase 4 で `status=skipped` として記録

### 1-6. 論理分割

#### 1-6-a. System 境界検出
- 水平投影の谷を staff_space の 3 倍以上の連続ゼロ帯で検出
- 各 system の上下に `staff_space` の余白を付けて切り出し → `page_{n}_system_{k}.png`

#### 1-6-b. グランドスタッフ検出
- system 内の 5 本線クラスタ間距離が `staff_space * 1.5 ～ 4.0` なら同一グランド
- 検出結果は metrics に `grand_staff_groups` として `[(top_y, bottom_y), …]` を記録

#### 1-6-c. 小節境界推定（オプション）
- 垂直線検出（Hough, 角度 ±1°）で bar line 候補を抽出
- 両端が staff line と交差する縦線のみ採用
- 後段（Phase 3 の部分再処理）で活用、本ステージでは metadata に残すだけ

### 1-7. 段階別成果物
- `preprocess_01_normalized.png`（1-1 後）
- `preprocess_02_staff_normalized.png`（1-2 後）
- `preprocess_03_deskewed.png`（1-3 後）
- `preprocess_04_binary.png`（1-4 後）
- `preprocess_05_systems/{k}.png`（1-6 後）
- `preprocess_metrics.json`（上記 1-5-a の全指標）

### 完了条件
- 前処理後の「Audiveris 0 小節出力」率がベースライン比で 30%以上減
- 1-5 の全指標が `metrics.fields` として記録されログから参照可能
- 品質ゲートで drop された page が Phase 4 のレポートに `skipped` として現れる

---

## Phase 2: 認識制御（Audiveris実行戦略）

> 実装は `backend/app/pipeline/stages/omr.py`。
> 現行 `backend/app/omr/audiveris_runner.py` の CLI 組立て・Popen 監視・
> `.mxl` サルベージ・`.omr` 解析は **そのまま再利用**し、以下を追加する。

### 2-1. Audiveris 設定最適化

#### 2-1-a. 現行 CLI の制約を尊重
- `_audiveris_command` は `-batch -export -output <dir> <pdf>` 固定で、
  `-transcribe` や `-save` を同居させると `Voices.refineScore` / `Book.reduceScores` で
  NPE が出るケースがあることを既に確認済み（既存コメント参照）。
- **Phase 2 でも CLI 構成は変えない**。設定は **プラグイン/オプション XML** 側で制御する。

#### 2-1-b. Audiveris の `config/` 側で抑制
- `$AUDIVERIS_HOME/config/run.properties`（または `-option key=value`）で以下を切る:
  - `org.audiveris.omr.text.TextBuilder.useOCR = false`（歌詞・指番号 OCR）
  - `org.audiveris.omr.sheet.Picture.prefered = bw`（カラー分岐を抑制）
  - `org.audiveris.omr.score.Score.useChordNames = false`（コード記号）
- 実装方針: プロファイルごとに `params/audiveris/{profile}.properties` を置き、
  `-option file:<properties>` で指定するラッパを `omr.py` に追加。

#### 2-1-c. JVM チューニング
- `AUDIVERIS_OPTS="-Xmx{jvm_xmx} -XX:+UseG1GC -XX:MaxGCPauseMillis=500"` を環境変数で注入
- 既定 `Xmx=2g`、長大スコア時のみ `4g` に昇格（`params.omr.audiveris.jvm_xmx`）

### 2-2. マルチ試行

#### 2-2-a. 生成マトリクス
- 入力画像バリエーション（Phase 1 成果物を素材に）:
  - `binarize.method ∈ {sauvola, adaptive_mean}`
  - `binarize.k ∈ {0.15, 0.20, 0.25}`（Sauvola のみ）
  - `staff_norm.target_staff_space_px ∈ {20, 22, 25}`
- 既定マトリクス = 2 × 3 = 6 Trial（画像のみ変え、Audiveris 設定は固定）

#### 2-2-b. 並列実行と資源制御
- `anyio.Semaphore(max_concurrent_trials=2)` で Trial 並列を制限（JVM 常駐が重い）
- 1 Trial = 1 Audiveris プロセス、終了後に JVM ごと解放（warm pool は作らない）
- Trial 単位のタイムアウト = `params.omr.audiveris.timeout_sec`（既定 1800s、現行値を踏襲）

#### 2-2-c. 早期打切り（short-circuit）
- 先行 Trial のスコア（Phase 4 の粗スコア）が `params.omr.multi_trial.good_enough_score`（既定 0.90）
  を超えたら残り Trial をキャンセル。
- cancel は `Process.kill()` + 一時ディレクトリの GC。

### 2-3. ステップ監視

#### 2-3-a. 監視ポイント
- Audiveris ログ行頭の `[GRID]`, `[HEADERS]`, `[TRANSCRIPTION]` をパースし段階ごとに:
  - `[GRID]` 完了時: `.omr` 途中成果物が保存されていれば解凍して staff line 数確認
  - `[HEADERS]` 完了時: ヘッダ検出失敗は `warnings` に残す（NPE の前兆が多いステージ）
  - `[TRANSCRIPTION]` 開始時: `last_heartbeat` を更新（60s 以上停止で heartbeat 異常）

#### 2-3-b. GRID 段階チェック
- `.omr` を一時解凍（既存 `layout_parser.parse_omr_project` を流用）し、
  Phase 1 が期待した system 数と `.omr` 内の staff line 数の比を算出
- 比が 0.8 未満なら **即時 kill** → retryable で扱う（他 Trial に資源を譲る）

#### 2-3-c. ハートビート
- Popen の stdout 読み取りループで 1 行受信するたびに `monotonic()` を記録
- `now - last_line > heartbeat_timeout_sec`（既定 180s）なら強制 kill

### 2-4. 結果フィルタリング

#### 2-4-a. 「壊れ XML」判定
- 以下のいずれかに該当したら Trial を `failed` 扱い:
  - `<measure>` 要素数 = 0
  - 全 `<note>` 数 = 0 または 1 小節平均 > 50（明らかな誤検出）
  - 全 `<part>` が空（`<note>` / `<rest>` を 1 つも含まない）
  - `<score-partwise>` か `<score-timewise>` のルートが存在しない
- チェック実装は `stages/omr.py::validate_musicxml_shape(xml) -> IssueList` として
  Phase 4 のスコアリングからも再利用。

#### 2-4-b. 部分的に壊れたページの扱い
- `page_no` 単位で `measure_count < expected * 0.5` を `page.status=degraded` に落とし、
  同 page の他 Trial が `ok` ならそちらを採用、全滅なら `skipped`。

### 2-5. 部分再処理（高度、v2 以降で実装）

#### 2-5-a. 異常小節検出
- Phase 3 の `rhythm_fix` が出す「拍数不一致」メトリクスを入力として、
  連続 3 小節以上が不一致なら「異常 region」とみなす。
- 異常 region の座標は `.omr` の measure bbox から逆引き（`layout_parser.MeasureLayout`）。

#### 2-5-b. 再画像化
- 対象 region のみ元画像から切り出し、Phase 1 のサブセット（1-2, 1-4）を再実行。
- 再 OMR は `-batch -export` を region 画像に対して行う。
- 結果は Phase 3 の「小節差し替え」機構で母スコアに貼り戻す（詳細は Phase 3-8-b）。

#### 2-5-c. 再帰防止
- 同一 region に対する再処理は最大 2 回まで。3 回目以降は諦めて `warnings` に残す。

### 2-6. Trial 結果の集約
- 各 Trial の `OmrResult` に加え、以下を `StageOutput.metrics.fields` に格納:
  - `trial_id`, `valid_xml`, `measure_count`, `note_count`,
    `avg_notes_per_measure`, `grid_ok`, `heartbeat_ok`, `coarse_score`
- `page` レベルに集約して返すとき、ok Trial を `coarse_score` 降順でソートし
  上位 N（既定 3）を Phase 3 に渡す。

### 完了条件
- 1 page あたりの有効 Trial 数 ≥ 1 の割合がベースライン比で +20pt 以上
- NPE/ハング時でも heartbeat または GRID 監視で 3 分以内に kill できる
- 壊れ XML はすべて Phase 4 のレポートに `reason` 付きで現れ、無音で消えない

---

## Phase 3: 後処理（楽譜として成立させる）

> 実装は `backend/app/pipeline/stages/postprocess.py` + サブモジュール群。
> 既存 `backend/app/music/parser.py`（小節/拍情報取得）、
> `accompaniment.py`（part 判定）、`merger.py`（layout マージ）と連携。
> **全ルールは冪等**であること（retry 時に毎回同じ入力から同じ出力）。

### 3-0. 共通基盤
- **内部モデル**: `music21.stream.Score` を一次表現とし、最終的に MusicXML に書き戻す。
  - 変換コスト: `music21.converter.parse(music_xml)` で 100〜500ms / 譜
  - 直 XML 編集は「削除のみ」の限定ユースに留める（複雑な編集は music21 経由）
- **編集ログ**: 1 編集 = 1 イベント（`{op, location, before, after, reason}`）を
  `postprocess_edits.jsonl` に逐次書き出し、Phase 4 で参照。
- **最小変更原則**: 各サブステージは「候補変更集合 → コスト最小の 1 組を採用」の形を取り、
  変更コストは `params.postprocess.edit_costs` で調整可能にする。

### 3-1. リズム補正（最重要）

#### 3-1-a. 小節拍数チェック
- 参照拍数 = `<time>` から取得。拍子変化も `time-signature` イベントで追跡。
- 実測拍数 = 小節内 `<note>/<rest>` の `duration / divisions` の総和（voice ごと）
- `expected - actual` を `delta_beats` として metrics に記録

#### 3-1-b. 編集コスト最小化（DP 定式化）
- 1 小節内の編集を以下の演算に限定し、それぞれコストを付与:
  | 演算                       | コスト (既定) | 前提                                   |
  |---------------------------|--------------|----------------------------------------|
  | 末尾に休符挿入 (delta>0)  | 1            | delta を 1 回で解消                     |
  | 音価スナップ (近似値に丸め)| 2            | 丸め先が既定グリッド内                   |
  | 末尾音削除 (delta<0)       | 3            | 最終音の duration == -delta             |
  | 末尾音を和音化             | 2            | 同時刻の別 voice 音を合流               |
  | タイ延長                   | 1            | 直前小節が同音で終わり、tied-start あり |

- 1 小節あたりの編集回数上限 `max_edits_per_measure`（既定 4）を超えたら補正を諦めて
  `measure.status=unfixable` を metrics に積む。
- 実装: 小節内 voice 列に対し Viterbi ライクな DP（状態＝累積拍数、遷移＝上記演算）。

#### 3-1-c. 音価スナップ
- グリッド = `params.postprocess.rhythm_fix.snap_durations`（既定 `[1, 2, 4, 8, 16]`）
- スナップ閾値: 実測値がグリッドの最寄り値から ±15% 以内なら無条件で丸め、
  ±15〜25% は近傍 2 グリッドの両候補を DP に渡す。

#### 3-1-d. 拍子変化の扱い
- 小節内に拍子変化は起きない前提（OMR で頻出する誤検出）
- `<time>` の途中出現は「次小節から有効」に正規化し、誤検出の疑いがあれば
  前後小節の duration 合計と突き合わせて棄却する

### 3-2. タイミング補正

#### 3-2-a. 量子化グリッド
- 基本グリッド = 最小 `snap_durations`（既定 16 分）
- 三連符・付点は別系統で扱う: `triplet_enabled=true` のとき 12 分グリッドも候補に
- グリッドは **小節内でローカル固定**（小節を跨いだ再グリッド化はしない）

#### 3-2-b. 同時刻クラスタリング
- onset（voice × division 単位のオフセット）のヒストグラムで密度の谷を検出
- 谷を使って近接 onset を 1 クラスタにまとめ、同クラスタ内の音を「同時刻」とみなす
- クラスタ幅上限 = `divisions / 16`（16 分以内）
- クラスタ化されたら最小 onset に揃え、差分は edits ログに残す

#### 3-2-c. 微ズレ閾値の動的決定
- 小節内の onset 標準偏差の 1.5σ を動的閾値に採用
- σ が大きすぎる（> `divisions / 4`）小節は量子化を保留し `noisy_timing` フラグ

### 3-3. 音高補正

#### 3-3-a. 調性推定（Krumhansl-Schmuckler）
- 入力: pitch class ヒストグラム（note × duration 重み付け）
- K-S プロファイル（major / minor × 12）との相関係数を計算
- 最大相関の key を採用、相関値を `key_confidence` として metrics に記録
- 信頼度 < 0.6 の場合は Phase 3-3-b/c の補正を無効化（誤補正リスク回避）

#### 3-3-b. スケール外音補正
- 対象: 単発出現でスケール外かつ前後音と半音差の音（典型的な誤認識パターン）
- 操作: 半音単位で最寄りのスケール音に補正
- 禁止: 同一補正が 1 小節で 2 回以上走る場合は「臨時記号多用の曲」とみなし補正停止
- 記録: `scale_fix_count`, `scale_outliers` を metrics に

#### 3-3-c. n-gram 旋律補正
- 楽曲全体から 3-gram 音程差分布を作成
- 全 3-gram の下位 1% に該当する「不自然なジャンプ」を検出
- 中央音を前後の線形補間に最も近い音に 1 半音以内で補正
- 補正は 1 曲あたり総音数の 2% 以下に制限（`max_ngram_fix_ratio`）

#### 3-3-d. オクターブ誤り補正
- 旋律連続性（前後音の音高差の中央値）に対し ±オクターブ (±12 半音) を試し、
  よりスムーズになる方を採用
- 和音内は対象外（構成音のオクターブは意図的な配置が多い）

### 3-4. 音域・密度フィルタ

#### 3-4-a. 楽器音域テーブル
- `backend/app/music/instrument_ranges.py` を新設:
  ```python
  RANGES = {
      "piano":       ("A0", "C8"),
      "violin":      ("G3", "E7"),
      "viola":       ("C3", "E6"),
      "cello":       ("C2", "C6"),
      "flute":       ("C4", "D7"),
      "clarinet_bb": ("D3", "C7"),
      "voice_sop":   ("C4", "A5"),
      # …
  }
  ```
- part 名正規表現（既存 `_PIANO_NAME_RE` を参考）から楽器 ID を推定
- 推定できない場合は「ワイド既定」`("C1", "C8")` を使う（= 過補正回避）

#### 3-4-b. 音域逸脱の扱い
- 逸脱音は音域に入るまでオクターブ移調（上下どちらも試し、音程連続性の良い方）
- 移調で戻らない（2 オクターブ以上逸脱）の音は **削除し休符置換**（duration 保持）
- `out_of_range_fixed`, `out_of_range_dropped` を metrics に記録

#### 3-4-c. 密度異常検出
- 小節あたり音数のヒストグラムを取り、IQR 外れ値（上側 1.5 × IQR 超え）を異常とみなす
- 異常小節は Phase 2-5 の部分再処理候補に回す
- 下側外れ値（0 音）は Phase 3-1 で既に処理済みなので対象外

#### 3-4-d. 孤立音削除
- 前後ともに `staff_space * 3` 相当以上の時間距離があり、
  かつ voice 内で 1 音だけ極端に短い（duration < `divisions/8`）音は削除
- 削除は 1 小節 1 音を上限（`max_isolated_removals_per_measure`）

### 3-5. 和音・voice 再構築（高優先）

> 既存 `accompaniment.py::_part_has_two_staves` の「2 段譜＝ピアノ」判定と連動。
> ピアノ伴奏 part では staff=1 (右手) / staff=2 (左手) を前提に再構築する。

#### 3-5-a. 和音化（同時刻音の統合）
- Phase 3-2 で得た onset クラスタに対し、同一 voice 内で複数音があるなら
  先頭音を `chord-base`、以降を `<chord/>` 付きで統合
- 統合条件: `duration` が一致 **かつ** `staff` が同一（違う staff は別和音）
- 異 `duration` の同時発音は **voice 分割** の対象（3-5-c へ）

#### 3-5-b. 横ズレ補正
- Audiveris は和音構成音の x 座標を数 px ずらして出すことがある
- `.omr` の x 座標で `|Δx| < staff_space * 0.6` なら同時刻扱い
- 補正済み onset は metadata に `onset_cluster_id` を付与（以降の再処理で再参照可）

#### 3-5-c. voice 再構成（右手 / 左手）
- 前提: 2 staff のピアノ part（1 staff や非ピアノは本節を skip）
- 手順:
  1. note を (onset, pitch, staff_hint) のベクトルで表現。staff_hint は
     Audiveris が付けた `<staff>` と `.omr` の y 座標から決定（y 座標優先）
  2. k=2 クラスタリング（pitch × staff_hint の 2D 特徴）で RH/LH を再割当て
  3. 割当後、連続音の音域ジャンプが大きい voice を平滑化（median ±12 半音から逸脱で再割当て）
- 保守: 再割当て率が 30% を超えたら元の割当てに rollback（=誤補正ガード）

#### 3-5-d. ノイズ声部削除
- voice あたりの総 note 数が全体の 2% 未満、または継続時間が 4 小節未満なら
  「ノイズ声部」として削除候補
- ただし単音旋律（ソロ楽器 part 全体）は絶対に削除しない：
  → 削除は `accompaniment_part_id` に対してのみ許可

### 3-6. 記号整理

#### 3-6-a. タイ整合
- `<tie type="start"/>` と `<tie type="stop"/>` のペアリングを再検査
- 不整合パターンと処理:
  | 症状                          | 処理                                                |
  |------------------------------|-----------------------------------------------------|
  | start のみ / 次音が別音高    | start を削除                                          |
  | stop のみ / 前音が別音高     | stop を削除                                           |
  | start 後の stop が 2 小節以上先 | 中間音を確認、同音継続なら chain、違えば start 削除 |
  | 和音内 tie の向き不整合       | 和音 base の tie を正とし他は再計算                   |

#### 3-6-b. スラー処理（削除寄り）
- MIDI 再生には不要 → `params.postprocess.symbols.drop_slurs=true`（既定 true）で削除
- 視覚表示が要る環境では保持するオプションを残す（将来用）

#### 3-6-c. 装飾音・ダイナミクス
- `<grace>` 音符: 自動再生では無視されやすいため MIDI レンダリング前に削除
- `<dynamics>` / `<wedge>`: 保持（Phase 5 の MIDI 生成時に velocity に反映）
- トリル / モルデント: `<ornaments>` は削除（`grace` と同じ扱い）

#### 3-6-d. 拍子・調号の整合
- 同一 divisions 内での重複する `<time>` / `<key>` は最初の 1 つのみ残す
- Audiveris が各 page 先頭に重複挿入することがあるため、連続する同値は除去

### 3-7. テンポ処理

> 既存 `ocr/tempo_ocr.py::extract_tempo_from_pdf` が PDF 上段の速度標語を
> 読み取る実装。これを Phase 3 の一部として呼び出し、
> `parser.extract_tempo_info` と統合する。

#### 3-7-a. ソース優先順位
1. MusicXML 内 `<sound tempo=...>` / `<metronome>`（既存抽出）
2. PDF OCR による速度標語（`extract_tempo_from_pdf`）
3. 既定値 `params.postprocess.tempo.default_bpm`（既定 72）

#### 3-7-b. 揺らぎ対応（オプション）
- MusicXML に複数 tempo がある場合は位置情報付きで保持
- `rit.` / `accel.` などは正規表現で拾い、区間の目安を warnings に記録（補正はしない）

#### 3-7-c. 固定テンポ上書き
- 運用モード `params.postprocess.tempo.mode="fixed"` のとき、API 引数の `tempo_bpm` を優先
- そのとき source=`user_override` として metrics に記録

### 3-8. 構造補正

#### 3-8-a. 小節数整合
- 期待小節数（= 上位 Trial が報告する中央値）と各 Trial の `measure_count` を比較
- ±5% 以内なら許容、外れたら Phase 4 のスコアリングで減点

#### 3-8-b. 小節差し替え機構（Phase 2-5 と対をなす）
- 入力: 再 OMR した region の MusicXML + 元スコアの MusicXML
- 手順:
  1. 両方を music21 で parse
  2. 差し替え対象 measure の `number` 範囲で元 Score の measure を除去
  3. 新 region の measure を挿入、part 対応は `id` 一致 + 既定 part_idx で決定
  4. `<clef>`, `<key>`, `<time>` が欠落する場合は直前小節からコピー
- 失敗時（part 対応取れない等）は rollback し `warnings` に残す

#### 3-8-c. リピート / ダカーポ
- 既定: `repeat_mode="expand"`（自動展開して直線化）
- `<barline location="left"><repeat direction="forward"/>` と
  `<barline location="right"><repeat direction="backward"/>` のペアを展開
- `<ending>` あり（1st/2nd）: 2 回目は 1st を飛ばすルールで展開
- `da capo`, `dal segno`, `coda`: 未対応 → `drop` モードで記号だけ削除（将来拡張）

#### 3-8-d. part 連動の整合
- 全 part で小節数が一致していることを最終チェック
- ずれがあれば短い part の末尾に空小節（全休符）を追加して揃える

### 3-9. Phase 3 の出力物
- `postprocess_edits.jsonl`（全編集の順序付きログ）
- `postprocess_metrics.json`（下記の集約指標）
  - `measure_duration_match_rate`, `rhythm_unfixable_count`, `scale_fix_count`,
    `out_of_range_fixed`, `voice_rebuild_applied`, `tie_fixed_count`,
    `ngram_fix_count`, `removed_notes`, `added_rests`
- `postprocess_output.musicxml`（最終成果物）

### 完了条件
- 拍整合率（`measure_duration_match_rate`）が全サンプルで ≥ 0.95
- 編集ログ 1 つから「どの小節でどんな操作が何のために行われたか」が再現できる
- 既存 `merger.py::merge_layout_with_musicxml` が Phase 3 出力を問題なく受け入れる
- 既存 `find_accompaniment_part` / `find_solo_part` が Phase 3 後でも正しい part ID を返す

---

## Phase 4: 評価・選択（自動採択）

> 実装は `backend/app/pipeline/stages/evaluate.py`。
> Phase 2 の「粗スコア」(coarse) はファスト判定用の簡易実装、
> Phase 4 のスコア (final) は後処理済み MusicXML に対する厳密評価。
> 両者は同じ `fields` キー体系を共有し、coarse は一部指標を `NaN` で返す。

### 4-1. スコアリング

#### 4-1-a. 部分指標の定義
| key                          | 定義                                                                         | 範囲        |
|------------------------------|------------------------------------------------------------------------------|-------------|
| `measure_duration_match`     | 小節単位で期待拍数と一致する割合（voice 集約後）                              | [0, 1]       |
| `in_range`                   | 全音高に対する `音域内音 / 全音` の比                                         | [0, 1]       |
| `density`                    | 小節あたり音数が IQR 内に収まる割合                                           | [0, 1]       |
| `key_consistency`            | 推定キーのスケール音比率 × K-S 信頼度                                         | [0, 1]       |
| `structure_consistency`      | part 間の小節数一致度 + tie 整合度 + 空 part 無し（3 要素の重み付き平均）        | [0, 1]       |
| `edits_penalty`              | Phase 3 編集数 / 全音数（**加点ではなく減点**、多いほど悪い）                  | [0, ∞)       |

#### 4-1-b. 総合スコア
```
final_score = Σ_i w_i * metric_i  -  w_edits * edits_penalty
w_i は params.scoring.weights（既定は 0-2-b の YAML に記載）
```
- 重みは **和が 1.0 になる制約**を CI で検証（`tests/pipeline/test_scoring_weights.py`）
- 既定値（Phase 0 の YAML と同値）:
  - `measure_duration_match=0.35`, `structure_consistency=0.25`,
    `in_range=0.15`, `key_consistency=0.15`, `density=0.10`
  - `edits_penalty` は `w_edits=0.15` を乗じて減算

#### 4-1-c. ハード失格条件（スコア評価前にゼロ化）
- `measure_count == 0`
- `Σ note_count == 0`
- MusicXML パース失敗（XML 破損）
- 任意 part の全小節が空

→ 該当する Trial は `final_score = 0`, `reason=disqualified_<cause>` で記録。

#### 4-1-d. 正規化・スケーリング
- 全指標は 0–1 に正規化済みで入ってくる前提
- `edits_penalty` のみ非有界なので `tanh(x)` でソフトに 0–1 に収める
- 学習的な重み調整を将来入れる場合は `sklearn.isotonic` 等で後付け可

### 4-2. 最適解選択

#### 4-2-a. 集約階層
```
Trial  ─ final_score  ─┐
                       ├→ Page.best_trial = argmax(final_score)
Page   ─ best_trial  ──┤
                       ├→ Job.score = weighted_mean(Page.best_trial.score)
                                          weight = page の note 数 (長いページほど重い)
```

#### 4-2-b. 採択ゲート
- Page 採択: `best_trial.final_score >= params.scoring.page_threshold`（既定 0.70）
- 閾値未満の Page:
  - `on_low_score="retry"` なら別 params で 1 回再試行
  - `on_low_score="skip"` なら `status=skipped` で通過（全体は続行）
  - `on_low_score="fail_job"` なら Job ごと失敗扱い
- 既定は `retry`

#### 4-2-c. Tie-break（同点時の優先順位）
1. `measure_duration_match` が高いもの
2. `edits_penalty` が低いもの
3. `param_set_id` の辞書順（再現性のため決定論的に）

#### 4-2-d. 採択結果の persistence
- 採択された Trial の `param_set_id` を `artifacts/{job_id}/chosen.json` に記録
- 次回同一入力（`input_sha256` 一致）では採択 param_set を既定候補の先頭に置く
  （= ウォームスタート、探索の収束加速）

### 4-3. フィードバックループ

#### 4-3-a. 失敗分類体系
- `failure_class` を次のラベルで記録:
  - `preprocess.quality_gate_drop`
  - `omr.npe_in_transcription`
  - `omr.heartbeat_timeout`
  - `omr.invalid_xml`
  - `postprocess.rhythm_unfixable`
  - `postprocess.voice_rebuild_rollback`
  - `evaluate.low_score_below_threshold`
- ラベル付与は各ステージが `metrics.fields["failure_class"]` に書き込む

#### 4-3-b. 崩れた工程の特定
- `final_score < 0.7` かつ Trial が `ok` の場合、ステージ別に以下を評価:
  - 前処理: `staff_detection_rate < 0.85` → `blame=preprocess`
  - OMR: `valid_xml=false` or `grid_ok=false` → `blame=omr`
  - 後処理: `rhythm_unfixable_count > 2` or `scale_fix_count > avg*3` → `blame=postprocess`
- `blame` は最も早く該当したステージ 1 つに絞る

#### 4-3-c. パラメータ探索の自動化
- `param_set=auto` 指定時の探索戦略:
  - 1 回目: `v1_baseline`, `v2_staff_norm`, `v3_multi_trial` を並列
  - 2 回目以降: 前回採択 params をシード、`blame` に応じて関連キーを bandit で摂動
- 摂動対象マップ（抜粋）:
  - `blame=preprocess` → `binarize.k ∈ {0.15, 0.2, 0.25}`, `target_staff_space_px ∈ {20, 22, 25}`
  - `blame=omr` → `jvm_xmx`, `audiveris.plugins_disabled` 組合せ
  - `blame=postprocess` → `rhythm_fix.max_edits_per_measure ∈ {3, 4, 5}`
- 探索記録は `artifacts/{job_id}/search_history.jsonl`

#### 4-3-d. レポート出力
- ジョブ終了時に `artifacts/{job_id}/report.md` を生成:
  - 全 page × Trial のスコア表
  - 採択結果と理由
  - `failure_class` ヒストグラム
  - Phase 3 編集数トップ 10 小節
- HTML 版（`report.html`）もオプションで生成（CI で人が見る用）

### 4-4. オフライン評価（回帰検知）
- サンプル 20 本程度を `tests/fixtures/golden/` に配置（PDF + 期待 MusicXML）
- `tests/pipeline/test_regression.py` で:
  - 全サンプルの `final_score` 平均が main ブランチ値より下がっていないこと
  - `measure_duration_match` の 95 パーセンタイルが閾値以上であること
- PR で閾値割れしたら fail。ベースライン更新は明示 commit (`fixtures: refresh baseline`) でのみ

### 完了条件
- 同一入力に対して自動採択結果が手動ラベル（5 本のゴールデン PDF）と一致率 ≥ 0.8
- `blame` ラベルが失敗ケースの 90% 以上に付与される
- 再実行時に `chosen.json` によるウォームスタートが効いて総実行時間が短縮される

---

## Phase 5: 出力

### 5-1. MusicXML 出力
- 生成源: Phase 4 で採択された Trial の `postprocess_output.musicxml`
- 既存 `merge_layout_with_musicxml`（`backend/app/music/merger.py`）を通して
  measure bbox 情報を埋め込み → フロント連動を維持
- `AnalyzeResponse.music_xml` にそのまま格納（既存 API スキーマと互換）

### 5-2. API スキーマ拡張（後方互換）
既存 `AnalyzeResponse`（`backend/app/schemas.py`）はフィールド追加のみで拡張:
```python
class AnalyzeResponse(BaseModel):
    # 既存フィールド（変更なし）
    music_xml: str
    score_title: str | None = None
    accompaniment_part_id: str | None
    solo_part_id: str | None = None
    measures: list[MeasureBox]
    divisions: int
    tempo_bpm: float
    tempo_source: str = "default"
    tempo_matched_word: str | None = None
    tempo_candidates: list[str] = Field(default_factory=list)
    time_signature: TimeSignatureModel | None = None
    page_sizes: list[tuple[float, float]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # 追加（Phase 4 以降で埋まる）
    job_id: str | None = None                  # artifacts/{job_id} への参照
    param_set_id: str | None = None
    pipeline_metrics: dict[str, float] | None = None  # final_score などの主要指標
    pipeline_report_url: str | None = None     # report.md への相対パス
```
- `pipeline_metrics` は最低でも `final_score`, `measure_duration_match`,
  `in_range`, `edits_penalty` を含める
- 既存クライアント（フロント）は新フィールドを無視して動くので破壊的変更なし

### 5-3. MIDI 生成（オプション）
- ツール: `music21.converter.write('midi')` or `pretty_midi`
- 保存: `artifacts/{job_id}/output.mid`
- velocity: `<dynamics>` を 20–127 にマッピング（`ppp=20, pp=35, p=50, mp=65, mf=80, f=95, ff=110, fff=125`）
- `<metronome>` → set_tempo、ない場合は `AnalyzeResponse.tempo_bpm`

### 5-4. 音源レンダリング（オプション、v2+）
- 既存スコープ外。`fluidsynth` or `timidity` を別サービスに切り出す前提でインタフェースのみ用意
- API: `GET /analyze/{job_id}/audio.wav?soundfont=xxx`（遅延生成）

### 5-5. デバッグ成果物の公開
- 開発環境のみ `GET /artifacts/{job_id}/...` を静的配信（本番は直接配信しない）
- リリース環境では `pipeline_report_url` から Signed URL を返し、期間限定ダウンロード

---

## 実装順（2スプリント先までの具体タスク）

> 見積もりは「作業者 1 人 1 日 = 1 pt」換算。
> 各タスクに「完了定義 (DoD)」を明記し、PR テンプレと紐付ける。

### Sprint 1（まず必須）: 基盤 + 認識候補生成

#### S1-01: pipeline スケルトン（4pt）
- ファイル: `backend/app/pipeline/{__init__.py,contracts.py,controller.py,registry.py,artifacts.py,debug.py}`
- DoD: `Pipeline().run(job)` が空ステージ列を回し、構造化ログ（0-3-d）を吐ける

#### S1-02: Stage 抽象と既存 Audiveris 呼び出しの移植（3pt）
- ファイル: `backend/app/pipeline/stages/omr.py`（既存 `omr/audiveris_runner.py` を `_drive_audiveris` として内部化）
- `main.py` から直接呼ぶのをやめ、`Pipeline` 経由に差し替え
- DoD: 既存 `/analyze` のレスポンスが変わらない（既存テスト全緑）

#### S1-03: パラメータ管理（3pt）
- ファイル: `backend/params/v1_baseline.yaml`, `backend/params/schema.json`, `pipeline/params_loader.py`
- 継承解決、JSON Schema 検証、`artifacts/{job_id}/resolved_params.yaml` の書き出し
- DoD: `tests/pipeline/test_params_schema.py` 通過

#### S1-04: 五線正規化 + 品質ゲート（5pt）
- ファイル: `pipeline/stages/preprocess.py`（1-1, 1-2, 1-5 のみ）
- 1-3, 1-4 は既定オフ、1-6 は後続スプリントへ
- DoD: 品質ゲート metrics が出力される / ゲート drop が後段に流れない

#### S1-05: マルチ試行（4pt）
- `pipeline/stages/omr.py` に Trial 並列、`Semaphore` + キャンセル
- `good_enough_score` の早期打切りは S1 では省略（Phase 4 実装後）
- DoD: 2×3 マトリクスが並列で走り、Trial 単位のログが出る

#### S1-06: 壊れ XML フィルタ（2pt）
- `validate_musicxml_shape` の実装と Phase 2 統合
- DoD: `measure_count=0` の Trial が `status=failed` で落ちる

#### S1-07: 再現性 CI（2pt）
- `tests/pipeline/test_determinism.py`, `test_circuit_breaker.py`
- DoD: CI で 2 連続実行の結果一致を検証

**Sprint 1 合計 = 23pt（およそ 2 週間 @ 2 名体制）**

### Sprint 2（精度を実際に押し上げる）: 後処理 + 自動採択

#### S2-01: music21 導入 + postprocess スケルトン（3pt）
- `pyproject.toml` に `music21` 追加、`pipeline/stages/postprocess.py` の骨組み
- DoD: MusicXML → music21 Score → MusicXML の round-trip が無損失

#### S2-02: 拍数補正（6pt）
- `postprocess/rhythm_fix.py`: 3-1 の全サブ（小節 DP を含む）
- 編集ログ（`postprocess_edits.jsonl`）
- DoD: ゴールデン 5 本で `measure_duration_match_rate` ≥ 0.95

#### S2-03: 和音化 + voice 再構築（5pt）
- `postprocess/voice_rebuild.py`: 3-5 全サブ（rollback ガード込み）
- DoD: ピアノ譜ゴールデンで voice 数が目視妥当 / rollback が発火しない

#### S2-04: スコアリング + 最適解採択（4pt）
- `pipeline/stages/evaluate.py`: 4-1, 4-2
- `chosen.json` とウォームスタート
- DoD: `final_score` が `pipeline_metrics` に載って API 経由で返る

#### S2-05: 回帰テスト（3pt）
- `tests/fixtures/golden/` に 5 サンプル追加
- `tests/pipeline/test_regression.py` を CI に統合
- DoD: PR で `final_score` 下がる変更がブロックされる

**Sprint 2 合計 = 21pt**

### Sprint 3 以降（参考）: 残りの高度機能
- 3-2, 3-3, 3-4 の本格実装（タイミング/音高/音域）
- 2-5 部分再処理
- 3-8-b 小節差し替え
- 4-3-c bandit 探索
- Phase 5-4 音源レンダリング

---

## リスクと先回り対策

### 技術リスク
| リスク                                        | 影響                            | 先回り対策                                                           |
|----------------------------------------------|--------------------------------|---------------------------------------------------------------------|
| マルチ試行で計算コスト増                      | p95 レイテンシ悪化              | 品質ゲートで低品質入力を早期 drop、`max_concurrent_trials` で上限制御 |
| 後処理が過補正して原譜を壊す                  | 採択品質の劣化                   | 最小変更制約、編集数 penalty、rollback ガード、編集ログ残し            |
| 指標最適化が局所化する                        | 特定ジャンルで劣化               | 複数 KPI 加重、楽曲カテゴリ別に回帰テスト、ゴールデンに多様性確保       |
| Audiveris の NPE（Voices.refineScore等）      | Trial が増えれば頻度も増える      | GRID 監視で早期 kill、heartbeat timeout、`-export` のみ CLI を維持     |
| music21 の導入で依存が重くなる                 | Docker イメージサイズ増           | `music21` は backend 用に限定、corpus 除外 (`music21.corpus` 不使用)   |
| 再現性の崩れ（乱択の混入）                    | 自動採択の揺らぎ                 | 乱数は `numpy.random.default_rng(seed)` に統一、seed は `param_set_id` から導出 |
| JVM のメモリリーク                             | 長時間実行で OOM                 | 1 Trial = 1 JVM プロセスで隔離（warm pool しない）、`Xmx` 上限明示    |

### 運用リスク
| リスク                                                | 対策                                                                 |
|------------------------------------------------------|---------------------------------------------------------------------|
| `artifacts/` が肥大化                                 | `retention_hours` で非同期 GC、`PIPELINE_DEBUG` を本番無効          |
| ユーザ提供 MusicXML 経路（現行 `main.py`）が回帰しやすい | 既存分岐（`user_xml_looks_valid`）を Phase 0 移植後も厚めにテスト     |
| 静的配信による情報漏洩                                | 本番は Signed URL 経由のみ、直接パス配信を禁止                        |
| ログ肥大                                             | JSON Lines + lv (level) フィルタ、本番は WARN 以上だけ永続化            |

---

## 既存コードとの接続点まとめ

| 既存ファイル / シンボル                                    | Phase/節での役割                                                  |
|-----------------------------------------------------------|----------------------------------------------------------------|
| `backend/app/main.py` の `/analyze`                        | Pipeline への単一エントリポイント（S1-02 で移植）                  |
| `backend/app/omr/audiveris_runner.py::run_audiveris`       | Phase 2 の `_drive_audiveris` として内部化、CLI 構成は不変         |
| `backend/app/omr/layout_parser.py::parse_omr_project`      | Phase 2-3-b の GRID 監視と Phase 2-5-a の region 逆引きに再利用     |
| `backend/app/music/parser.py::extract_*`                   | Phase 3-1, 3-7, 3-8 の入力ソース                                   |
| `backend/app/music/accompaniment.py::find_*_part`          | Phase 3-5-c の voice 再構成の対象判定、Phase 3-6-c のノイズ声部削除 |
| `backend/app/music/merger.py::merge_layout_with_musicxml`  | Phase 5-1 で layout + MusicXML を最終マージ                        |
| `backend/app/ocr/tempo_ocr.py::extract_tempo_from_pdf`     | Phase 3-7-a のソース優先順 2                                         |
| `backend/app/schemas.py::AnalyzeResponse`                  | Phase 5-2 で後方互換に拡張                                          |

---

## ドキュメントとしての更新ルール
- 仕様変更が発生したら **必ず本書を先に更新**（コード先行を禁止）
- 各 Phase の冒頭に `> 実装は …` として「責任ファイル」を書き続けること
- `完了条件` は PR レビュー時の受け入れチェックリストとして使う

---

## 最終メッセージ

この順序で進めると、**再現性の土台 → 認識入力品質 → 候補生成 → 楽譜成立性 → 自動採択** の流れが作れ、
「精度改善が継続的に積み上がる状態」に最短で到達できます。
