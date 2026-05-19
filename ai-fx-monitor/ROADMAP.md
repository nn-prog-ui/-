# ROADMAP

AI FX市場監視システム 開発ロードマップ

---

## Phase 0：設計・基盤（完了）

- [x] 要件整理
- [x] フォルダ構成作成
- [x] ROADMAP.md
- [x] PROGRESS.md
- [x] CLAUDE.md
- [x] README.md
- [x] .env.example
- [x] .gitignore
- [x] requirements.txt

---

## Phase 1：データ処理（完了）

- [x] CSV読み込み（loader.py）
- [x] OHLCデータ処理・バリデーション
- [x] 日足・4時間足・1時間足への変換（resampler.py）
- [x] 欠損値処理
- [x] サンプルCSV自動生成スクリプト
- [x] CSVなし時のダミーデータフォールバック

---

## Phase 2：テクニカル指標（完了）

- [x] 20MA計算
- [x] 75MA計算
- [x] RSI（14期間）
- [x] ATR（14期間）
- [x] 直近高値（20本）
- [x] 直近安値（20本）
- [x] pytest テスト作成

---

## Phase 3：判定ルール（完了）

- [x] 買い候補判定（7条件）
- [x] 売り候補判定（7条件）
- [x] 見送り判定（データ不足・条件未充足）
- [x] 理由の構造化（条件ごとの合否）
- [x] スコアリング（-7〜+7）
- [x] 損切り・利確候補の計算
- [x] リスクリワード計算（1.5以上が条件）
- [x] pytest テスト作成

---

## Phase 4：Web画面（完了）

- [x] FastAPI起動
- [x] 現在判定の表示
- [x] 根拠・条件の表示
- [x] エントリー・損切り・利確・RR表示
- [x] 買い/売り/見送りボタン
- [x] スマホ対応レスポンシブ表示
- [x] 承認履歴ページ

---

## Phase 5：SQLite保存（完了）

- [x] 判定履歴保存（全フィールド）
- [x] 人間の承認アクション記録
- [x] 判定時点の価格・根拠の保存
- [x] 後から検証可能な形式

---

## Phase 6：AIコメント（完了）

- [x] モック実装（ルール結果をもとに文章生成）
- [x] Claude API連携アダプター（ANTHROPIC_API_KEY + prompt caching）
- [x] OpenAI API連携アダプター（OPENAI_API_KEY、gpt-4o-mini デフォルト）
- [x] 優先順位：Claude > OpenAI > モック自動フォールバック
- [x] 禁止表現サニタイズ（_FORBIDDEN_WORDS チェック）
- [x] テスト23件

---

## Phase 7：README整備（完了）

- [x] インストール方法
- [x] 起動方法
- [x] CSVの置き方
- [x] 画面の見方
- [x] テスト方法

---

## 完了フェーズ

### Phase 8：リアルタイム価格取得 ✅

- [x] OANDAデモ口座APIアダプター（完全分離設計、app/data/oanda_adapter.py）
- [x] 価格取得インターフェース定義（price_source.py: DATA_SOURCE切替）
- [x] CSVフォールバック機能（OANDA障害時は自動CSVへ）
- [x] テスト18件

### Phase 9：通知機能 ✅

- [x] Gmail SMTP通知アダプター
- [x] 通知条件設定（スコア閾値・BUY/SELL判定時のみ）
- [x] ※LINE Notify は2025年3月終了のためGmail SMTPを採用

### Phase 10：価格推移追跡 ✅

- [x] 承認後の価格追跡（entry/SL/TP到達で自動クローズ）
- [x] 損益（pips）記録
- [x] 勝率・RR実績集計
- [x] 成績ページ（/performance）

### Phase 11：精度向上（完了）

- [x] ボリンジャーバンド追加（BB20・±2σ、1時間足）
- [x] MACD追加（12・26・9、1時間足）
- [x] 通貨強弱フィルター（日足モメンタムスコア 5/10/20日）
- [x] 複数通貨ペア対応（USD/JPY・EUR/USD・GBP/USD・EUR/JPY）

