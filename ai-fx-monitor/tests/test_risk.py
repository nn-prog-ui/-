"""リスク管理テスト"""
import numpy as np
import pandas as pd
import pytest

from app.strategy.risk import (
    MIN_RISK_REWARD,
    TradeSetup,
    calculate_buy_setup,
    calculate_sell_setup,
    can_approve,
)


def make_ohlc(n: int = 200, start: float = 150.0, trend: float = 0.0) -> pd.DataFrame:
    np.random.seed(1)
    closes = [start + trend * i + np.random.normal(0, 0.05) for i in range(n)]
    closes = np.array(closes)
    highs = closes + 0.1
    lows = closes - 0.1
    opens = np.roll(closes, 1)
    opens[0] = start
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes},
        index=idx,
    )


class TestCalculateBuySetup:
    def test_buy_setup_returns_trade_setup(self):
        df = make_ohlc(200)
        setup = calculate_buy_setup(df, df)
        assert isinstance(setup, TradeSetup)

    def test_buy_setup_entry_price_is_current(self):
        df = make_ohlc(200)
        setup = calculate_buy_setup(df, df)
        if setup.entry_price is not None:
            assert abs(setup.entry_price - float(df["close"].iloc[-1])) < 0.01

    def test_buy_setup_stoploss_below_entry(self):
        df = make_ohlc(200)
        setup = calculate_buy_setup(df, df)
        if setup.stop_loss is not None and setup.entry_price is not None:
            assert setup.stop_loss < setup.entry_price

    def test_buy_setup_takeprofit_above_entry(self):
        df = make_ohlc(200)
        setup = calculate_buy_setup(df, df)
        if setup.take_profit is not None and setup.entry_price is not None:
            assert setup.take_profit > setup.entry_price

    def test_buy_setup_empty_df_returns_invalid(self):
        setup = calculate_buy_setup(pd.DataFrame(), pd.DataFrame())
        assert not setup.is_valid
        assert setup.entry_price is None

    def test_buy_setup_rr_consistency(self):
        """risk_rewardが設定されている場合、手計算と一致するか確認。"""
        df = make_ohlc(200)
        setup = calculate_buy_setup(df, df)
        if (
            setup.risk_reward is not None
            and setup.entry_price is not None
            and setup.stop_loss is not None
            and setup.take_profit is not None
        ):
            risk = setup.entry_price - setup.stop_loss
            reward = setup.take_profit - setup.entry_price
            expected_rr = round(reward / risk, 2)
            assert abs(setup.risk_reward - expected_rr) < 0.01


class TestCalculateSellSetup:
    def test_sell_setup_returns_trade_setup(self):
        df = make_ohlc(200)
        setup = calculate_sell_setup(df, df)
        assert isinstance(setup, TradeSetup)

    def test_sell_setup_stoploss_above_entry(self):
        df = make_ohlc(200)
        setup = calculate_sell_setup(df, df)
        if setup.stop_loss is not None and setup.entry_price is not None:
            assert setup.stop_loss > setup.entry_price

    def test_sell_setup_takeprofit_below_entry(self):
        df = make_ohlc(200)
        setup = calculate_sell_setup(df, df)
        if setup.take_profit is not None and setup.entry_price is not None:
            assert setup.take_profit < setup.entry_price

    def test_sell_setup_empty_returns_invalid(self):
        setup = calculate_sell_setup(pd.DataFrame(), pd.DataFrame())
        assert not setup.is_valid


class TestCanApprove:
    def test_skip_signal_cannot_approve(self):
        setup = TradeSetup(150.0, 149.5, 151.0, 2.0, True)
        ok, reason = can_approve(setup, "SKIP")
        assert not ok

    def test_no_stoploss_cannot_approve(self):
        setup = TradeSetup(150.0, None, 151.0, None, False, "損切りなし")
        ok, reason = can_approve(setup, "BUY")
        assert not ok
        assert "損切り" in reason

    def test_no_takeprofit_cannot_approve(self):
        setup = TradeSetup(150.0, 149.5, None, None, False, "利確なし")
        ok, reason = can_approve(setup, "BUY")
        assert not ok
        assert "利確" in reason

    def test_no_rr_cannot_approve(self):
        setup = TradeSetup(150.0, 149.5, 151.0, None, False, "RR計算不能")
        ok, reason = can_approve(setup, "BUY")
        assert not ok

    def test_low_rr_cannot_approve(self):
        setup = TradeSetup(150.0, 149.5, 150.3, 0.6, False, "RR不足")
        ok, reason = can_approve(setup, "BUY")
        assert not ok

    def test_valid_buy_setup_can_approve(self):
        setup = TradeSetup(150.0, 149.5, 151.0, 2.0, True)
        ok, reason = can_approve(setup, "BUY")
        assert ok
        assert reason == ""

    def test_valid_sell_setup_can_approve(self):
        setup = TradeSetup(150.0, 150.5, 149.0, 2.0, True)
        ok, reason = can_approve(setup, "SELL")
        assert ok
