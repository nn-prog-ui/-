# PROGRESS

AI FX市場監視システム 進捗記録

---

## 2026-05-12 初期MVP実装

### 実施内容

#### Phase 0：設計完了
- プロジェクトフォルダ構成作成
- 全ドキュメントファイル作成

#### Phase 1：データ処理完了
- `app/data/loader.py`：CSV読み込み・バリデーション・ダミーデータ生成
- `app/data/resampler.py`：1時間足→4時間足・日足への変換
- `scripts/generate_sample_csv.py`：テスト用CSVサンプル生成

#### Phase 2：テクニカル指標完了
- `app/indicators/moving_average.py`：20MA・75MA計算
- `app/indicators/rsi.py`：RSI14計算
- `app/indicators/atr.py`：ATR14計算・直近高安値
- `tests/test_indicators.py`：pytest テスト

#### Phase 3：判定ルール完了
- `app/strategy/rules.py`：買い/売り/見送り判定ロジック（7条件）
- `app/strategy/scoring.py`：スコア計算（-7〜+7）
- `app/strategy/risk.py`：損切り・利確・RR計算（RR1.5以上条件）
- `tests/test_rules.py`：ルールテスト
- `tests/test_risk.py`：リスク計算テスト

#### Phase 4：Web画面完了（最小版）
- `app/web/routes.py`：FastAPIルーティング
- `app/web/templates/index.html`：メイン判定画面
- `app/web/templates/history.html`：承認履歴画面
- `app/web/static/style.css`：スマホ対応CSS

#### Phase 5：SQLite保存完了（最小版）
- `app/database/db.py`：DB接続・初期化
- `app/database/models.py`：データモデル定義
- `app/database/repository.py`：CRUD操作
- 承認ボタン押下→SQLite記録（注文なし）

#### Phase 6：AIコメント完了（初期はモック）
- `app/services/ai_commentary.py`：ルールベースのコメント生成
- 将来API接続可能な設計（MockCommentaryAdapter）

---

## 2026-05-14 機能拡張（Phase 8〜17）

### Phase 8：リアルタイム価格取得
- `app/data/oanda_adapter.py`：OANDA API価格取得（practice環境専用）
- `app/data/price_source.py`：DATA_SOURCE環境変数でCSV/OANDA切替
- OANDA障害時のCSVフォールバック
- テスト18件

### Phase 9：Gmail SMTP通知
- `app/services/notification.py`：GmailAdapter / LogOnlyAdapter
- 通知条件：NOTIFY_ON_BUY/SELL/SKIP、NOTIFY_MIN_SCORE
- LINE Notify は2025年3月終了のためGmail SMTPを採用

### Phase 10：価格推移追跡
- `app/database/repository.py` に `check_and_close_open_trades()` 追加
- 承認済み取引のSL/TP到達で自動クローズ・損益記録
- `/performance` ページで勝率・損益集計を表示

### Phase 11：精度向上
- `app/indicators/bollinger_bands.py`：BB20±2σ（1時間足）
- `app/indicators/macd.py`：MACD 12-26-9（1時間足）
- `app/indicators/currency_strength.py`：日足モメンタムスコア（5/10/20日）
- 複数通貨ペア対応（USD/JPY・EUR/USD・GBP/USD・EUR/JPY）

### Phase 12：デモ注文連携
- `app/services/demo_order.py`：DemoOrderAdapter（practice専用・live接続不可）
- 2段階確認フロー（チェックボックス×2）
- `app/database/models.py` に demo_orders テーブル追加
- `/demo-trade/{record_id}` エンドポイント
- テスト29件（安全制約・エラーハンドリング含む）

### Phase 13：デモ注文決済・損益追跡
- `DemoOrderAdapter.close_trade()`：OANDA practice APIでポジション決済
- `DemoOrderAdapter.get_trade_detail()`：リアルタイムP&L取得
- `/demo-close/{demo_id}` エンドポイント（確認チェックボックス付き）
- demo_orders テーブルへ exit_price/pnl_pips/closed_at カラムをマイグレーション追加

