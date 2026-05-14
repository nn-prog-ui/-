# AI FX市場監視システム

**重要：このシステムは分析・通知・承認履歴保存のみを行います。自動売買・本番注文機能は実装していません。**

---

## 概要

USD/JPY・EUR/USD・GBP/USD・EUR/JPYを監視し、テクニカル指標に基づいて「買い候補」「売り候補」「見送り」を根拠付きで提示するWebダッシュボードです。最終判断は必ず人間が行います。

- 承認ボタンを押しても注文は発生しません（SQLiteへの履歴保存のみ）
- OANDA practiceデモ口座への注文は別途 `/demo-trade` から手動で実行
- 本番注文APIは実装していません（将来も実装しない）
- APSchedulerで設定した間隔の自動スキャン・通知に対応

---

## システム構成

```
CSVデータ / OANDA API → market_analyzer.py → FastAPI Web + SQLite
                                           ↓
                              AI Commentary (Claude / OpenAI / モック)
                                           ↓
                              通知 (Gmail SMTP) + 定期スキャン (APScheduler)
```

## フォルダ構成

```
ai-fx-monitor/
├── app/
│   ├── main.py                      # FastAPIアプリ起動・スケジューラー管理
│   ├── config.py                    # 設定管理
│   ├── data/
│   │   ├── loader.py                # CSV読み込み
│   │   ├── resampler.py             # 時間足変換
│   │   ├── price_source.py          # データソース切替（CSV / OANDA）
│   │   └── oanda_adapter.py         # OANDA API価格取得アダプター
│   ├── indicators/
│   │   ├── moving_average.py        # 20MA / 75MA
│   │   ├── rsi.py                   # RSI（14期間）
│   │   ├── atr.py                   # ATR（14期間）・直近高安値
│   │   ├── bollinger_bands.py       # ボリンジャーバンド（BB20±2σ）
│   │   ├── macd.py                  # MACD（12-26-9）
│   │   └── currency_strength.py     # 通貨強弱（日足モメンタム）
│   ├── strategy/
│   │   ├── rules.py                 # 売買判定ルール（7条件）
│   │   ├── scoring.py               # スコアリング
│   │   └── risk.py                  # 損切り・利確・RR計算
│   ├── services/
│   │   ├── market_analyzer.py       # 市場分析統合
│   │   ├── ai_commentary.py         # AIコメント（Claude / OpenAI / モック）
│   │   ├── economic_calendar.py     # 経済指標カレンダー
│   │   ├── notification.py          # Gmail SMTP通知
│   │   ├── demo_order.py            # デモ注文アダプター（OANDA practice専用）
│   │   └── scheduler.py             # 定期スキャン（APScheduler）
│   ├── scripts/
│   │   └── backtest.py              # バックテストCLI
│   ├── database/
│   │   ├── db.py                    # DB接続
│   │   ├── models.py                # テーブル定義・マイグレーション
│   │   └── repository.py            # CRUD操作
│   └── web/
│       ├── routes.py                # ルーティング
│       ├── templates/
│       │   ├── index.html           # メイン判定画面
│       │   ├── history.html         # 承認履歴画面
│       │   ├── performance.html     # 成績・統計画面
│       │   └── demo_trade.html      # デモ注文・履歴画面
│       └── static/
│           └── style.css            # スマホ対応CSS
├── data/
│   ├── raw/                         # 生CSVデータ置き場
│   └── processed/                   # 加工済みデータ
├── tests/                           # pytest テスト（195件）
├── scripts/
│   └── generate_sample_csv.py       # サンプルCSV生成
├── .env.example
├── .gitignore
├── requirements.txt
├── ROADMAP.md
├── PROGRESS.md
└── CLAUDE.md
```

---

## インストール方法

### 1. 前提条件

- Python 3.11 以上
- pip

### 2. 仮想環境を作成・有効化

```bash
cd ai-fx-monitor
python -m venv venv
source venv/bin/activate       # Mac/Linux
# venv\Scripts\activate        # Windows
```

### 3. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

### 4. 環境変数を設定

```bash
cp .env.example .env
# .env を編集（最初はデフォルトのままでOK）
```

---

## 起動方法

### サンプルCSVを生成（初回のみ）

```bash
python scripts/generate_sample_csv.py
```

### サーバー起動

