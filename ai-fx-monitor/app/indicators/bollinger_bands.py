"""ボリンジャーバンド計算モジュール"""
from __future__ import annotations

import pandas as pd


def calculate_bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
    col: str = "close",
) -> pd.DataFrame:
    """ボリンジャーバンド（上限・中央・下限）を計算して列を追加する。"""
    result = df.copy()
    result["bb_middle"] = result[col].rolling(window=period, min_periods=period).mean()
    std = result[col].rolling(window=period, min_periods=period).std()
    result["bb_upper"] = result["bb_middle"] + std_dev * std
    result["bb_lower"] = result["bb_middle"] - std_dev * std
    width = result["bb_upper"] - result["bb_lower"]
    result["bb_pct"] = (result[col] - result["bb_lower"]) / width.replace(0, float("nan"))
    return result


def get_bb_values(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[float | None, float | None, float | None]:
    """最新の BB 上限・中央・下限を返す（upper, middle, lower）。"""
    if df.empty or len(df) < period:
        return None, None, None
    calc = calculate_bollinger_bands(df, period, std_dev)
    upper = calc["bb_upper"].iloc[-1]
    middle = calc["bb_middle"].iloc[-1]
    lower = calc["bb_lower"].iloc[-1]
    if pd.isna(upper) or pd.isna(middle) or pd.isna(lower):
        return None, None, None
    return round(float(upper), 3), round(float(middle), 3), round(float(lower), 3)


def get_bb_status(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
    threshold: float = 0.15,
) -> str:
    """現在価格の BB に対する位置を返す。

    threshold 以下の bb_pct → 「下限接近」（売られすぎ、反発の可能性）
    1 - threshold 以上の bb_pct → 「上限接近」（買われすぎ、反落の可能性）
    """
    if df.empty or len(df) < period:
        return "判定不能"
    calc = calculate_bollinger_bands(df, period, std_dev)
    pct = calc["bb_pct"].iloc[-1]
    if pd.isna(pct):
        return "判定不能"
    pct = float(pct)
    if pct <= threshold:
        return "下限接近"
    if pct >= (1.0 - threshold):
        return "上限接近"
    return "中央付近"