### Phase 12：デモ注文連携（十分な検証後のみ）✅

- [x] デモ口座注文アダプター（本番層と完全分離）
- [x] 注文前の多重確認フロー（2段階チェックボックス）
- [x] OANDA practice API連携（DemoOrderAdapter）
- [x] デモ注文履歴DB保存・一覧画面
- [x] 承認履歴からデモ注文へのリンク（buy/sell承認のみ）
- [x] テスト29件（安全制約・エラーハンドリング含む）
- [x] ※本番注文は絶対に作らない（将来でも慎重に検討）

### Phase 16：定期スキャン（APScheduler）✅

- [x] `app/services/scheduler.py` — BackgroundSchedulerで全ペアを定期分析
- [x] `SCAN_ENABLED` / `SCAN_INTERVAL_MINUTES` 環境変数で制御
- [x] `app/main.py` startup/shutdown イベントに統合
- [x] 1ペアのエラーで他ペアが止まらない設計
- [x] テスト13件（無効化・起動・冪等性・エラー継続）

### Phase 17：バックテストCLI ✅

- [x] `app/scripts/backtest.py` — 過去CSVで判定ルール精度を検証（注文なし）
- [x] `python -m app.scripts.backtest --symbol USD/JPY --window 500`
- [x] SL/TP到達シミュレーション・勝率・pips集計・全ペアサマリー
- [x] テスト13件（pip計算・SL/TP判定・データ不足）

### Phase 18：ドキュメント整備 ✅

- [x] `README.md` — Phase 8〜17の全機能を追記（フォルダ構成・設定・使い方）
- [x] `PROGRESS.md` — 全フェーズの実装記録・エラー記録を補完

### Phase 14：デモ注文成績統計 ✅

- [x] `get_demo_performance_stats()` — 総注文数・勝ち/負け/勝率・合計pips・平均pipsを集計
- [x] `/performance` — デモ注文成績カード（5指標）を追加
- [x] `/demo-orders` — 一覧画面の上部にサマリーバーを追加
- [x] テスト9件追加（空DB・オープン・クローズ・勝率・平均pips計算）
- [x] 全189テスト通過

### Phase 13：デモ注文の決済・損益追跡 ✅

- [x] `DemoOrderAdapter.close_trade()` — OANDA practice APIでポジション決済
- [x] `DemoOrderAdapter.get_trade_detail()` — トレード詳細・リアルタイムP&L取得
- [x] `close_demo_order()` — 決済価格・損益pipsをDBに記録
- [x] `POST /demo-close/{demo_id}` — 手動決済エンドポイント（確認チェックボックス付き）
- [x] デモ注文一覧画面に決済価格・損益(pips)・決済ボタンを追加
- [x] demo_orders テーブルへのマイグレーション（exit_price/pnl_pips/closed_at）
- [x] テスト35件（全180テスト通過）

### Phase 19：判定根拠の条件表示 ✅

- [x] `AnalysisResult.buy_conditions` / `sell_conditions`（ConditionResult リスト）
- [x] `index.html` に「判定根拠」セクション追加（条件ごとの合否アイコン・詳細テキスト）
- [x] `.condition-pass` / `.condition-fail` スタイル

### Phase 20：過去トレード学習データ ✅

- [x] `get_signal_pattern_stats()` — 日足・4H トレンドパターン別の勝率・取引数を集計
- [x] `AnalysisResult.historical_stats` フィールド追加
- [x] `index.html` に「同パターン成績」カード表示（勝率・取引数・直近結果）

### Phase 21：バックテスト可視化 ✅

- [x] `app/web/templates/backtest.html` — パラメータフォーム + 結果グリッド
- [x] `GET /backtest` — フォーム表示
- [x] `POST /backtest` — バックテスト実行・結果表示（勝率・pips集計・条件別分類）

### Phase 22：設定画面 ✅

