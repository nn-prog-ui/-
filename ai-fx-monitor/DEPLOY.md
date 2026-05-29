# Railway デプロイガイド（Phase 76）

> **重要**: このシステムは FX 市場の**分析・通知のみ**を行います。自動注文機能はありません。

---

## 1. 前提条件

- [Railway](https://railway.app) アカウント（無料プランで動作）
- GitHub リポジトリがプッシュ済みであること

---

## 2. デプロイ手順

### Step 1: Railway プロジェクト作成

1. Railway ダッシュボード → **New Project**
2. **Deploy from GitHub repo** を選択
3. リポジトリを選択

### Step 2: 永続ボリュームの追加（必須）

SQLite DB と CSV データを保持するためにボリュームが必要です。

1. プロジェクト → **+ Add** → **Volume**
2. 設定:
   - **Mount Path**: `/app/data`
   - サイズ: 1GB（無料枠内）

### Step 3: 環境変数の設定

Railway ダッシュボード → **Variables** タブで以下を設定:

```
# 必須
APP_ENV=production
TRADING_MODE=demo_only          ← 絶対に変更しないこと
DB_PATH=/app/data/fx_monitor.db
DATA_DIR=/app/data/raw
PROCESSED_DIR=/app/data/processed

# セキュリティ（本番では必ず設定）
AUTH_USERNAME=admin
AUTH_PASSWORD=<強力なパスワード>

# AI分析（オプション）
ANTHROPIC_API_KEY=<your_key>
# OPENAI_API_KEY=<your_key>

# メール通知（オプション）
# EMAIL_FROM=your_gmail@gmail.com
# EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
# EMAIL_TO=your_gmail@gmail.com
# NOTIFY_ON_BUY=true
# NOTIFY_ON_SELL=true
# NOTIFY_GEO_ALERT=true
```

### Step 4: デプロイ実行

環境変数設定後、Railway が自動でビルド・デプロイを開始します。

---

## 3. 初回起動の動作

起動時に自動で以下が実行されます（`app/scripts/startup_check.py`）:

1. `/app/data/raw/` ディレクトリを作成
2. CSV データファイルが存在しない場合は**ダミーデータを自動生成**
3. SQLite DB を初期化
4. 定期スキャンスケジューラーを起動

---

## 4. ヘルスチェック確認

デプロイ後、以下にアクセスして確認:

```
https://<your-app>.railway.app/health
```

正常なレスポンス例:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "app_env": "production",
  "trading_mode": "demo_only",
  "db": { "ok": true, "records": 0 },
  "csv_data": {
    "USD/JPY": true,
    "EUR/USD": true,
    "GBP/USD": true,
    "EUR/JPY": true
  }
}
```

---

## 5. OANDA リアルタイム価格（オプション）

デモ口座でリアルタイム価格を使う場合（CSV のダミーデータではなく）:

```
DATA_SOURCE=oanda
OANDA_API_KEY=<practice_api_key>
OANDA_ACCOUNT_ID=<account_id>
OANDA_ENVIRONMENT=practice       ← 必ず practice のまま
```

> ⚠️ `OANDA_ENVIRONMENT=live` に設定すると起動時エラーになります（安全ロック）。

---

## 6. トラブルシューティング

| 問題 | 対処 |
|------|------|
| ヘルスチェックが `degraded` | DB ファイルのパス確認（ボリュームがマウントされているか） |
| ページ表示が遅い | Railway の無料プランは CPU 制限あり。有料プランで改善 |
| メール通知が届かない | Gmail アプリパスワードが正しいか確認 |
| CSV データなし表示 | ボリューム設定後に一度再デプロイ（ダミーデータが生成される） |

---

## 7. セキュリティチェックリスト

- [ ] `AUTH_USERNAME` と `AUTH_PASSWORD` を設定した
- [ ] `TRADING_MODE=demo_only` のまま（変更しない）
- [ ] `OANDA_ENVIRONMENT=practice` のまま（変更しない）
- [ ] API キーをコードにハードコードしていない
- [ ] `.env` ファイルを Git にコミットしていない

---

*AI FX市場監視システム — 分析・通知のみ / 本番注文機能なし*
