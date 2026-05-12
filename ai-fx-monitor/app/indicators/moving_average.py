"""移動平均線計算モジュール"""
from __future__ import annotations

import pandas as pd


def calculate_ma(series: pd.Series, period: int) -> pd.Series:
    """単純移動平均（SMA）を計算する。

    Args:
        series: 価格系列（通常はclose）
        period: 期間

    Returns:
        移動平均系列。データ不足の場合はNaNを含む。
    """
    if len(series) < period:
        return pd.Series([float("nan")] * len(series), index=series.index)
    return series.rolling(window=period, min_periods=period).mean()


def get_ma_trend(df: pd.DataFrame, short: int = 20, long: int = 75) -> str:
    """移動平均線の並びからトレンドを判定する。

    Returns:
        "上昇" | "下降" | "判定不能"
    """
    if df.empty or len(df) < long:
        return "判定不能"

    ma_short = calculate_ma(df["close"], short)
    ma_long = calculate_ma(df["close"], long)

    last_short = ma_short.iloc[-1]
    last_long = ma_long.iloc[-1]

    if pd.isna(last_short) or pd.isna(last_long):
        return "判定不能"

    if last_short > last_long:
        return "上昇"
    elif last_short < last_long:
        return "下降"
    return "横ばい"


def get_ma_values(df: pd.DataFrame) -> dict[str, float | None]:
    """直近の20MA・75MA値を返す。"""
    if df.empty:
        return {"ma20": None, "ma75": None}

    ma20 = calculate_ma(df["close"], 20)
    ma75 = calculate_ma(df["close"], 75)

    def last_val(s: pd.Series) -> float | None:
        v = s.iloc[-1]
        return None if pd.isna(v) else round(float(v), 3)

    return {"ma20": last_val(ma20), "ma75": last_val(ma75)}
