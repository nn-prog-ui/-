"""リスク管理モジュール：損切り・利確・リスクリワード計算"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.indicators.atr import get_atr_value, get_recent_high, get_recent_low


@dataclass
class TradeSetup:
    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None
    is_valid: bool
    invalid_reason: str = ""


MIN_RISK_REWARD = 1.5


def calculate_buy_setup(df_1h: pd.DataFrame, df_daily: pd.DataFrame) -> TradeSetup:
    """買いエントリー時のトレードセットアップを計算する。

    エントリー：現在価格
    損切り：1時間足の直近安値より少し下
    利確：日足の直近高値付近（空間が十分あれば）
    """
    if df_1h.empty:
        return TradeSetup(None, None, None, None, False, "データ不足")

    current_price = float(df_1h["close"].iloc[-1])

    recent_low_1h = get_recent_low(df_1h, lookback=20)
    if recent_low_1h is None:
        return TradeSetup(current_price, None, None, None, False, "直近安値が計算できません")

    atr = get_atr_value(df_1h, 14)
    buffer = atr * 0.5 if atr else 0.05

    stop_loss = round(recent_low_1h - buffer, 3)
    risk = current_price - stop_loss

    if risk <= 0:
        return TradeSetup(current_price, stop_loss, None, None, False, "損切り価格が現在価格以上です")

    recent_high_daily = get_recent_high(df_daily, lookback=20) if not df_daily.empty else None
    if recent_high_daily and recent_high_daily > current_price:
        take_profit = round(recent_high_daily * 0.995, 3)
    else:
        take_profit = round(current_price + risk * 2.0, 3)

    reward = take_profit - current_price
    if reward <= 0:
        return TradeSetup(current_price, stop_loss, None, None, False, "利確価格が現在価格以下です")

    rr = round(reward / risk, 2)
    is_valid = rr >= MIN_RISK_REWARD
    reason = "" if is_valid else f"RR={rr} が最低基準{MIN_RISK_REWARD}未満です"

    return TradeSetup(current_price, stop_loss, take_profit, rr, is_valid, reason)


def calculate_sell_setup(df_1h: pd.DataFrame, df_daily: pd.DataFrame) -> TradeSetup:
    """売りエントリー時のトレードセットアップを計算する。

    エントリー：現在価格
    損切り：1時間足の直近高値より少し上
    利確：日足の直近安値付近（空間が十分あれば）
    """
    if df_1h.empty:
        return TradeSetup(None, None, None, None, False, "データ不足")

    current_price = float(df_1h["close"].iloc[-1])

    recent_high_1h = get_recent_high(df_1h, lookback=20)
    if recent_high_1h is None:
        return TradeSetup(current_price, None, None, None, False, "直近高値が計算できません")

    atr = get_atr_value(df_1h, 14)
    buffer = atr * 0.5 if atr else 0.05

    stop_loss = round(recent_high_1h + buffer, 3)
    risk = stop_loss - current_price

    if risk <= 0:
        return TradeSetup(current_price, stop_loss, None, None, False, "損切り価格が現在価格以下です")

    recent_low_daily = get_recent_low(df_daily, lookback=20) if not df_daily.empty else None
    if recent_low_daily and recent_low_daily < current_price:
        take_profit = round(recent_low_daily * 1.005, 3)
    else:
        take_profit = round(current_price - risk * 2.0, 3)

    reward = current_price - take_profit
    if reward <= 0:
        return TradeSetup(current_price, stop_loss, None, None, False, "利確価格が現在価格以上です")

    rr = round(reward / risk, 2)
    is_valid = rr >= MIN_RISK_REWARD
    reason = "" if is_valid else f"RR={rr} が最低基準{MIN_RISK_REWARD}未満です"

    return TradeSetup(current_price, stop_loss, take_profit, rr, is_valid, reason)


def can_approve(setup: TradeSetup, signal: str) -> tuple[bool, str]:
    """承認可能かチェックする。

    承認不可条件：
    - 損切り価格なし
    - 利確価格なし
    - RR計算不能
    - RRが基準未満
    """
    if signal not in ("BUY", "SELL"):
        return False, "判定が見送りのため承認不可"
    if setup.stop_loss is None:
        return False, "損切り価格がないため承認不可"
    if setup.take_profit is None:
        return False, "利確価格がないため承認不可"
    if setup.risk_reward is None:
        return False, "リスクリワードが計算できないため承認不可"
    if not setup.is_valid:
        return False, setup.invalid_reason
    return True, ""