- [x] `app/web/templates/settings.html` — スキャン間隔・通知トグル・OANDA接続確認
- [x] `GET /settings` / `POST /settings` — app_settings テーブルへの永続化
- [x] `app_settings` DB テーブル（SCAN_ENABLED / SCAN_INTERVAL_MINUTES ほか）

### Phase 23：ダッシュボード ✅

- [x] `app/web/templates/dashboard.html` — 複数通貨ペアの最新シグナル一覧
- [x] `GET /dashboard` — 全ペアを並行分析して表示
- [x] `/api/all-signals` JSON エンドポイント

### Phase 24：精度レポート ✅

- [x] `app/web/templates/report.html` — 方向別・パターン別・トレンド別の勝率表
- [x] `GET /report` — approval_history + demo_orders を集計して表示

### Phase 25：自動リフレッシュ ✅

- [x] `index.html` に 60秒ポーリング実装（`setInterval(checkSignals, POLL_MS)`）
- [x] `/api/latest-signal` エンドポイント — ページリロードなしで最新シグナルを取得
- [x] シグナル変化時のみ DOM を更新

### Phase 26：SVG 累積損益チャート ✅

- [x] `performance.html` に SVG 累積 pips ラインチャートを追加
- [x] `/api/chart-data` エンドポイント — 時系列累積 pips データを返す
- [x] ホバーツールチップ・軸ラベル・レスポンシブ対応

### Phase 27：バックテスト結果を DB 保存 ✅

- [x] `save_backtest_results()` — バックテスト結果を approval_history にシミュレーション記録として保存
- [x] `POST /backtest` 実行後に即時 DB 保存（シミュレーションフラグ付き）

### Phase 28：SVG ローソク足チャート ✅

- [x] `index.html` に SVG ローソク足チャート追加（`drawCandles()` 関数）
- [x] 陽線・陰線（緑/赤）＋ヒゲ描画
- [x] エントリー・SL・TP 水平ライン重ね表示
- [x] `/api/candles?tf=` エンドポイント — OHLCV データを JSON で返す

### Phase 29：ブラウザ通知（Web Notification API）✅

- [x] `index.html` に Notification API 実装
- [x] 初回ロード時に通知許可を要求
- [x] `checkSignals()` でシグナル変化検出時に `showNotification()` を呼び出し

### Phase 30：ローソク足チャートに MA20・MA50・BB 重ねプロット ✅

- [x] SVG チャートに MA20 ライン（青）・MA50 ライン（橙）を追加
- [x] BB 上限・下限バンド（グレー破線）を重ね描画

### Phase 31：ローソク足チャートに複数時間足タブ ✅

- [x] チャート上部に「1時間 / 4時間 / 1日足」タブボタンを追加
- [x] `data-tf` 切替で `/api/candles?tf=1h|4h|1d` を再取得・再描画
- [x] アクティブタブの `.tf-active` スタイル

---

### Phase 35：CSV エクスポート ✅

- [x] `get_history_for_export()` — ペア・シグナル・アクション・期間フィルター付き全件取得
- [x] `get_journal_for_export()` — タグ・タイプフィルター付き全件取得（approval_history JOIN）
- [x] `get_demo_orders_for_export()` — デモ注文全件取得
- [x] `GET /export/history.csv` — クエリパラメータでフィルター可能な CSV ダウンロード
- [x] `GET /export/journal.csv` — ジャーナル CSV ダウンロード
- [x] `GET /export/demo-orders.csv` — デモ注文成績 CSV ダウンロード
- [x] `history.html` / `journal.html` / `performance.html` にエクスポートバーを追加
- [x] `text/csv; charset=utf-8-sig`（Excel で文字化けしない BOM 付き UTF-8）
- [x] テスト16件（全343テスト通過）

### Phase 34：トレードジャーナル ✅