### Phase 14：デモ注文成績統計
- `get_demo_performance_stats()`：勝率・pips統計の集計
- `/performance` にデモ成績カード5枚を追加
- `/demo-orders` 一覧にサマリーバーを追加

### Phase 15：Phase 6完了（Claude/OpenAI API連携）
- `ClaudeCommentaryAdapter`：Anthropic SDK・プロンプトキャッシュ対応
- `OpenAICommentaryAdapter`：OpenAI Chat Completions API対応
- 優先順位：ANTHROPIC_API_KEY → OPENAI_API_KEY → モック
- 禁止表現サニタイズ（`_FORBIDDEN_WORDS`）
- `requirements.txt` に `anthropic>=0.40.0` / `openai>=1.0.0` 追加
- テスト23件

### Phase 16：定期スキャン（APScheduler）
- `app/services/scheduler.py`：BackgroundSchedulerで全ペアを定期分析
- 環境変数：`SCAN_ENABLED`（デフォルト: true）・`SCAN_INTERVAL_MINUTES`（デフォルト: 60）
- `app/main.py` の startup/shutdown イベントに統合
- 1ペアのエラーで他ペアが止まらない設計
- `requirements.txt` に `apscheduler>=3.10.0` 追加

### Phase 17：バックテストCLI
- `app/scripts/backtest.py`：過去CSVで判定ルールの精度を検証
- 実際の注文は一切発生しない（分析・集計のみ）
- `python -m app.scripts.backtest --symbol USD/JPY --window 500 --step 24`
- SL/TP到達シミュレーション・勝率・pips集計
- テスト13件

### Phase 18：ドキュメント整備
- `README.md`：Phase 8〜17の全機能を追記（フォルダ構成・使い方・設定説明）
- `PROGRESS.md`：全フェーズの実装記録を追記

---

### Phase 64：HTTP Basic認証（本番デプロイセキュリティ）（2026-05-22）

- `app/services/auth.py`：新規作成
  - `AUTH_USERNAME` / `AUTH_PASSWORD`：環境変数から読み込み
  - `AUTH_ENABLED`：両方設定時のみ認証を有効化（未設定時はフリーアクセス）
  - `PUBLIC_PATHS`：`/health`（Railway ヘルスチェック用）
  - `PUBLIC_PREFIXES`：`/static/`（アイコン・CSS・JS・manifest）
  - `parse_basic_auth()`：Authorization ヘッダーを (username, password) に分解
  - `check_credentials()`：`secrets.compare_digest` でタイミング攻撃耐性
  - `is_public_path()`：公開パスかどうかを判定
- `app/main.py`：`BasicAuthMiddleware`（Starlette BaseHTTPMiddleware）を追加
  - 認証不要パスは無条件でスルー
  - 認証失敗時は `401 Unauthorized` + `WWW-Authenticate: Basic realm="AI FX Monitor"`
- `.env.example`：`AUTH_USERNAME` / `AUTH_PASSWORD` 設定例と Railway 変数の説明を追加
- `tests/test_auth.py`：テスト30件新規作成
  - `TestParseBasicAuth`（6件）：有効ヘッダー・None・空・非Basicスキーム・コロン入りPW・不正Base64
  - `TestCheckCredentials`（4件）：正解・誤PW・誤ユーザー・空
  - `TestIsPublicPath`（8件）：各公開/非公開パスの判定
  - `TestAuthMiddlewareEnabled`（7件）：認証ON時の各エンドポイント動作
  - `TestAuthMiddlewareDisabled`（4件）：認証OFF時は全エンドポイントにアクセス可

---

### Phase 54：月次・週次目標管理（2026-05-21）

- `app/database/models.py`：`CREATE_GOALS_TABLE` 追加（trade_goals テーブル）
- `app/database/db.py`：`init_db()` に `CREATE_GOALS_TABLE` 追加
- `app/scripts/goal_tracker.py`：新規作成
  - `TradeGoal` dataclass（id/period_type/period_label/target_pips/symbol/note/actual_pips/progress_pct/achieved）
  - `create_goal()`：UPSERT対応（同一キーは上書き）
  - `get_goals()`：目標一覧 + `approval_history` から実績・進捗を自動計算
  - `delete_goal()`・`get_goal_by_id()`：CRUD
  - `_actual_pips()`：月次は `LIKE` パターン、週次は ISO 週日付範囲で絞込
  - 修正：SQLite NULL は UNIQUE 制約で別扱いのため `symbol` を空文字列で管理
