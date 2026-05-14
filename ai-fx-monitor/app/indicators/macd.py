"""MACD（移動平均収束拡散法）計算モジュール"""
from __future__ import annotations

import pandas as pd


def calculate_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    col: str = "close",
) -> pd.DataFrame:
    """MACD・シグナル・ヒストグラムを計算して列を追加する。"""
    result = df.copy()
    ema_fast = result[col].ewm(span=fast, adjust=False).mean()
    ema_slow = result[col].ewm(span=slow, adjust=False).mean()
    result["macd"] = ema_fast - ema_slow
    result["macd_signal"] = result["macd"].ewm(span=signal, adjust=False).mean()
    result["macd_histogram"] = result["macd"] - result["macd_signal"]
    return result


def get_macd_values(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float | None, float | None, float | None]:
    """最新の MACD値・シグナル値・ヒストグラム値を返す。"""
    min_bars = slow + signal
    if df.empty or len(df) < min_bars:
        return None, None, None
    calc = calculate_macd(df, fast, slow, signal)
    macd_val = calc["macd"].iloc[-1]
    signal_val = calc["macd_signal"].iloc[-1]
    histogram = calc["macd_histogram"].iloc[-1]
    if pd.isna(macd_val) or pd.isna(signal_val) or pd.isna(histogram):
        return None, None, None
    return round(float(macd_val), 6), round(float(signal_val), 6), round(float(histogram), 6)


def get_macd_status(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> str:
    """MACD の現在状態を返す。

    ゴールデンクロス: MACD がシグナルを下から上に抜けた直後
    デッドクロス:     MACD がシグナルを上から下に抜けた直後
    上昇モメンタム:   MACD > シグナル継続中
    下降モメンタム:   MACD < シグナル継続中
    """
    min_bars = slow + signal + 1
    if df.empty or len(df) < min_bars:
        return "判定不能"
    calc = calculate_macd(df, fast, slow, signal)

    current_macd = calc["macd"].iloc[-1]
    current_sig = calc["macd_signal"].iloc[-1]
    prev_macd = calc["macd"].iloc[-2]
    prev_sig = calc["macd_signal"].iloc[-2]

    if pd.isna(current_macd) or pd.isna(current_sig) or pd.isna(prev_macd) or pd.isna(prev_sig):
        return "判定不能"

    current_above = current_macd > current_sig
    prev_above = prev_macd > prev_sig

    if current_above and not prev_above:
        return "ゴールデンクロス"
    if not current_above and prev_above:
        return "デッドクロス"
    if current_above:
        return "上昇モメンタム"
    return "下降モメンタム"