- [x] `trade_journal` DB テーブル（approval_id・notes・tags・entry_type・emotion_score）
- [x] CRUD 5関数（upsert / get_entry / get_entries / get_count）
- [x] タイプ 8種（ブレイクアウト/押し目買い/戻り売り/反発/ダマシ/反省/要検証/その他）
- [x] 感情スコア 1〜5（😰焦り〜😌完全冷静）
- [x] `history.html` にインラインジャーナルフォーム（追加ボタン→展開）
- [x] `GET /journal` / `POST /journal/{id}` ルート追加
- [x] `journal.html` — タグ・タイプ絞り込み付きジャーナル一覧ページ
- [x] タグクリックで絞り込み・「履歴で見る」リンク
- [x] 全テンプレートのナビに「ジャーナル」リンク追加
- [x] テスト16件（全327テスト通過）

### Phase 46：シグナル品質スコアリング ✅

- [x] `app/scripts/signal_quality.py` — 品質スコアリングエンジン
  - スコアバケット（high/mid/low）・RSIバケット（oversold/neutral/overbought）・トレンド一致（aligned/mixed）
  - 品質ラベル S/A/B/C/D/N/A（勝率 65%/55%/45%/35%/それ以下 / データ不足）
  - `get_signal_quality()` — 具体→抽象の段階的照合で最適なパターンを選択
  - `get_all_pattern_stats()` — 全パターン統計一覧
- [x] `app/services/market_analyzer.py` — `AnalysisResult.signal_quality` 追加
- [x] `app/web/routes.py` — `GET /api/signal-quality` と `GET /api/signal-quality/patterns` 追加
- [x] `app/web/templates/index.html` — 品質バッジ（S/A/B/C/D）をシグナルセクション直下に表示
- [x] `app/web/static/style.css` — quality-badge CSSブロック追加
- [x] `tests/test_signal_quality.py` — テスト47件（全795テスト通過）

### Phase 45：ヒートマップカレンダー ✅

- [x] `app/scripts/heatmap_calendar.py` — ヒートマップ集計エンジン
  - `HeatmapCell` dataclass（weekday/hour/trades/wins/losses/win_rate/total_pips/avg_pips）
  - `HeatmapResult` dataclass（7×24 セルマトリクス・全体勝率・評価テキスト）
  - `get_heatmap_rows()` — approval_history から closed 取引を取得
  - `build_heatmap()` — 曜日×時間帯の7×24ヒートマップを構築
  - `_assess()` — 最良/最悪の時間帯を日本語評価テキストで返す
- [x] `app/web/routes.py` — `GET /api/heatmap-calendar` エンドポイント追加
- [x] `app/web/templates/backtest.html` — ヒートマップカレンダーUIセクション追加
- [x] `tests/test_heatmap_calendar.py` — テスト48件（全748テスト通過）

### Phase 44：パラメータ感度分析 ✅

- [x] `app/scripts/sensitivity.py` — 感度分析エンジン
  - `SENSITIVITY_PARAMS` — 対応パラメータ名→ラベルの辞書（6種類）
  - `SensitivityCell` dataclass（x_val/y_val/trades/win_rate/total_pips）
  - `SensitivityResult` dataclass（param_x/param_y/base値/cells 2Dリスト）
  - `_clamp_param()` — パラメータ値を整数化・範囲クランプ
  - `run_sensitivity()` — ±10%/±20% の5×5マトリクスでバックテストを実行
  - `_assess()` — 勝率変動幅で感度（低/中/高）・改善余地を日本語評価
  - `optimizer._run_one()` と `OptimizeParams` を再利用
- [x] `app/web/routes.py` — `GET /api/sensitivity` エンドポイント追加
  - symbol / param_x / param_y / 基準パラメータ6値 / window / step_bars / future_bars 対応
  - X×Y のセルマトリクスと評価を JSON で返す
- [x] `app/web/templates/backtest.html` — 感度分析セクション追加
  - パラメータフォーム（通貨ペア・X軸・Y軸・基準MA・ウィンドウ）
  - 勝率ヒートマップテーブル（緑→赤グラデーション・基準セル太枠）
  - 合計損益マトリクステーブル（色分け）
- [x] `tests/test_sensitivity.py` — テスト35件（全700テスト通過）

