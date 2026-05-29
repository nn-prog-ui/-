# Phase 76: Railway 本番デプロイ用 Dockerfile
# ============================================================
# セキュリティ方針:
#   - TRADING_MODE=demo_only を強制（live への変更は起動時エラー）
#   - 本番注文機能は一切含まない
#   - APIキーはビルド時に焼き込まない（Railway Variables で注入）
# ============================================================

FROM python:3.11-slim AS base

# タイムゾーン設定（ログ・定期スキャンの時刻表示用）
ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 作業ディレクトリ
WORKDIR /app

# システム依存パッケージ（pandas/numpy のビルドに必要な場合を考慮）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# ── 依存パッケージのインストール ──────────────────────────────────────────
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── 本番イメージ ──────────────────────────────────────────────────────────
FROM base AS production

# deps ステージからインストール済みパッケージをコピー
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# アプリケーションコードをコピー
COPY app/ ./app/
COPY data/ ./data/

# データ・ログディレクトリを作成（Railway ボリュームのマウント先）
RUN mkdir -p /app/data/raw /app/data/processed /app/logs

# Railway ボリュームがマウントされる /app/data を永続化対象として明示
# （実際のボリューム設定は Railway ダッシュボードで行う）
VOLUME ["/app/data"]

# ポート公開（Railway は PORT 環境変数で上書きするため参考値）
EXPOSE 8000

# 安全ロック: TRADING_MODE は必ず demo_only（起動時にアプリ側でも検証）
ENV TRADING_MODE=demo_only
ENV APP_ENV=production
ENV DB_PATH=/app/data/fx_monitor.db
ENV DATA_DIR=/app/data/raw
ENV PROCESSED_DIR=/app/data/processed

# 起動コマンド（railway.toml の startCommand が優先される）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
