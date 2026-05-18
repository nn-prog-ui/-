"""バックテストモジュールのテスト"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.scripts.backtest import (
    BacktestResult,
    BacktestTrade,
    _pip_size,
    _simulate_outcome,
    run_backtest,
)
from app.database.repository import save_backtest_results
from app.strategy.rules import SIGNAL_BUY, SIGNAL_SELL


class TestPipSize:
    def test_jpy_pair(self):
        assert _pip_size("USD/JPY") == pytest.approx(0.01)

    def test_non_jpy_pair(self):
        assert _pip_size("EUR/USD") == pytest.approx(0.0001)

    def test_eurjpy(self):
        assert _pip_size("EUR/JPY") == pytest.approx(0.01)


class TestSimulateOutcome:
    def _make_bars(self, closes: list[float]) -> pd.DataFrame:
        return pd.DataFrame({"close": closes})

    def test_buy_hits_take_profit(self):
        trade = BacktestTrade(
            bar_index=0, signal=SIGNAL_BUY,
            entry_price=150.0, stop_loss=149.5, take_profit=151.0, risk_reward=2.0,
        )
        bars = self._make_bars([150.3, 150.8, 151.0])
        result = _simulate_outcome(trade, bars, "USD/JPY")
        assert result.outcome == "win"
        assert result.pnl_pips == pytest.approx(100.0)

    def test_buy_hits_stop_loss(self):
        trade = BacktestTrade(
            bar_index=0, signal=SIGNAL_BUY,
            entry_price=150.0, stop_loss=149.5, take_profit=151.0, risk_reward=2.0,
        )
        bars = self._make_bars([149.8, 149.5])
        result = _simulate_outcome(trade, bars, "USD/JPY")
        assert result.outcome == "loss"
        assert result.pnl_pips == pytest.approx(-50.0)

    def test_sell_hits_take_profit(self):
        trade = BacktestTrade(
            bar_index=0, signal=SIGNAL_SELL,
            entry_price=150.0, stop_loss=150.5, take_profit=149.0, risk_reward=2.0,
        )
        bars = self._make_bars([149.5, 149.0])
        result = _simulate_outcome(trade, bars, "USD/JPY")
        assert result.outcome == "win"
        assert result.pnl_pips == pytest.approx(100.0)

    def test_sell_hits_stop_loss(self):
        trade = BacktestTrade(
            bar_index=0, signal=SIGNAL_SELL,
            entry_price=150.0, stop_loss=150.5, take_profit=149.0, risk_reward=2.0,
        )
        bars = self._make_bars([150.3, 150.5])
        result = _simulate_outcome(trade, bars, "USD/JPY")
        assert result.outcome == "loss"
        assert result.pnl_pips == pytest.approx(-50.0)

    def test_no_hit_returns_open(self):
        trade = BacktestTrade(
            bar_index=0, signal=SIGNAL_BUY,
            entry_price=150.0, stop_loss=149.5, take_profit=151.0, risk_reward=2.0,
        )
        bars = self._make_bars([150.1, 150.2, 150.3])
        result = _simulate_outcome(trade, bars, "USD/JPY")
        assert result.outcome == "open"
        assert result.pnl_pips == 0.0

    def test_eurusd_pip_size(self):
        trade = BacktestTrade(
            bar_index=0, signal=SIGNAL_BUY,
            entry_price=1.1000, stop_loss=1.0950, take_profit=1.1100, risk_reward=2.0,
        )
        bars = self._make_bars([1.1050, 1.1100])
        result = _simulate_outcome(trade, bars, "EUR/USD")
        assert result.outcome == "win"
        assert result.pnl_pips == pytest.approx(100.0)


class TestSaveBacktestResults:
    """Phase 27: save_backtest_results のテスト。"""

    def _make_db(self, tmp_path: Path) -> Path:
        """テスト用の一時DBを初期化して返す。"""
        from app.database.db import init_db
        db_path = tmp_path / "test.db"
        init_db(db_path)
        return db_path

    def _make_trade(self, signal: str, outcome: str) -> BacktestTrade:
        return BacktestTrade(
            bar_index=0,
            signal=signal,
            entry_price=150.0,
            stop_loss=149.5,
            take_profit=151.0,
            risk_reward=2.0,
            outcome=outcome,
            exit_price=151.0 if outcome == "win" else 149.5 if outcome == "loss" else 0.0,
            pnl_pips=50.0 if outcome == "win" else -50.0 if outcome == "loss" else 0.0,
        )

    def test_save_closed_trades_only(self, tmp_path):
        """outcome='open'の取引は保存されない。"""
        db_path = self._make_db(tmp_path)
        trades = [
            self._make_trade("BUY", "win"),
            self._make_trade("BUY", "open"),
            self._make_trade("SELL", "loss"),
        ]
        count = save_backtest_results(trades, "USD/JPY", db_path)
        assert count == 2  # open は除外

    def test_returns_saved_count(self, tmp_path):
        """戻り値が保存件数と一致する。"""
        db_path = self._make_db(tmp_path)
        trades = [
            self._make_trade("BUY", "win"),
            self._make_trade("SELL", "win"),
            self._make_trade("BUY", "loss"),
        ]
        count = save_backtest_results(trades, "USD/JPY", db_path)
        assert count == 3

    def test_saved_as_dummy_data(self, tmp_path):
        """is_dummy_data=1 で保存される。"""
        import sqlite3
        db_path = self._make_db(tmp_path)
        trades = [self._make_trade("BUY", "win")]
        save_backtest_results(trades, "USD/JPY", db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT is_dummy_data FROM approval_history").fetchone()
        conn.close()
        assert row[0] == 1

    def test_win_loss_outcome_saved(self, tmp_path):
        """outcome=win/loss がそれぞれ正しく保存される。"""
        import sqlite3
        db_path = self._make_db(tmp_path)
        trades = [
            self._make_trade("BUY", "win"),
            self._make_trade("SELL", "loss"),
        ]
        save_backtest_results(trades, "EUR/USD", db_path)

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT outcome, human_action FROM approval_history ORDER BY id"
        ).fetchall()
        conn.close()

        assert rows[0][0] == "win"
        assert rows[0][1] == "buy_approved"
        assert rows[1][0] == "loss"
        assert rows[1][1] == "sell_approved"


class TestRunBacktest:
    def test_insufficient_data_returns_empty_result(self, tmp_path):
        tiny_df = pd.DataFrame({
            "open": [150.0] * 10,
            "high": [150.5] * 10,
            "low": [149.5] * 10,
            "close": [150.0] * 10,
        }, index=pd.date_range("2024-01-01", periods=10, freq="1h"))

        with patch("app.scripts.backtest.load_or_generate", return_value=tiny_df):
            result = run_backtest("USD/JPY", window=500, step=24, future_bars=100)

        assert result.valid_setups == 0
        assert result.signals_generated == 0

    def test_result_has_correct_symbol(self, tmp_path):
        tiny_df = pd.DataFrame({
            "open": [150.0] * 10,
            "high": [150.5] * 10,
            "low": [149.5] * 10,
            "close": [150.0] * 10,
        }, index=pd.date_range("2024-01-01", periods=10, freq="1h"))

        with patch("app.scripts.backtest.load_or_generate", return_value=tiny_df):
            result = run_backtest("USD/JPY", window=500)

        assert result.symbol == "USD/JPY"

    def test_win_rate_none_when_no_closed_trades(self):
        result = BacktestResult(
            symbol="USD/JPY",
            total_bars=1000,
            signals_generated=10,
            buy_signals=5,
            sell_signals=5,
            skip_signals=0,
            valid_setups=0,
        )
        assert result.win_rate is None

    def test_unknown_symbol_raises(self):
        with pytest.raises((ValueError, KeyError)):
            run_backtest("XXX/YYY")
