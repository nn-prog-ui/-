"""CSV読み込みおよびダミーデータ生成モジュール"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"datetime", "open", "high", "low", "close"}


def load_csv(filepath: str | Path) -> pd.DataFrame:
    """OHLCVフォーマットのCSVを読み込み、バリデーションして返す。

    CSVが存在しない場合、またはバリデーション失敗時は空のDataFrameを返す。
    """
    filepath = Path(filepath)
    if not filepath.exists():
        logger.warning("CSVファイルが見つかりません: %s", filepath)
        return pd.DataFrame()

    try:
        df = pd.read_csv(filepath, parse_dates=["datetime"])
        df.columns = [c.strip().lower() for c in df.columns]

        if not _validate_ohlc(df):
            logger.error("CSVバリデーション失敗: %s", filepath)
            return pd.DataFrame()

        df = df.sort_values("datetime").reset_index(drop=True)
        df = df.set_index("datetime")
        df = _clean_ohlc(df)
        logger.info("CSVロード完了: %s (%d行)", filepath, len(df))
        return df

    except Exception as exc:
        logger.error("CSV読み込みエラー: %s - %s", filepath, exc)
        return pd.DataFrame()


def _validate_ohlc(df: pd.DataFrame) -> bool:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        logger.error("必須カラムがありません: %s", missing)
        return False
    if len(df) < 100:
        logger.warning("データ行数が少なすぎます: %d行 (最低100行推奨)", len(df))
    return True


def _clean_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])

    # high >= low の整合性チェック
    invalid_mask = df["high"] < df["low"]
    if invalid_mask.any():
        logger.warning("high < low の行を除外: %d行", invalid_mask.sum())
        df = df[~invalid_mask]

    return df


# Phase 83: シンボル別の代表価格（ダミーデータ生成時のベース価格）
_SYMBOL_BASE_PRICES: dict[str, float] = {
    "USD/JPY": 150.0,
    "EUR/USD": 1.085,
    "GBP/USD": 1.265,
    "EUR/JPY": 162.0,
    "AUD/JPY": 97.0,
    "AUD/USD": 0.644,
    "EUR/GBP": 0.850,
    "GBP/JPY": 192.0,
}


def generate_dummy_data(
    n_bars: int = 500,
    base_price: float | None = None,
    symbol: str = "USD/JPY",
    freq: str = "1h",
) -> pd.DataFrame:
    """テスト用ダミーOHLCデータを生成する。

    実際の市場データがない開発・テスト段階でのみ使用すること。
    base_price が None の場合はシンボルに応じた代表価格を使用する。
    """
    if base_price is None:
        base_price = _SYMBOL_BASE_PRICES.get(symbol, 150.0)
    np.random.seed(42)
    periods = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=n_bars, freq=freq)

    returns = np.random.normal(0, 0.0015, n_bars)
    closes = base_price * np.cumprod(1 + returns)

    opens = np.roll(closes, 1)
    opens[0] = base_price

    noise = np.abs(np.random.normal(0, 0.05, n_bars))
    highs = np.maximum(opens, closes) + noise
    lows = np.minimum(opens, closes) - noise

    volumes = np.random.randint(500, 5000, n_bars)

    df = pd.DataFrame(
        {
            "open": np.round(opens, 3),
            "high": np.round(highs, 3),
            "low": np.round(lows, 3),
            "close": np.round(closes, 3),
            "volume": volumes,
        },
        index=periods,
    )
    df.index.name = "datetime"
    logger.info("ダミーデータ生成: %d行 (%s %s)", n_bars, symbol, freq)
    return df


def load_or_generate(filepath: str | Path, **dummy_kwargs) -> tuple[pd.DataFrame, bool]:
    """CSVを読み込み、なければダミーデータを返す。

    Returns:
        (DataFrame, is_dummy): is_dummy=TrueならダミーデータをUIに表示すべき
    """
    df = load_csv(filepath)
    if df.empty:
        logger.info("ダミーデータで代替します")
        return generate_dummy_data(**dummy_kwargs), True
    return df, False