- `app/web/routes.py`：`GET /goals` + `POST /goals` + `POST /goals/:id/delete` 追加
- `app/web/templates/goals.html`：新規作成
  - 目標作成フォーム（期間タイプ切替で自動ラベル補完 JS）
  - 進捗バー（0〜100%、達成=緑 / 50%以上=黄 / 未達=青）
  - 達成バッジ・削除ボタン付き一覧
- 全21テンプレートのナビに「目標管理」リンク追加
- `tests/test_goal_tracker.py`：テスト17件新規作成（全1037件通過）

---

### Phase 53：システムスコアカード（2026-05-21）

- `app/scripts/scorecard.py`：新規作成
  - `MetricGrade` dataclass（name/key/value/unit/grade/comment）
  - `Scorecard` dataclass（総合グレード/スコア/推奨改善案/レーダーデータ）
  - `get_scorecard(symbol, db_path)`：9指標を一括グレーディング
  - 9指標：勝率/期待値/PF/最大DD/SQN/リカバリーF/最大連勝/平均損益/プラス月率
  - `_overall_grade()`：N/A を除く指標の加重平均グレード計算
  - `_make_recommendation()`：最低グレード指標の改善提案を自動生成
- `app/web/routes.py`：`GET /scorecard` + `GET /api/scorecard` 追加
- `app/web/templates/scorecard.html`：新規作成
  - 総合グレード表示（A〜F、スコア表示）+ 改善提案バナー
  - 9指標グレードカード（グレード色ボーダー付き）
  - グレード基準 details 折りたたみ
  - レーダーチャート（Chart.js radar、5軸=A〜F対応）
- 全20テンプレートのナビに「スコアカード」リンク追加
- `tests/test_scorecard.py`：テスト30件新規作成（全1016件通過）

---

### Phase 52：月次・週次パフォーマンスサマリー（2026-05-21）

- `app/scripts/period_stats.py`：新規作成
  - `PeriodStat` dataclass（label/trades/wins/losses/win_rate/total_pips/avg_pips）
  - `PeriodReport` dataclass（月次/週次リスト・最良最悪月・連続プラス/マイナス月数）
  - `get_period_report(symbol, db_path)`：月次・週次を一括集計
  - `_build_period_stats()`：汎用期間集計（月 or 週を切替可能）
  - `_max_consecutive()`：連続プラス/マイナス月数の最大値計算
  - `_parse_dt()` バグ修正：`len(fmt)` スライスを固定長スライスに変更
- `app/web/routes.py`：`GET /period-stats` + `GET /api/period-stats` 追加
- `app/web/templates/period_stats.html`：新規作成
  - サマリーカード6枚（合計pips/集計月数/最良月/最悪月/連続プラス/連続マイナス）
  - 月次損益バーチャート（Chart.js bar、赤/緑色分け）
  - 月次勝率ラインチャート（50%基準線付き）
  - 月次明細テーブル（降順、直近から表示）
  - 週次損益バーチャート（直近20週）
- 全19テンプレートのナビに「月次分析」リンク追加
- `tests/test_period_stats.py`：テスト22件新規作成（全982件通過）

---

### Phase 51：ポジションサイジング計算機（2026-05-21）

- `app/scripts/position_sizing.py`：新規作成
  - `SizingInput` dataclass（残高/リスク%/SL pips/pip価値/勝率/平均損益）
  - `SizingResult` dataclass（固定リスクlot/ケリー比率/半ケリーlot/期待値/警告）
  - `calculate_sizing()`：固定リスク法・ケリー基準（f*=p-q/R）・半ケリー推奨の3手法
  - `get_historical_stats()`：DBから勝率/平均損益を事前取得（フォーム自動補完用）
  - `_round_lot()`：ロットをステップ単位に切り捨て
  - Van Tharp 基準の警告生成（ケリー過大 >25%、リスク過大 >5%）
