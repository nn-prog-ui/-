"""通貨強弱フィルターモジュール

単一ペアの場合は複数の時間軸モメンタムから強弱スコアを算出する。
複数ペアのデータが提供された場合は相対強弱を計算する。

スコア定義:
  正値 → ベース通貨（例: USDJPYのUSD）が相対的に強い
  負値 → クォート通貨（例: USDJPYのJPY）が相対的に強い
  範囲 → -100 〜 +100（パーセンテージベースのモメンタム平均）
"""
from __future__ import annotations

import pandas as pd

_LOOKBACKS = [5, 10, 20]


def calculate_pair_momentum(
    df_daily: pd.DataFrame,
    lookbacks: list[int] | None = None,
) -> float:
    """単一ペアの日足データからモメンタムスコアを計算する。

    各 lookback 期間の変化率（%）を平均して返す。
    """
    if lookbacks is None:
        lookbacks = _LOOKBACKS
    if df_daily.empty or len(df_daily) < max(lookbacks):
        return 0.0

    scores: list[float] = []
    close = df_daily["close"]
    for lb in lookbacks:
        if len(close) <= lb:
            continue
        pct = (float(close.iloc[-1]) - float(close.iloc[-lb])) / float(close.iloc[-lb]) * 100
        if not pd.isna(pct):
            scores.append(pct)

    return round(sum(scores) / len(scores), 2) if scores else 0.0


def get_strength_status(score: float, threshold: float = 0.1) -> str:
    """スコアから状態文字列を返す。"""
    if score > threshold:
        return "強い"
    if score < -threshold:
        return "弱い"
    return "中立"


def is_strength_confirmed(score: float, signal: str, threshold: float = 0.05) -> bool:
    """シグナル方向とモメンタムが矛盾していないか確認する。

    BUY シグナルで score が大きく負（逆張り）→ 非確認
    SELL シグナルで score が大きく正（逆張り）→ 非確認
    """
    if signal == "BUY":
        return score >= -threshold
    if signal == "SELL":
        return score <= threshold
    return True
