"""時間足変換モジュール（1時間足 → 4時間足・日足）"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

OHLC_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def resample_to_timeframe(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """OHLCデータを指定のルール（例: '4h', '1D'）でリサンプルする。

    Args:
        df: DatetimeIndexを持つOHLCDataFrame（1時間足想定）
        rule: pandas resample rule文字列

    Returns:
        リサンプル済みDataFrame。失敗時は空DataFrame。
    """
    if df.empty:
        return pd.DataFrame()

    agg = {k: v for k, v in OHLC_AGG.items() if k in df.columns}

    try:
        resampled = df.resample(rule).agg(agg).dropna(subset=["open", "close"])
        logger.debug("リサンプル完了: %s → %d行", rule, len(resampled))
        return resampled
    except Exception as exc:
        logger.error("リサンプルエラー: %s - %s", rule, exc)
        return pd.DataFrame()


def to_4h(df: pd.DataFrame) -> pd.DataFrame:
    return resample_to_timeframe(df, "4h")


def to_daily(df: pd.DataFrame) -> pd.DataFrame:
    return resample_to_timeframe(df, "1D")


def get_all_timeframes(df_1h: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """1時間足DataFrameから全時間足を返す。

    Returns:
        {"1h": df, "4h": df, "daily": df}
    """
    return {
        "1h": df_1h,
        "4h": to_4h(df_1h),
        "daily": to_daily(df_1h),
    }