### Phase 43：モンテカルロ分析 ✅

- [x] `app/scripts/monte_carlo.py` — モンテカルロ分析エンジン
  - `PercentileStats` dataclass（p5/p25/p50/p75/p95/mean/min/max）
  - `MonteCarloResult` dataclass（n_trades/ruin_probability/profit_probability/win_rate_ci）
  - `_max_drawdown()` — 累積損益から最大ドローダウンを計算
  - `_percentile_stats()` — パーセンタイル統計を計算
  - `_wilson_ci()` — 勝率の95%信頼区間（Wilson score法）
  - `run_monte_carlo()` — N回シャッフルして期待損益・DD・破産確率の分布を算出
  - `get_pnl_pips_from_db()` — DBからクローズ済み損益リストを取得（シンボル・ソース絞り込み対応）
  - `_assess()` — 破産リスク・収益期待・中央値損益を日本語評価
- [x] `app/web/routes.py` — `GET /api/monte-carlo` エンドポイント追加
  - symbol / n_simulations（10〜5000上限）/ ruin_threshold / data_source パラメータ対応
  - パーセンタイル統計・確率指標・勝率CIを JSON で返す
- [x] `app/web/templates/backtest.html` — モンテカルロ分析セクション追加
  - パラメータフォーム（通貨ペア・回数・破産閾値・データソース）
  - 破産確率・収益期待確率・勝率CI・中央値損益カード
  - 最終損益/最大DD パーセンタイル比較テーブル
  - 元データ統計グリッド
- [x] `tests/test_monte_carlo.py` — テスト53件（全665テスト通過）

### Phase 42：ウォークフォワード分析 ✅

- [x] `app/scripts/walk_forward.py` — WF分析エンジン
  - `WFWindow` dataclass（IS/OOS バー範囲・取引数・勝率・pips・過学習スコア・ロバストネス比）
  - `WalkForwardResult` dataclass（全ウィンドウ集計・OOS合算・総合評価）
  - `_run_slice()` — バー範囲指定でバックテストを実行して集計
  - `_fill_window_stats()` — 勝率・平均pips・過学習スコア・ロバストネス比を計算
  - `run_walk_forward()` — n_windows個に分割してIS/OOS検証を実行
  - `_assess()` — 過学習リスク・ロバストネス・OOS勝率を日本語で評価
- [x] `app/web/routes.py` — `GET /api/walk-forward` エンドポイント追加
  - 通貨ペア・ウィンドウ数・IS比率・バー数・ステップ・未来バー数をパラメータ受付
  - 全ウィンドウ詳細 + 集計値 + 総合評価を JSON で返す
- [x] `app/web/templates/backtest.html` — WF分析セクションを追加
  - パラメータフォーム（6項目）
  - 総合評価カード（過学習スコア・ロバストネス比を色分け表示）
  - OOS合算カード4枚（総取引数・合算勝率・合算pips・平均pips）
  - ウィンドウ別IS/OOS比較テーブル（色分け：低/中/高リスク）
  - 非同期フェッチ（`/api/walk-forward`）＋動的レンダリング
- [x] `tests/test_walk_forward.py` — テスト34件（全612テスト通過）

### Phase 41：Web Push通知 ✅

- [x] `app/database/models.py` — `push_subscriptions` テーブル追加（endpoint UNIQUE）
- [x] `app/database/db.py` — `init_db()` にテーブル作成追加
- [x] `app/database/repository.py` — Push CRUD 4関数 + `get_or_create_vapid_keys` 追加
  - `save_push_subscription` / `delete_push_subscription` / `get_push_subscriptions` / `count_push_subscriptions`
  - `get_or_create_vapid_keys` — `set_setting()` を直接呼んで永続化
- [x] `app/services/push_sender.py` — VAPID EC P-256 鍵生成・JWT 署名・httpx 非同期送信
  - `generate_vapid_keys` / `make_vapid_jwt` / `send_push_notification` / `send_push_to_all`
