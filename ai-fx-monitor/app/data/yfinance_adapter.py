"""yfinance 価格データアダプター（Phase 84）

Yahoo Finance から FX の OHLC データを取得する。
口座不要・無料・APIキー不要。

注意: Yahoo Finance は非公式 API のため、仕様変更の可能性がある。
その場合は DATA_SOURCE=csv（ダミー）に自動フォールバックする。

使い方:
    .env に DATA_SOURCE=yfinance を設定するだけ。
    インストール: pip install yfinance
"""
from __future__ import annotations

import logging
import time

import pandas as pd

logger = logging.getLogger(__name__)

# ── シンボルマッピング ─────────────────────────────────────────────────────
# このシステムの表記 → Yahoo Finance のティッカー
_YF_SYMBOL_MAP: dict[str, str] = {
    "USD/JPY": "JPY=X",
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "EUR/JPY": "EURJPY=X",
    "AUD/JPY": "AUDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "EUR/GBP": "EURGBP=X",
    "GBP/JPY": "GBPJPY=X",
}

# ── キャッシュ（Yahoo Finance への過剰リクエストを防ぐ） ────────────────────
# symbol → (取得時刻, DataFrame)
_ohlcv_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_price_cache: dict[str, tuple[float, dict]] = {}
_OHLCV_TTL = 3600   # 1時間（1H足データは1時間ごとに更新）
_PRICE_TTL = 300    # 5分（ライブ価格ポーリング用）


def get_yf_symbol(symbol: str) -> str:
    """通貨ペア表記を Yahoo Finance シンボルに変換する。

    例: "USD/JPY" → "JPY=X", "EUR/USD" → "EURUSD=X"
    """
    return _YF_SYMBOL_MAP.get(symbol, symbol.replace("/", "") + "=X")


def fetch_ohlcv(
    symbol: str,
    period: str = "6mo",
    interval: str = "1h",
    use_cache: bool = True,
) -> pd.DataFrame:
    """Yahoo Finance から OHLCV データを取得する。

    Args:
        symbol: 通貨ペア（例: "USD/JPY"）
        period: 取得期間（例: "6mo", "1y", "2y"）
        interval: 足の種類（例: "1h", "1d"）
        use_cache: True の場合、1時間以内のデータはキャッシュを返す

    Returns:
        DataFrame（index=datetime, columns=[open, high, low, close, volume]）
        取得失敗時は空の DataFrame
    """
    # キャッシュ確認（symbol + interval でキーを作成）
    cache_key = f"{symbol}:{interval}"
    if use_cache and cache_key in _ohlcv_cache:
        cached_time, cached_df = _ohlcv_cache[cache_key]
        if time.time() - cached_time < _OHLCV_TTL and not cached_df.empty:
            logger.debug("yfinance キャッシュ使用: %s", cache_key)
            return cached_df

    try:
        import yfinance as yf  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "yfinance がインストールされていません。\n"
            "pip install yfinance を実行してください。"
        ) from exc

    yf_symbol = get_yf_symbol(symbol)
    logger.info(
        "yfinance データ取得中: %s → %s (period=%s, interval=%s)",
        symbol, yf_symbol, period, interval,
    )

    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)

        if df.empty:
            logger.warning("yfinance: データが空でした: %s (%s)", symbol, yf_symbol)
            return pd.DataFrame()

        df = _normalize_df(df)
        logger.info("yfinance 取得完了: %s %d本", symbol, len(df))

        # キャッシュ保存
        _ohlcv_cache[cache_key] = (time.time(), df)
        return df

    except Exception as exc:
        logger.error("yfinance 取得エラー: %s → %s", symbol, exc)
        return pd.DataFrame()


def fetch_latest_price(symbol: str, use_cache: bool = True) -> dict | None:
    """最新価格と前回価格を取得する（30秒ポーリング用）。

    Args:
        symbol: 通貨ペア（例: "USD/JPY"）
        use_cache: True の場合、5分以内のデータはキャッシュを返す

    Returns:
        {price, prev_price, change, change_pct} または None
    """
    # キャッシュ確認
    if use_cache and symbol in _price_cache:
        cached_time, cached_data = _price_cache[symbol]
        if time.time() - cached_time < _PRICE_TTL:
            logger.debug("yfinance 価格キャッシュ使用: %s", symbol)
            return cached_data

    # 直近5日分の1時間足を取得（軽量）
    df = fetch_ohlcv(symbol, period="5d", interval="1h", use_cache=use_cache)
    if df.empty or len(df) < 2:
        return None

    price = round(float(df["close"].iloc[-1]), 5)
    prev  = round(float(df["close"].iloc[-2]), 5)
    chg   = round(price - prev, 5)
    chg_pct = round(chg / prev * 100, 4) if prev else None

    result = {
        "price":      price,
        "prev_price": prev,
        "change":     chg,
        "change_pct": chg_pct,
    }
    _price_cache[symbol] = (time.time(), result)
    return result


def clear_cache() -> None:
    """キャッシュをクリアする（テスト・デバッグ用）。"""
    _ohlcv_cache.clear()
    _price_cache.clear()


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance の DataFrame をこのシステムの形式に変換する。

    - カラム名を小文字に統一（Open→open など）
    - タイムゾーン情報を除去（tz-naive に）
    - 必要なカラムのみ残す
    - NaN を除去
    - 昇順ソート
    """
    # カラム名を小文字に
    col_map = {
        "Open":   "open",
        "High":   "high",
        "Low":    "low",
        "Close":  "close",
        "Volume": "volume",
    }
    df = df.rename(columns=col_map)

    # 必要なカラムのみ（存在するもの）
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep].copy()

    # volume がなければ 0 で埋める
    if "volume" not in df.columns:
        df["volume"] = 0

    # タイムゾーン除去
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index)
    df.index.name = "datetime"

    # NaN 除去・ソート
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_index()

    return df
