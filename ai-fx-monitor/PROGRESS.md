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
- `app/strategy/rules.py`：買い/売り/見送り判定ロジック
- `app/strategy/scoring.py`：スコア計算
- `app/strategy/risk.py`：損切り・利確・RR計算
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

#### Phase 6：AIコメント完了（モック）
- `app/services/ai_commentary.py`：ルールベースのコメント生成
- 将来API接続可能な設計

### 既知の制限事項

- リアルタイム価格取得未実装（CSVデータのみ）
- OANDA API未接続
- OpenAI/Claude API未接続
- 通知機能未実装

### 次の優先タスク

1. サンプルCSVでの動作確認
2. テスト全件パス確認
3. スマホブラウザでのレイアウト確認
4. OANDA APIアダプターの設計検討

---

## エラー記録

（エラーが発生した場合、ここに記録する）

---

## 変更履歴

| 日付 | 変更内容 | ファイル |
|------|----------|----------|
| 2026-05-12 | 初期MVP実装 | 全ファイル新規作成 |
