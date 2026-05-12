# AI FX市場監視システム（MVP）

**重要：このシステムは分析・通知・承認履歴保存のみを行います。自動売買・本番注文機能は実装していません。**

---

## 概要

USD/JPYを中心にFX市場を監視し、テクニカル指標に基づいて「買い候補」「売り候補」「見送り」を根拠付きで提示するWebダッシュボードです。最終判断は必ず人間が行います。

- 承認ボタンを押しても注文は発生しません（SQLiteへの履歴保存のみ）
- 本番注文APIは実装していません
- 将来の拡張に備えた設計になっています

---

## システム構成

```
Python監視エンジン + FastAPI Webダッシュボード + SQLite + CSVデータ
```

## フォルダ構成

```
ai-fx-monitor/
├── app/
│   ├── main.py                  # FastAPIアプリ起動
│   ├── config.py                # 設定管理
│   ├── data/
│   │   ├── loader.py            # CSV読み込み
│   │   └── resampler.py         # 時間足変換
│   ├── indicators/
│   │   ├── moving_average.py    # 20MA / 75MA
│   │   ├── rsi.py               # RSI
│   │   └── atr.py               # ATR
│   ├── strategy/
│   │   ├── rules.py             # 売買判定ルール
│   │   ├── scoring.py           # スコアリング
│   │   └── risk.py              # リスク管理
│   ├── services/
│   │   ├── market_analyzer.py   # 市場分析統合
│   │   ├── ai_commentary.py     # AIコメント生成（モック）
│   │   └── economic_calendar.py # 経済指標カレンダー
│   ├── database/
│   │   ├── db.py                # DB接続
│   │   ├── models.py            # データモデル
│   │   └── repository.py        # CRUD操作
│   └── web/
│       ├── routes.py            # ルーティング
│       ├── templates/
│       │   ├── index.html       # メイン判定画面
│       │   └── history.html     # 承認履歴画面
│       └── static/
│           └── style.css        # スマホ対応CSS
├── data/
│   ├── raw/                     # 生CSVデータ置き場
│   └── processed/               # 加工済みデータ
├── tests/
│   ├── test_indicators.py
│   ├── test_rules.py
│   └── test_risk.py
├── scripts/
│   └── generate_sample_csv.py   # サンプルCSV生成
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

- メイン画面：http://localhost:8000/
- 承認履歴：http://localhost:8000/history
- API docs：http://localhost:8000/docs

---

## CSVデータの置き方

`data/raw/` フォルダに以下の形式のCSVファイルを置いてください。

```
ファイル名例: USDJPY_1h.csv（1時間足）
```

### CSVフォーマット

```csv
datetime,open,high,low,close,volume
2024-01-01 00:00:00,140.100,140.250,140.000,140.180,1000
2024-01-01 01:00:00,140.180,140.320,140.100,140.280,1200
```

| カラム | 型 | 説明 |
|--------|-----|------|
| datetime | YYYY-MM-DD HH:MM:SS | 日時（UTC推奨） |
| open | float | 始値 |
| high | float | 高値 |
| low | float | 安値 |
| close | float | 終値 |
| volume | int | 出来高（省略可） |

> CSVがない場合、システムは自動的にダミーデータで動作します。

---

## テスト方法

```bash
cd ai-fx-monitor
python -m pytest tests/ -v
```

---

## 画面の見方

### メイン判定画面

| 項目 | 説明 |
|------|------|
| 現在価格 | 直近の終値 |
| 判定 | 買い候補 / 売り候補 / 見送り |
| スコア | -7〜+7のスコア（正=買い方向） |
| 日足/4時間足/1時間足 | 各時間足の状態 |
| RSI | 相対力指数（70超=買われすぎ、30未満=売られすぎ） |
| ATR | 平均真のレンジ（ボラティリティ指標） |
| エントリー候補 | 推奨エントリー価格 |
| 損切り | 推奨損切り価格 |
| 利確 | 推奨利確価格 |
| リスクリワード | 損益比率（1.5以上が条件） |
| 重要指標警戒 | 経済指標前後60分フラグ |
| AIコメント | 判定の根拠説明 |

### 承認ボタン（注文は発生しません）

| ボタン | 動作 |
|--------|------|
| 買い承認 | 買い承認をSQLiteに記録 |
| 売り承認 | 売り承認をSQLiteに記録 |
| 見送り | 見送りをSQLiteに記録 |

---

## 今後の拡張予定

ROADMAP.md を参照してください。

---

## 安全上の注意

1. このシステムは承認履歴の記録のみを行います
2. 本番口座には接続していません
3. APIキーは `.env` に記載し、Gitには絶対にコミットしないでください
4. FX取引には元本割れリスクがあります
5. このシステムの判定は投資アドバイスではありません

---

## ライセンス

個人利用・学習目的のみ。金融取引への使用は自己責任です。
