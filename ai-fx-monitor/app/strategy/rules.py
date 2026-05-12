"""売買判定ルールモジュール

ルールはこのファイルに集約する。変更・拡張はここだけ行う。
AIやその他のサービスはこのルール判定を変更できない。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.indicators.atr import (
    get_recent_high,
    get_recent_low,
    is_atr_abnormal,
)
from app.indicators.moving_average import get_ma_trend
from app.indicators.rsi import get_rsi_value
from app.strategy.scoring import ConditionResult, ScoreResult, calculate_score

SIGNAL_BUY = "BUY"
SIGNAL_SELL = "SELL"
SIGNAL_SKIP = "SKIP"

# 全条件を通過した場合にBUY/SELLとみなすために必要な最低条件数（全7条件中）
ALL_CONDITIONS_COUNT = 7


@dataclass
class SignalResult:
    signal: str
    score: ScoreResult | None
    daily_trend: str
    h4_trend: str
    h1_status: str
    rsi: float | None
    atr_abnormal: bool
    recent_high: float | None
    recent_low: float | None
    skip_reasons: list[str]
    data_sufficient: bool


def analyze_signal(
    df_daily: pd.DataFrame,
    df_4h: pd.DataFrame,
    df_1h: pd.DataFrame,
    economic_warning: bool = False,
) -> SignalResult:
    """メインの売買判定関数。

    データ不足、重要指標前後、条件未充足の場合は必ず SKIP を返す。
    """
    skip_reasons: list[str] = []

    # データ不足チェック
    if df_daily.empty or len(df_daily) < 75:
        return SignalResult(
            signal=SIGNAL_SKIP,
            score=None,
            daily_trend="判定不能",
            h4_trend="判定不能",
            h1_status="判定不能",
            rsi=None,
            atr_abnormal=False,
            recent_high=None,
            recent_low=None,
            skip_reasons=["日足データ不足（最低75本必要）"],
            data_sufficient=False,
        )

    if df_4h.empty or len(df_4h) < 75:
        skip_reasons.append("4時間足データ不足（最低75本必要）")

    if df_1h.empty or len(df_1h) < 75:
        skip_reasons.append("1時間足データ不足（最低75本必要）")

    if skip_reasons:
        return SignalResult(
            signal=SIGNAL_SKIP,
            score=None,
            daily_trend=get_ma_trend(df_daily) if len(df_daily) >= 75 else "判定不能",
            h4_trend="判定不能",
            h1_status="判定不能",
            rsi=None,
            atr_abnormal=False,
            recent_high=None,
            recent_low=None,
            skip_reasons=skip_reasons,
            data_sufficient=False,
        )

    # 各指標を計算
    daily_trend = get_ma_trend(df_daily)
    h4_trend = get_ma_trend(df_4h)
    rsi = get_rsi_value(df_1h)
    atr_bad = is_atr_abnormal(df_1h)
    recent_high = get_recent_high(df_1h, lookback=20)
    recent_low = get_recent_low(df_1h, lookback=20)
    current_price = float(df_1h["close"].iloc[-1])

    # 重要指標警戒フィルター
    if economic_warning:
        skip_reasons.append("重要経済指標の前後60分のため見送り")

    h1_high_breakout = _check_h1_high_breakout(df_1h, recent_high)
    h1_low_breakout = _check_h1_low_breakout(df_1h, recent_low)
    h1_status = _get_h1_status(h1_high_breakout, h1_low_breakout)

    # 買い条件チェック
    buy_conditions = _check_buy_conditions(
        daily_trend, h4_trend, h1_high_breakout, rsi, atr_bad, economic_warning
    )
    buy_score = calculate_score(buy_conditions, direction=SIGNAL_BUY)

    # 売り条件チェック
    sell_conditions = _check_sell_conditions(
        daily_trend, h4_trend, h1_low_breakout, rsi, atr_bad, economic_warning
    )
    sell_score = calculate_score(sell_conditions, direction=SIGNAL_SELL)

    # 判定
    buy_all_passed = buy_score.passed_count == ALL_CONDITIONS_COUNT
    sell_all_passed = sell_score.passed_count == ALL_CONDITIONS_COUNT

    if skip_reasons:
        signal = SIGNAL_SKIP
        score = None
    elif buy_all_passed and not sell_all_passed:
        signal = SIGNAL_BUY
        score = buy_score
    elif sell_all_passed and not buy_all_passed:
        signal = SIGNAL_SELL
        score = sell_score
    else:
        signal = SIGNAL_SKIP
        if not buy_all_passed:
            failed = [c.name for c in buy_score.failed_conditions]
            skip_reasons.append(f"買い条件未充足: {', '.join(failed)}")
        if not sell_all_passed:
            failed = [c.name for c in sell_score.failed_conditions]
            skip_reasons.append(f"売り条件未充足: {', '.join(failed)}")
        score = buy_score if buy_score.passed_count >= sell_score.passed_count else sell_score

    return SignalResult(
        signal=signal,
        score=score,
        daily_trend=daily_trend,
        h4_trend=h4_trend,
        h1_status=h1_status,
        rsi=rsi,
        atr_abnormal=atr_bad,
        recent_high=recent_high,
        recent_low=recent_low,
        skip_reasons=skip_reasons,
        data_sufficient=True,
    )


def _check_h1_high_breakout(df_1h: pd.DataFrame, recent_high: float | None) -> bool:
    """1時間足で直近高値を上抜けたか。"""
    if recent_high is None or df_1h.empty:
        return False
    lookback_high = df_1h["high"].iloc[-20:-1].max() if len(df_1h) >= 20 else None
    if lookback_high is None:
        return False
    current_close = float(df_1h["close"].iloc[-1])
    return current_close > lookback_high


def _check_h1_low_breakout(df_1h: pd.DataFrame, recent_low: float | None) -> bool:
    """1時間足で直近安値を下抜けたか。"""
    if recent_low is None or df_1h.empty:
        return False
    lookback_low = df_1h["low"].iloc[-20:-1].min() if len(df_1h) >= 20 else None
    if lookback_low is None:
        return False
    current_close = float(df_1h["close"].iloc[-1])
    return current_close < lookback_low


def _get_h1_status(high_breakout: bool, low_breakout: bool) -> str:
    if high_breakout:
        return "高値突破"
    if low_breakout:
        return "安値割れ"
    return "レンジ内"


def _check_buy_conditions(
    daily_trend: str,
    h4_trend: str,
    h1_high_breakout: bool,
    rsi: float | None,
    atr_bad: bool,
    economic_warning: bool,
) -> list[ConditionResult]:
    conditions = [
        ConditionResult(
            "日足20MA > 75MA（上昇トレンド）",
            daily_trend == "上昇",
            f"日足トレンド: {daily_trend}",
        ),
        ConditionResult(
            "4時間足20MA > 75MA（上昇トレンド）",
            h4_trend == "上昇",
            f"4時間足トレンド: {h4_trend}",
        ),
        ConditionResult(
            "1時間足で直近高値を上抜け",
            h1_high_breakout,
            "高値突破済み" if h1_high_breakout else "高値未突破",
        ),
        ConditionResult(
            "RSIが70未満（過熱なし）",
            rsi is not None and rsi < 70 and rsi >= 40,
            f"RSI: {rsi}" if rsi is not None else "RSI計算不能",
        ),
        ConditionResult(
            "ATRが異常に高くない",
            not atr_bad,
            "通常レンジ" if not atr_bad else "ATR異常高（警戒）",
        ),
        ConditionResult(
            "重要指標前後60分ではない",
            not economic_warning,
            "指標警戒なし" if not economic_warning else "重要指標前後",
        ),
        ConditionResult(
            "リスクリワード1.5以上（トレードセットアップ確認）",
            True,  # RRはrisk.pyで個別チェックするためここでは暫定True
            "RRはセットアップ計算時に確認",
        ),
    ]
    return conditions


def _check_sell_conditions(
    daily_trend: str,
    h4_trend: str,
    h1_low_breakout: bool,
    rsi: float | None,
    atr_bad: bool,
    economic_warning: bool,
) -> list[ConditionResult]:
    conditions = [
        ConditionResult(
            "日足20MA < 75MA（下降トレンド）",
            daily_trend == "下降",
            f"日足トレンド: {daily_trend}",
        ),
        ConditionResult(
            "4時間足20MA < 75MA（下降トレンド）",
            h4_trend == "下降",
            f"4時間足トレンド: {h4_trend}",
        ),
        ConditionResult(
            "1時間足で直近安値を下抜け",
            h1_low_breakout,
            "安値割れ済み" if h1_low_breakout else "安値未割れ",
        ),
        ConditionResult(
            "RSIが30超（売られすぎでない）",
            rsi is not None and rsi > 30 and rsi <= 60,
            f"RSI: {rsi}" if rsi is not None else "RSI計算不能",
        ),
        ConditionResult(
            "ATRが異常に高くない",
            not atr_bad,
            "通常レンジ" if not atr_bad else "ATR異常高（警戒）",
        ),
        ConditionResult(
            "重要指標前後60分ではない",
            not economic_warning,
            "指標警戒なし" if not economic_warning else "重要指標前後",
        ),
        ConditionResult(
            "リスクリワード1.5以上（トレードセットアップ確認）",
            True,
            "RRはセットアップ計算時に確認",
        ),
    ]
    return conditions