- `app/web/routes.py`：`GET /position-sizing` + `GET /api/position-sizing` 追加
- `app/web/templates/position_sizing.html`：新規作成
  - 入力フォーム（7項目 + ページ読み込み時に自動計算）
  - 期待値・ペイオフ比・ケリー評価カード
  - 固定リスク法・半ケリーのロット表示
  - 警告ボックス（問題がある場合のみ表示）
  - 手法解説パネル
- 全18テンプレートのナビに「ロット計算」リンク追加
- `tests/test_position_sizing.py`：テスト20件新規作成（全956件通過）

---

### Phase 50：R倍数・期待値分析（2026-05-20）

- `app/scripts/r_multiple.py`：新規作成
  - `RMultipleTrade` dataclass（record_id/symbol/outcome/pnl_pips/r_value/created_at）
  - `RMultipleReport` dataclass（期待値/SQN/平均R/中央値R/標準偏差/ヒストグラム/通貨別）
  - `get_r_multiple_report(symbol, db_path)`：1R基準＝平均実損失pips、R正規化・SQN計算
  - `_build_histogram()`：バケット幅0.5Rのヒストグラムデータ生成
  - `_sqn_grade()`：Van Tharp基準の5段階評価（Poor〜Holy Grail）
- `app/web/routes.py`：`GET /r-multiple` + `GET /api/r-multiple` 追加、インポート追加
- `app/web/templates/r_multiple.html`：新規作成
  - 指標カード9枚（期待値/SQN/平均R/中央値R/標準偏差/最大最小R/1R基準/±Rカウント/件数）
  - R分布ヒストグラム（Chart.js bar）
  - 累積R曲線（Chart.js line）
  - 通貨別SQNサマリーテーブル（グレードバッジ付き）
  - 個別トレード一覧（直近50件）
- 全テンプレートのナビに「R倍数」リンク追加（17テンプレート）
- `tests/test_r_multiple.py`：テスト26件新規作成（全932テスト通過）

---

### Phase 48：連勝/連敗ストリーク分析（2026-05-19）

- `app/scripts/streak.py`：新規作成
  - `StreakEvent` dataclass（type/length/start_at/end_at）
  - `StreakStats` dataclass（最大連勝/最大連敗/現在/平均/発生回数/開始日）
  - `_compute_streaks_v2()` — 時系列 outcome から連続ストリークを抽出
  - `get_streak_stats(symbol)` — 通貨ペア指定・全体集計対応
  - `get_streak_stats_by_symbol()` — 全通貨ペア別統計一覧
- `app/web/routes.py`：ダッシュボードルートにストリーク統計を追加、`GET /api/streaks` エンドポイント追加
- `app/web/templates/dashboard.html`：連勝/連敗ストリークカード追加（最大・現在・平均・通貨ペア別テーブル）
- `tests/test_streak.py`：テスト26件新規作成（全855テスト通過）

---

### Phase 47：ドローダウン分析（2026-05-19）

- `app/scripts/drawdown.py`：新規作成
  - `EquityPoint` dataclass（資産曲線の各点）
  - `DrawdownStats` dataclass（最大DD・平均DD・継続期間・RF・PF・RR・勝率）
  - `_build_equity_curve()` — 時系列 pnl_pips から累積資産曲線を生成
  - `_compute_stats()` — EquityPoint リストから全指標を計算
  - `get_drawdown_stats(symbol)` — 通貨ペア指定・全体集計の両方に対応
  - `get_drawdown_by_symbol()` — 全通貨ペア別統計一覧
  - `equity_curve_to_chart_data()` — Chart.js 用データ変換
- `app/web/routes.py`：`GET /drawdown` ページ・`GET /api/drawdown` API 追加
- `app/web/templates/drawdown.html`：新規作成（資産曲線・DDチャート・通貨ペア別比較表）
- 全テンプレートのナビに「DD分析」リンク追加
- `tests/test_drawdown.py`：テスト30件新規作成（全829テスト通過）

---

### Phase 46：シグナル品質スコアリング（2026-05-19）