- [x] `app/web/routes.py` — Push API 4ルート追加 + index で BUY/SELL 時に `asyncio.create_task`
  - `GET /api/push/vapid-public-key` / `POST /api/push/subscribe` / `POST /api/push/unsubscribe` / `POST /api/push/test`
- [x] `app/web/static/sw.js` — `push` / `notificationclick` ハンドラ追加
- [x] `app/web/templates/settings.html` — プッシュ通知セクション追加（有効化・無効化・テスト送信ボタン）
- [x] `cffi` パッケージを `pip install` して `cryptography` の Rust パニックを解消
- [x] テスト34件（全578テスト通過）

### Phase 40：PWA対応 ✅

- [x] `app/web/static/manifest.json` — name / short_name / start_url / display / icons / shortcuts 設定
- [x] `app/web/static/sw.js` — Service Worker（Static Cache First / HTML Network First / API Network Only）
- [x] `create_icons.py` — stdlib のみで 192×192 / 512×512 PNG アイコンを生成するスクリプト
- [x] `app/web/static/icons/icon-192.png` / `icon-512.png` — チャートモチーフの PNG アイコン
- [x] 全14テンプレートの `<head>` に manifest リンク・Apple 対応 meta・apple-touch-icon 追加
- [x] 全14テンプレートの `</body>` 直前に SW 登録スクリプト追加
- [x] テスト87件（全544テスト通過）

### Phase 39：経済指標カレンダー ✅

- [x] `economic_events` DB テーブル（id / event_dt / currency / importance / event_name / note）
- [x] 重要度 3段階：HIGH（★★★）/ MEDIUM（★★☆）/ LOW（★☆☆）
- [x] CRUD 関数：`create_economic_event` / `get_economic_events` / `count_economic_events` / `delete_economic_event`
- [x] `get_upcoming_warning_events()` — 直近N時間以内の HIGH/MEDIUM イベントを返す
- [x] `has_upcoming_warning()` — 警戒中かどうかを bool で返す
- [x] `GET /calendar` / `POST /calendar` / `POST /calendar/{id}/delete` ルート追加
- [x] `GET /api/upcoming-events` — 直近イベントをJSON返却（has_warning フラグ付き）
- [x] `app/web/templates/calendar.html` — 登録フォーム・フィルター・一覧・重要度説明
- [x] `index.html` — 直近24h以内の HIGH/MEDIUM イベントを警戒バッジで表示
- [x] 全テンプレートのナビに「指標」リンク追加
- [x] `app/web/static/style.css` — `econ-imp-badge` / `alert-warning` CSSブロック追加
- [x] テスト34件（全457テスト通過）

### Phase 38：チャート表示（Chart.js） ✅

- [x] `GET /charts` — チャートダッシュボードページ（symbol/limit クエリ対応）
- [x] `GET /api/chart-stats` — 月次成績・BUY/SELL別勝率をJSONで返す新規エンドポイント
- [x] Chart.js 4.4.0（CDN）でブラウザ描画、バックエンド変更最小
- [x] エクイティカーブ（累積pips折れ線、勝ち緑/負け赤の点カラー）
- [x] 月次成績棒グラフ（勝ち/負け積み上げ + 合計pips折れ線 複合グラフ）
- [x] 月次勝率ラインチャート
- [x] BUY/SELL別勝率・平均pips棒グラフ（複合）
- [x] 通貨ペア・件数フィルター（非同期再読み込み）
- [x] `app/web/static/style.css` — `.chart-container` / `.chart-grid-2col` CSS追加
- [x] 全テンプレートのナビに「チャート」リンク追加
- [x] `tests/conftest.py` — HTTPテスト用DB初期化フィクスチャ（autouse session scope）
- [x] テスト15件（全423テスト通過）

### Phase 37：通貨相関マトリクス ✅

