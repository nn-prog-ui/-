"""ATR（平均真のレンジ）・直近高安値計算モジュール"""
from __future__ import annotations

import pandas as pd


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATRを計算する。

    Args:
        df: high / low / close カラムを持つDataFrame
        period: 期間（デフォルト14）

    Returns:
        ATR系列。データ不足の場合はNaNを含む。
    """
    if df.empty or len(df) < period:
        return pd.Series([float("nan")] * len(df), index=df.index if not df.empty else None)

    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(com=period - 1, min_periods=period).mean()
    return atr


def get_atr_value(df: pd.DataFrame, period: int = 14) -> float | None:
    """直近のATR値を返す。"""
    if df.empty or len(df) < period:
        return None
    atr_series = calculate_atr(df, period)
    last = atr_series.iloc[-1]
    return None if pd.isna(last) else round(float(last), 3)


def is_atr_abnormal(df: pd.DataFrame, period: int = 14, threshold: float = 1.5) -> bool:
    """現在のATRが直近period本の平均の threshold倍以上なら異常と判定する。

    異常なボラティリティ時のエントリーを防ぐためのフィルター。
    """
    if df.empty or len(df) < period * 2:
        return False

    atr_series = calculate_atr(df, period)
    if atr_series.isna().all():
        return False

    recent_atr = atr_series.dropna()
    if len(recent_atr) < period:
        return False

    current = recent_atr.iloc[-1]
    historical_mean = recent_atr.iloc[-period - 1 : -1].mean()

    if historical_mean == 0:
        return False

    return bool(current > historical_mean * threshold)


def get_recent_high(df: pd.DataFrame, lookback: int = 20) -> float | None:
    """直近 lookback 本の高値を返す。"""
    if df.empty or len(df) < lookback:
        return None
    return round(float(df["high"].iloc[-lookback:].max()), 3)


def get_recent_low(df: pd.DataFrame, lookback: int = 20) -> float | None:
    """直近 lookback 本の安値を返す。"""
    if df.empty or len(df) < lookback:
        return None
    return round(float(df["low"].iloc[-lookback:].min()), 3)


def get_atr_status(df: pd.DataFrame) -> str:
    """ATRの状態文字列を返す。"""
    if is_atr_abnormal(df):
        return "異常高（警戒）"
    value = get_atr_value(df)
    if value is None:
        return "判定不能"
    return f"{value:.3f}（通常）"