- `app/scripts/signal_quality.py`：新規作成
  - `_score_bucket()` / `_rsi_bucket()` / `_trend_match()` — 条件バケット分類
  - `_quality_level()` — 勝率から品質レベル（0〜5）を返す
  - `QualityStats` dataclass（dimension/trades/wins/win_rate/avg_pips/quality_label/quality_level/quality_description）
  - `get_signal_quality()` — 具体→抽象の段階的照合で最も信頼性の高いパターン統計を取得
  - `get_all_pattern_stats()` — 全パターン統計一覧（分析ページ用）
- `app/services/market_analyzer.py`：`AnalysisResult.signal_quality` フィールド追加、run_analysis()で計算
- `app/web/routes.py`：`GET /api/signal-quality` および `GET /api/signal-quality/patterns` エンドポイント追加
- `app/web/templates/index.html`：シグナルセクション直下に品質バッジ（S/A/B/C/D）を表示
- `app/web/static/style.css`：`.quality-badge` / `.quality-s` 〜 `.quality-d` CSSブロック追加
- `tests/test_signal_quality.py`：テスト47件新規作成（全795テスト通過）

---

### Phase 45：ヒートマップカレンダー（2026-05-19）

- `app/scripts/heatmap_calendar.py`：新規作成
  - `HeatmapCell` dataclass（weekday, hour, trades, wins, losses, win_rate, total_pips, avg_pips）
  - `HeatmapResult` dataclass（7×24 セルマトリクス、総取引数、全体勝率、評価テキスト）
  - `get_heatmap_rows()` — approval_history から closed 取引を取得（symbol・is_simulation フィルタ対応）
  - `build_heatmap()` — 7×24 ヒートマップを構築し勝率・損益を集計
  - `_assess()` — 最良/最悪の曜日×時間帯を日本語テキストで評価
  - `_parse_created_at()` — "YYYY-MM-DD HH:MM:SS" / ISO形式対応のパーサー
- `app/web/routes.py`：`GET /api/heatmap-calendar` エンドポイント追加（symbol・metric・data_source フィルタ）
- `app/web/templates/backtest.html`：ヒートマップカレンダーセクション追加（インタラクティブUI + カラースケール凡例）
- `tests/test_heatmap_calendar.py`：テスト48件新規作成（全748テスト通過）

---

### Phase 44：パラメータ感度分析（2026-05-19）

- `app/scripts/sensitivity.py`：新規作成
  - `run_sensitivity()` — ±10%/±20% の5×5マトリクスでバックテスト実行
  - `_clamp_param()` — ma_short≥5、ma_long≤200、rsi 10〜90 に制限
  - `ma_short >= ma_long` のセルは自動スキップ（無効な組み合わせを除外）
  - `optimizer._run_one` と `OptimizeParams` を再利用（コード重複なし）
- `app/web/routes.py`：`GET /api/sensitivity` エンドポイント追加
- `app/web/templates/backtest.html`：感度分析セクション追加（ヒートマップ2枚）
- `tests/test_sensitivity.py`：テスト35件新規作成（全700テスト通過）

---

### Phase 43：モンテカルロ分析（2026-05-19）

- `app/scripts/monte_carlo.py`：新規作成
  - `run_monte_carlo()` — N回シャッフルして期待損益・DD・破産確率の分布を算出
  - `_wilson_ci()` — Wilson score法で勝率の95%信頼区間を計算
  - `get_pnl_pips_from_db()` — DBから損益リストを取得（is_dummy_dataでbacktest/real絞り込み）
- `app/web/routes.py`：`GET /api/monte-carlo` エンドポイント追加（n_simulations上限5000クランプ）
- `app/web/templates/backtest.html`：モンテカルロ分析セクション追加
- `tests/test_monte_carlo.py`：テスト53件新規作成（全665テスト通過）

#### 注意点・修正
- `_max_drawdown` はグローバルピークからの最大下落を返す（部分的なリカバリー後の下落も含む）
- APIパッチパスはテスト内で `app.web.routes.get_pnl_pips_from_db` を指定（routes.py がインポートしているため）

---

### Phase 42：ウォークフォワード分析（2026-05-18）