- [x] `app/services/correlation.py` — 日次リターンのピアソン相関係数計算（注文なし・分析のみ）
- [x] `CorrelationMatrix` dataclass（symbols / matrix / lookback_days / data_points）
- [x] `to_css_class()` — 相関値からヒートマップ用CSSクラスを返す（5段階）
- [x] `calculate_correlation_matrix()` — 全ペアの相関マトリクスを計算（共通インデックスで算出）
- [x] `correlation_label()` — 相関値を日本語ラベルに変換
- [x] 期間プリセット4種：1ヶ月(21日) / 3ヶ月(63日) / 6ヶ月(126日) / 1年(252日)
- [x] `GET /correlation` ルート追加（lookbackクエリパラメータ対応）
- [x] `app/web/templates/correlation.html` — ヒートマップ・凡例・データ点数カード
- [x] 全テンプレートのナビに「相関」リンク追加
- [x] `app/web/static/style.css` — ヒートマップCSSブロック追加（5段階カラースケール）
- [x] テスト34件（全408テスト通過）

### Phase 36：戦略パラメータ最適化 ✅

- [x] `app/scripts/optimizer.py` — グリッドサーチ最適化エンジン（注文なし・分析専用）
- [x] `OptimizeParams` dataclass（ma_short / ma_long / rsi_buy_max / rsi_buy_min / rsi_sell_min / rsi_sell_max）
- [x] `OptimizeResult` dataclass（wins / losses / open_count / total_pips / win_rate / avg_pips / score）
- [x] `_analyze_with_params()` — 本番 rules.py を一切変更しない最適化専用シグナル判定
- [x] `_run_one()` — ウォークフォワード型ミニバックテスト（window/step/future_bars 設定可）
- [x] `optimize()` — グリッドサーチ本体（short < long フィルター、最大200組み合わせ上限）
- [x] 最適化メトリック 3種：`win_rate` / `total_pips` / `avg_pips`
- [x] CLI 対応（`python -m app.scripts.optimizer --symbol USD/JPY --metric win_rate`）
- [x] `GET /optimizer` / `POST /optimizer` ルート追加
- [x] `app/web/templates/optimizer.html` — グリッドサーチフォーム・推奨パラメータカード・結果テーブル
- [x] 全テンプレートのナビに「最適化」リンク追加
- [x] テスト31件（全374テスト通過）

### Phase 33：カスタムアラート設定 ✅

- [x] `alerts` DB テーブル（symbol / label / condition_type / condition_value / cooldown_minutes / last_triggered_at）
- [x] 条件タイプ 5種：`signal_type` / `confluence_min` / `rsi_below` / `rsi_above` / `score_min`
- [x] `app/services/alert_evaluator.py` — 条件評価エンジン（クールダウン・発火・通知）
- [x] `app/database/repository.py` — CRUD（create / get / toggle / delete / update_triggered）
- [x] `app/services/scheduler.py` — スキャン時に `evaluate_alerts()` を呼び出し
- [x] `GET /alerts` / `POST /alerts` / `POST /alerts/{id}/toggle` / `POST /alerts/{id}/delete`
- [x] `app/web/templates/alerts.html` — 作成フォーム・一覧・条件説明テーブル
- [x] 全テンプレートのナビに「アラート」リンク追加
- [x] テスト22件（全311テスト通過）

### Phase 32：マルチタイムフレーム判定強化 ✅

- [x] `ConfluenceResult` dataclass（daily/4h/1h 各TFの方向一致フラグ）
- [x] `calculate_timeframe_confluence()` — 方向ごとの一致度スコア（0〜3）を計算
- [x] `SignalResult.confluence` フィールド追加（analyze_signal()で自動計算）
- [x] `AnalysisResult.confluence` フィールド追加（market_analyzer.pyで伝播）
- [x] `index.html` にTFバッジパネル追加（日足/4H/1H の一致バッジ＋スコアラベル）
- [x] CSSクラス（confluence-strong/medium/weak, tf-badge agree/disagree）追加
- [x] テスト10件（全289テスト通過）

---

## 絶対に実装しないこと

- 本番注文の自動発注
- 損切りなし戦略
- ナンピン・マーチンゲール戦略
- 人間承認なしの発注
- ライブ口座への直接接続
