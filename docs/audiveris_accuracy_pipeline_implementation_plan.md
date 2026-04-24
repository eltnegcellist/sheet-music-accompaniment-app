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

### 2-1. Audiveris設定最適化
- OCR（歌詞/コード/指番号）を無効化
- 装飾記号認識を抑制
- 不要クラス削減

### 2-2. マルチ試行
- 二値化パラメータ違いの複数画像を生成
- 複数パターンでOMR
- 並列 or バッチ実行

### 2-3. ステップ監視
- GRID段階の五線本数チェック
- スタッフ間隔分散チェック
- 異常時即リトライ

### 2-4. 結果フィルタリング
- 壊れたXML除外（小節数ゼロ、極端な音符数など）

### 2-5. 部分再処理（高度）
- 異常小節検出
- 小節単位で再画像化→再OMR

### 完了条件
- 1入力あたりの有効候補XML数が増える
- 「全損」案件が減る

---

## Phase 3: 後処理（楽譜として成立させる）

### 3-1. リズム補正（最重要）
- 小節拍数チェック
- 不足: 休符挿入
- 過剰: 音削除 or 和音化
- 最小変更アルゴリズム
- 音価スナップ（1/4, 1/8 など）

### 3-2. タイミング補正
- 微ズレ量子化
- 同時刻クラスタリング

### 3-3. 音高補正
- 調性推定（K-S法）
- スケール外音補正
- n-gram的旋律補正
- オクターブ誤り補正

### 3-4. 音域・密度フィルタ
- 楽器音域外削除
- 密度異常検出
- 孤立音削除

### 3-5. 和音・voice再構築（高優先）
- 同時刻音の和音化
- 横ズレ補正
- voice再構成（右手/左手）
- ノイズ声部削除

### 3-6. 記号整理
- タイ整合
- スラー除去/無視
- 装飾音・ダイナミクス削除

### 3-7. テンポ処理
- 固定テンポ上書き
- （オプション）拍構造から推定

### 3-8. 構造補正
- 小節数整合チェック
- リピート/ダカーポ削除 or 展開

### 完了条件
- 拍整合率が目標値に到達
- 演奏不能XMLの発生率が実運用閾値以下

---

## Phase 4: 評価・選択（自動採択）

### 4-1. スコアリング
- 拍整合性
- 音域妥当性
- 密度
- 調性一致
- 構造一貫性

### 4-2. 最適解選択
- 複数OMR結果から最高スコア採択
- 閾値未満は再試行 or 破棄

### 4-3. フィードバックループ
- スコア悪化原因を記録（前処理/OMR/後処理どこで崩れたか）
- 次回パラメータ探索に反映

### 完了条件
- 「最良候補の自動選択」が手動選択と同等以上
- 失敗パターンがログ分類できる

---

## Phase 5: 出力

- MusicXML出力
- MIDI生成
- （オプション）音源レンダリング

---

## 実装順（2スプリント先までの具体タスク）

### Sprint 1（まず必須）
1. Phase 0一式（制御/ログ/パラメータ管理/非同期）
2. Phase 1のうち 1-2, 1-5（五線正規化 + 品質ゲート）
3. Phase 2のうち 2-2, 2-4（マルチ試行 + 壊れXML除外）

### Sprint 2（精度を実際に押し上げる）
1. Phase 3のうち 3-1（拍数補正）
2. Phase 3のうち 3-5（和音/voice再構築）
3. Phase 4のうち 4-1, 4-2（スコアリング + 最適解採択）

---

## リスクと先回り対策

- リスク: マルチ試行で計算コスト増
  - 対策: 品質ゲートで低品質入力を早期除外、ページ並列 + 上限同時実行数
- リスク: 後処理が過補正して原譜を壊す
  - 対策: 最小変更制約、変更量に上限、変更ログ保存
- リスク: 指標最適化が局所化
  - 対策: 複数KPIの加重スコア、楽曲カテゴリ別に評価

---

## 最終メッセージ

この順序で進めると、**再現性の土台 → 認識入力品質 → 候補生成 → 楽譜成立性 → 自動採択** の流れが作れ、
「精度改善が継続的に積み上がる状態」に最短で到達できます。