- `app/scripts/walk_forward.py`：新規作成
  - `WFWindow` / `WalkForwardResult` dataclass
  - `_run_slice()` — バー範囲でバックテスト実行・集計
  - `_fill_window_stats()` — 勝率・pips・過学習スコア・ロバストネス比を計算
  - `run_walk_forward()` — データをn_windows個に分割してIS/OOS検証
  - `_assess()` — 過学習リスク・ロバストネス・OOS勝率を日本語評価
- `app/web/routes.py`：`GET /api/walk-forward` エンドポイント追加（WF分析結果をJSON返却）
- `app/web/templates/backtest.html`：WF分析セクション追加（パラメータフォーム・結果テーブル・集計カード）
- `tests/test_walk_forward.py`：テスト34件新規作成（全612テスト通過）

#### 注意点・修正
- `SUPPORTED_SYMBOLS` のシンボルは `EUR/USD` 形式（スラッシュあり）→テストのシンボルを修正
- `_assess()` は `avg_overfitting_score` または `avg_oos_win_rate` がないと早期リターンするため、ロバストネスのみ検証する場合は `avg_overfitting_score` も同時に設定

---

### Phase 41：Web Push通知（2026-05-18）

- `app/database/models.py`：`CREATE_PUSH_SUBSCRIPTIONS_TABLE` 追加
- `app/database/db.py`：`init_db()` に追加
- `app/database/repository.py`：
  - `save_push_subscription / delete_push_subscription / get_push_subscriptions / count_push_subscriptions` 追加
  - `get_or_create_vapid_keys` 追加（`set_setting` を直接呼ぶよう修正、`save_settings` は `_SETTINGS_DEFAULTS` 外を無視するバグを回避）
- `app/services/push_sender.py`：新規作成（VAPID EC P-256 / ES256 JWT / httpx 非同期 push / `send_push_to_all`）
- `app/web/routes.py`：`/api/push/*` 4ルート追加 + index で BUY/SELL 時に `asyncio.create_task`
- `app/web/static/sw.js`：push / notificationclick ハンドラ追加
- `app/web/templates/settings.html`：プッシュ通知 UI 追加（JS で購読/解除/テスト）
- `cffi` パッケージを `pip install` して `cryptography` の `_cffi_backend` エラーを解消
- `tests/test_push.py`：テスト34件新規作成（全578テスト通過）

---

### Phase 40：PWA対応（2026-05-18）

- `create_icons.py` — stdlib (struct / zlib) のみで PNG アイコンを生成するスクリプトを新規作成・実行
  - 背景 #1a1a2e（ダーク紺）、折れ線チャートモチーフ（緑 #4ade80）
- `app/web/static/icons/icon-192.png` / `icon-512.png` — 生成済みアイコンを配置
- `app/web/static/manifest.json` — PWA 必須フィールドすべて含む（shortcuts 3件）
- `app/web/static/sw.js` — 3戦略で FetchEvent を処理（Static Cache First / HTML Network First / API Network Only）
- 全14テンプレート：`<head>` に `<link rel="manifest">` と Apple 関連 meta を追加
- 全14テンプレート：`</body>` 直前に `navigator.serviceWorker.register` スクリプトを追加
- `tests/test_pwa.py` — テスト87件新規作成（全544テスト通過）
  - ファイル存在確認・PNG バリデーション・manifest フィールド検証・SW 内容確認・テンプレートチェック・HTTP配信確認

---

### Phase 39：経済指標カレンダー（2026-05-18）

- `app/database/models.py`：`CREATE_ECONOMIC_EVENTS_TABLE` 追加
- `app/database/db.py`：`init_db()` に `CREATE_ECONOMIC_EVENTS_TABLE` 追加
- `app/database/repository.py`：
  - `from datetime import datetime` → `datetime, timedelta` に変更
  - `create_economic_event / get_economic_events / count_economic_events / delete_economic_event` 追加
  - `get_upcoming_warning_events / has_upcoming_warning` 追加（window_hours パラメータ対応）
