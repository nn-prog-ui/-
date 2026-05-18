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
