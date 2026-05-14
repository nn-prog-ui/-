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

---

## 絶対に実装しないこと

- 本番注文の自動発注
- 損切りなし戦略
- ナンピン・マーチンゲール戦略
- 人間承認なしの発注
- ライブ口座への直接接続