- `app/web/routes.py`：`/calendar` GET/POST、`/calendar/{id}/delete`、`/api/upcoming-events` ルート追加
- `app/web/routes.py`：`/`（判定ページ）に `warning_events` を渡すよう変更
- `app/web/templates/calendar.html`：登録フォーム・フィルター・一覧テーブル・重要度説明新規作成
- `app/web/templates/index.html`：直近24h警戒バッジを挿入
- 全テンプレートのナビに「指標」リンク追加
- `app/web/static/style.css`：`econ-imp-badge`（HIGH/MEDIUM/LOW色分け）・`alert-warning` CSS追加
- `tests/test_calendar.py`：テスト34件新規作成（全457テスト通過）

---

### Phase 38：チャート表示（Chart.js）（2026-05-18）

- `app/web/routes.py`：`GET /api/chart-stats`（月次成績・BUY/SELL別勝率JSON）と `GET /charts`ルート追加
- `app/web/templates/charts.html`：Chart.js CDN使用のチャートダッシュボード新規作成
  - エクイティカーブ（累積pips）、月次棒グラフ複合、月次勝率ライン、BUY/SELL複合グラフ
  - 通貨ペア・件数フィルターで非同期再読み込み
- 全テンプレートのナビに「チャート」リンク追加
- `app/web/static/style.css`：`.chart-container` / `.chart-grid-2col` CSS追加
- `tests/conftest.py`：HTTPインテグレーションテスト用DB初期化フィクスチャを新規作成
  - `scope="session", autouse=True` で全テスト実行前にスキーマ・マイグレーション適用
  - 従来のHTTPテストで `outcome` 列が存在しないエラーを修正
- `tests/test_charts.py`：テスト15件新規作成（全423テスト通過）

---

### Phase 37：通貨相関マトリクス（2026-05-18）

- `app/services/correlation.py`：ピアソン相関係数計算サービス新規作成
  - `CorrelationMatrix` dataclass（matrix / data_points / get() / to_css_class()）
  - `calculate_correlation_matrix()` — 日次リターンの共通インデックス相関計算
  - NaN ガード実装（np.isnan チェック）
- `app/web/routes.py`：`GET /correlation` ルート追加（lookbackクエリパラメータ対応）
- `app/web/templates/correlation.html`：ヒートマップテーブル・凡例・データ点数カード新規作成
- 全テンプレートのナビに「相関」リンク追加
- `app/web/static/style.css`：ヒートマップ用CSSブロック追加（corr-pos/neg-strong/medium/neutral）
- 境界値バグ修正：-0.7の境界テストで期待値を修正（`>= -0.7` は corr-neg-medium）
- `tests/test_correlation.py`：テスト34件新規作成（全408テスト通過）

---

### Phase 36：戦略パラメータ最適化（2026-05-18）

- `app/scripts/optimizer.py`：グリッドサーチ最適化エンジン新規作成（注文なし・分析専用）
  - `OptimizeParams` / `OptimizeResult` dataclass、`_analyze_with_params()`、`optimize()` 関数
  - 本番 `rules.py` は一切変更せず、別関数でパラメータ注入型シグナル判定を実装
  - MA候補×RSI候補のグリッドサーチ、最大200組み合わせ上限
  - CLI対応（`python -m app.scripts.optimizer`）
- `app/web/routes.py`：`GET /optimizer` / `POST /optimizer` ルート追加
- `app/web/templates/optimizer.html`：グリッドサーチフォーム・推奨パラメータカード・結果テーブル新規作成
- 全テンプレートのナビに「最適化」リンク追加
- `app/scripts/optimizer.py`：`load_or_generate()` 呼び出し引数のバグを修正（シグネチャが1引数）
- `tests/test_optimizer.py`：テスト31件新規作成（全374テスト通過）

---

### Phase 35：CSV エクスポート（2026-05-18）

- `app/database/repository.py`：エクスポート用クエリ3関数追加（history/journal/demo-orders）
- `app/web/routes.py`：`csv`/`io` インポート + StreamingResponse + 3エクスポートエンドポイント追加
- `app/web/templates/history.html`：エクスポートバー追加（全件/買いのみ/売りのみ）
- `app/web/templates/journal.html`：エクスポートバー追加
- `app/web/templates/performance.html`：エクスポートバー追加（買い承認/売り承認/デモ注文）
- `app/web/static/style.css`：`.export-bar` / `.export-btn` スタイル追加
- `tests/test_export.py`：テスト16件新規作成（全343テスト通過）