```bash
cd ai-fx-monitor
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### ブラウザでアクセス

| URL | 説明 |
|-----|------|
| http://localhost:8000/ | メイン判定画面 |
| http://localhost:8000/history | 承認履歴 |
| http://localhost:8000/performance | 成績・統計 |
| http://localhost:8000/demo-orders | デモ注文履歴 |
| http://localhost:8000/docs | API仕様書 |

---

## CSVデータの置き方

`data/raw/` フォルダに以下の形式のCSVファイルを置いてください。

| ファイル名 | 通貨ペア |
|------------|----------|
| USDJPY_1h.csv | USD/JPY |
| EURUSD_1h.csv | EUR/USD |
| GBPUSD_1h.csv | GBP/USD |
| EURJPY_1h.csv | EUR/JPY |

### CSVフォーマット

```csv
datetime,open,high,low,close,volume
2024-01-01 00:00:00,140.100,140.250,140.000,140.180,1000
2024-01-01 01:00:00,140.180,140.320,140.100,140.280,1200
```

> CSVがない場合、システムは自動的にダミーデータで動作します。

---

## テスト方法

```bash
cd ai-fx-monitor
python -m pytest tests/ -v
```

---

## バックテスト

過去のCSVデータで判定ルールの精度を検証します（注文は一切発生しません）。

```bash
# 全通貨ペア（デフォルト設定）
python -m app.scripts.backtest

# ペア指定・詳細設定
python -m app.scripts.backtest --symbol USD/JPY --window 500 --step 24 --future 100
```

| オプション | デフォルト | 説明 |
|----------|---------|------|
| `--symbol` | 全ペア | 通貨ペア指定 |
| `--window` | 500 | 判定に使う直近バー数 |
| `--step` | 24 | 判定間隔（本数） |
| `--future` | 100 | SL/TP到達チェック用未来バー数 |

> バックテスト結果は過去データのシミュレーションです。将来の成績を保証するものではありません。

---

## OANDA API連携（オプション）

`.env` に以下を設定するとリアルタイム価格でスキャンできます。

```env
DATA_SOURCE=oanda
OANDA_API_KEY=your_practice_api_key_here
OANDA_ACCOUNT_ID=your_account_id_here
OANDA_ENVIRONMENT=practice   # ← 必ずpractice（デモ）のまま
```

---

## AIコメント連携（オプション）

`.env` にAPIキーを設定すると自動的に有効になります。優先順位: Claude > OpenAI > モック

```env
# Claude API（推奨）
ANTHROPIC_API_KEY=your_anthropic_api_key_here
CLAUDE_MODEL=claude-haiku-4-5   # 省略可

# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini        # 省略可
```

---

## 定期スキャン設定（オプション）

サーバー起動中に自動で全ペアをスキャンし、条件が揃ったときにメール通知します。

```env
SCAN_ENABLED=true           # 有効/無効（デフォルト: true）
SCAN_INTERVAL_MINUTES=60    # スキャン間隔（デフォルト: 60分）
```

---

## Gmail通知設定（オプション）

```env
EMAIL_FROM=your_gmail@gmail.com
EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   # Gmailアプリパスワード（16文字）
EMAIL_TO=your_gmail@gmail.com
NOTIFY_ON_BUY=true
NOTIFY_ON_SELL=true
NOTIFY_ON_SKIP=false
NOTIFY_MIN_SCORE=0
```

> Gmailアプリパスワードの取得: Googleアカウント → セキュリティ → 2段階認証ON → アプリパスワード

---

## 画面の見方

### メイン判定画面

| 項目 | 説明 |
|------|------|
| 現在価格 | 直近の終値 |
| 判定 | 買い候補 / 売り候補 / 見送り |
| スコア | -7〜+7（正=買い方向） |
| 日足/4時間足/1時間足 | 各時間足のMAトレンド |
| RSI | 70超=買われすぎ、30未満=売られすぎ |
| ATR | ボラティリティ指標 |
| ボリンジャーバンド | BB20±2σ（1時間足） |
| MACD | 12-26-9（1時間足） |
| 通貨強弱 | 日足モメンタムスコア |
| エントリー/損切り/利確/RR | リスク管理情報（RR1.5以上が条件） |
| 重要指標警戒 | 経済指標前後60分フラグ |
| AIコメント | 判定の補足説明（判定変更なし） |

### 承認ボタン（注文は発生しません）

| ボタン | 動作 |
|--------|------|
| 買い承認 | BUYシグナル時のみ有効。SQLiteに履歴を記録 |
| 売り承認 | SELLシグナル時のみ有効。SQLiteに履歴を記録 |
| 見送り | 常に有効。SQLiteに履歴を記録 |

### デモ注文（OANDA設定時のみ）

承認履歴から「デモ注文」ボタンを押すと、2段階確認フロー経由でOANDA practiceデモ口座に注文を送信できます。本番資金は一切使われません。

---

## 安全上の注意

1. このシステムは承認履歴の記録のみを行います（自動注文なし）
2. 本番口座には接続していません
3. APIキーは `.env` に記載し、Gitには絶対にコミットしないでください
4. FX取引には元本割れリスクがあります
5. このシステムの判定は投資アドバイスではありません
6. `TRADING_MODE=demo_only` は絶対に変更しないでください

---

## ライセンス

個人利用・学習目的のみ。金融取引への使用は自己責任です。
