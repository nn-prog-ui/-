"""RSI（相対力指数）計算モジュール"""
from __future__ import annotations

import pandas as pd


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSIを計算する（Wilder平滑化法）。

    Args:
        series: 価格系列（通常はclose）
        period: 期間（デフォルト14）

    Returns:
        RSI系列（0〜100）。データ不足の場合はNaNを含む。
    """
    if len(series) < period + 1:
        return pd.Series([float("nan")] * len(series), index=series.index)

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, float("inf"))
    rsi = 100 - (100 / (1 + rs))

    # 損失が完全にゼロの場合（全部上昇）はRSI=100
    rsi = rsi.where(avg_loss != 0, 100.0)

    return rsi


def get_rsi_value(df: pd.DataFrame, period: int = 14) -> float | None:
    """直近のRSI値を返す。データ不足の場合はNone。"""
    if df.empty or len(df) < period + 1:
        return None
    rsi_series = calculate_rsi(df["close"], period)
    last = rsi_series.iloc[-1]
    return None if pd.isna(last) else round(float(last), 1)


def get_rsi_status(rsi_value: float | None) -> str:
    """RSI値から状態文字列を返す。"""
    if rsi_value is None:
        return "判定不能"
    if rsi_value >= 70:
        return "買われすぎ"
    if rsi_value <= 30:
        return "売られすぎ"
    if rsi_value >= 60:
        return "やや強い"
    if rsi_value <= 40:
        return "やや弱い"
    return "中立"