### Phase 34：トレードジャーナル（2026-05-18）

- `app/database/models.py`：`CREATE_TRADE_JOURNAL_TABLE` 追加
- `app/database/db.py`：`init_db()` に trade_journal テーブル作成を追加
- `app/database/repository.py`：CRUD 5関数 + JOURNAL_ENTRY_TYPES / JOURNAL_EMOTION_LABELS 定数追加
- `app/web/routes.py`：`/journal` GET + `POST /journal/{id}` 追加、history ルートに journal データ注入
- `app/web/templates/history.html`：インラインジャーナルフォーム（折りたたみ式）追加
- `app/web/templates/journal.html`：ジャーナル一覧ページ新規作成
- `app/web/static/style.css`：ジャーナル用CSSブロック追加
- 全テンプレートのナビに「ジャーナル」リンク追加
- `tests/test_journal.py`：テスト16件新規作成（全327テスト通過）

### Phase 33：カスタムアラート設定（2026-05-18）

- `app/database/models.py`：`CREATE_ALERTS_TABLE` 追加
- `app/database/db.py`：`init_db()` に alerts テーブル作成を追加
- `app/database/repository.py`：CRUD 6関数追加（create/get/get_active/toggle/delete/update_triggered）
- `app/services/alert_evaluator.py`：条件評価エンジン新規作成（5条件タイプ・クールダウン・通知フォールバック）
- `app/services/scheduler.py`：`_run_scan()` に `evaluate_alerts()` 呼び出し追加
- `app/web/routes.py`：`/alerts` GET/POST + toggle/delete エンドポイント追加
- `app/web/templates/alerts.html`：作成フォーム・一覧・条件説明テーブル新規作成
- `app/web/static/style.css`：アラートリスト用CSSブロック追加
- 全テンプレートのナビに「アラート」リンク追加
- `tests/test_alert_evaluator.py`：テスト22件新規作成（全311テスト通過）

### Phase 32：マルチタイムフレーム判定強化（2026-05-18）

- `app/strategy/scoring.py`：`ConfluenceResult` dataclass + `calculate_timeframe_confluence()` 追加
- `app/strategy/rules.py`：`SignalResult.confluence` フィールド追加、analyze_signal()でconfluence計算
- `app/services/market_analyzer.py`：`AnalysisResult.confluence` フィールド追加・伝播
- `app/web/static/style.css`：TFバッジ・confluenceスコアバッジのCSSブロック追加
- `app/web/templates/index.html`：環境認識カードにconfluenceパネル挿入
- `tests/test_confluence.py`：テスト10件新規作成（全289テスト通過）

---

## エラー記録

### relatedTransactionIDs が空リストの IndexError（Phase 13）
- 原因：`data.get("relatedTransactionIDs", [None])[0]` が空リスト時に IndexError
- 修正：`related = data.get("relatedTransactionIDs") or []; order_id = related[0] if related else None`

---

## 変更履歴

| 日付 | 変更内容 | 主なファイル |
|------|----------|-------------|
| 2026-05-12 | 初期MVP実装（Phase 0〜6） | 全ファイル新規作成 |
| 2026-05-14 | Phase 8 リアルタイム価格取得 | oanda_adapter.py, price_source.py |
| 2026-05-14 | Phase 9 Gmail通知 | notification.py |
| 2026-05-14 | Phase 10 価格追跡 | repository.py, performance.html |
| 2026-05-14 | Phase 11 精度向上 | bollinger_bands.py, macd.py, currency_strength.py |
| 2026-05-14 | Phase 12 デモ注文 | demo_order.py, demo_trade.html |
| 2026-05-14 | Phase 13 デモ決済 | demo_order.py, routes.py |
| 2026-05-14 | Phase 14 デモ成績統計 | repository.py, performance.html |
| 2026-05-14 | Phase 15 Claude/OpenAI連携 | ai_commentary.py |
| 2026-05-14 | Phase 16 定期スキャン | scheduler.py, main.py |
| 2026-05-14 | Phase 17 バックテストCLI | scripts/backtest.py |
| 2026-05-14 | Phase 18 ドキュメント整備 | README.md, PROGRESS.md |
