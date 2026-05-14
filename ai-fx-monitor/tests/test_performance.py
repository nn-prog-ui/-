"""価格追跡・勝率集計のテスト"""
from __future__ import annotations
from datetime import datetime

import pytest

from app.database.db import init_db
from app.database.repository import (
    check_and_close_open_trades,
    close_trade,
    get_open_trades,
    get_performance_stats,
    save_approval,
)
from app.services.market_analyzer import AnalysisResult
from app.strategy.risk import TradeSetup


def _make_setup(entry=150.0, sl=149.5, tp=151.0, rr=2.0) -> TradeSetup:
    return TradeSetup(entry_price=entry, stop_loss=sl, take_profit=tp, risk_reward=rr, is_valid=True)


def _make_result(signal="BUY", symbol="USD/JPY", current_price=150.0,
                 setup=None, **kwargs) -> AnalysisResult:
    if setup is None and signal in ("BUY", "SELL"):
        ep = kwargs.pop("entry_price", 150.0)
        sl = kwargs.pop("stop_loss", 149.5 if signal == "BUY" else 150.5)
        tp = kwargs.pop("take_profit", 151.0 if signal == "BUY" else 149.0)
        rr = kwargs.pop("risk_reward", 2.0)
        setup = TradeSetup(entry_price=ep, stop_loss=sl, take_profit=tp, risk_reward=rr, is_valid=True)
    elif signal == "SKIP":
        kwargs.pop("entry_price", None)
        kwargs.pop("stop_loss", None)
        kwargs.pop("take_profit", None)
        kwargs.pop("risk_reward", None)
        setup = None
    return AnalysisResult(
        symbol=symbol,
        analyzed_at=datetime.now(),
        current_price=current_price,
        signal=signal,
        score=kwargs.pop("score", 5),
        daily_trend=kwargs.pop("daily_trend", "上昇"),
        h4_trend=kwargs.pop("h4_trend", "上昇"),
        h1_status=kwargs.pop("h1_status", "押し目"),
        rsi=kwargs.pop("rsi", 55.0),
        atr_value=kwargs.pop("atr_value", 0.5),
        atr_status=kwargs.pop("atr_status", "標準"),
        recent_high=kwargs.pop("recent_high", 151.0),
        recent_low=kwargs.pop("recent_low", 149.0),
        setup=setup,
        economic_warning=kwargs.pop("economic_warning", False),
        economic_event_name=kwargs.pop("economic_event_name", ""),
        ai_comment=kwargs.pop("ai_comment", ""),
        skip_reasons=kwargs.pop("skip_reasons", []),
        data_sufficient=kwargs.pop("data_sufficient", True),
        is_dummy_data=kwargs.pop("is_dummy_data", False),
    )


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


class TestGetPerformanceStatsEmpty:
    def test_empty_db_returns_zeros(self, db):
        stats = get_performance_stats(db)
        assert stats["total_trades"] == 0
        assert stats["win_count"] == 0
        assert stats["loss_count"] == 0
        assert stats["open_count"] == 0
        assert stats["win_rate"] is None
        assert stats["total_pips"] == 0.0
        assert stats["avg_pips"] is None

    def test_returns_all_keys(self, db):
        stats = get_performance_stats(db)
        for key in ("total_trades", "closed_trades", "win_count", "loss_count",
                    "open_count", "win_rate", "total_pips", "avg_pips"):
            assert key in stats


class TestGetOpenTrades:
    def test_empty_when_no_approvals(self, db):
        assert get_open_trades(db) == []

    def test_returns_buy_approved(self, db):
        save_approval(_make_result(), "buy_approved", db_path=db)
        trades = get_open_trades(db)
        assert len(trades) == 1
        assert trades[0]["human_action"] == "buy_approved"

    def test_returns_sell_approved(self, db):
        save_approval(_make_result(signal="SELL"), "sell_approved", db_path=db)
        trades = get_open_trades(db)
        assert len(trades) == 1

    def test_skipped_not_returned(self, db):
        save_approval(_make_result(signal="SKIP"), "skipped", db_path=db)
        assert get_open_trades(db) == []

    def test_closed_trade_not_returned(self, db):
        rec_id = save_approval(_make_result(), "buy_approved", db_path=db)
        close_trade(rec_id, "win", 151.0, 100.0, db)
        assert get_open_trades(db) == []


class TestCheckAndCloseOpenTrades:
    def test_buy_hits_take_profit(self, db):
        save_approval(_make_result(entry_price=150.0, stop_loss=149.5, take_profit=151.0), "buy_approved", db_path=db)
        closed = check_and_close_open_trades(151.0, "USD/JPY", db)
        assert len(closed) == 1
        assert closed[0]["outcome"] == "win"

    def test_buy_hits_stop_loss(self, db):
        save_approval(_make_result(entry_price=150.0, stop_loss=149.5, take_profit=151.0), "buy_approved", db_path=db)
        closed = check_and_close_open_trades(149.5, "USD/JPY", db)
        assert len(closed) == 1
        assert closed[0]["outcome"] == "loss"

    def test_sell_hits_take_profit(self, db):
        save_approval(_make_result(signal="SELL", entry_price=150.0, stop_loss=150.5, take_profit=149.0),
                      "sell_approved", db_path=db)
        closed = check_and_close_open_trades(149.0, "USD/JPY", db)
        assert len(closed) == 1
        assert closed[0]["outcome"] == "win"

    def test_sell_hits_stop_loss(self, db):
        save_approval(_make_result(signal="SELL", entry_price=150.0, stop_loss=150.5, take_profit=149.0),
                      "sell_approved", db_path=db)
        closed = check_and_close_open_trades(150.5, "USD/JPY", db)
        assert len(closed) == 1
        assert closed[0]["outcome"] == "loss"

    def test_between_sl_tp_stays_open(self, db):
        save_approval(_make_result(entry_price=150.0, stop_loss=149.5, take_profit=151.0), "buy_approved", db_path=db)
        closed = check_and_close_open_trades(150.3, "USD/JPY", db)
        assert len(closed) == 0
        assert len(get_open_trades(db)) == 1

    def test_pips_jpy_pair(self, db):
        save_approval(_make_result(entry_price=150.0, stop_loss=149.5, take_profit=151.0), "buy_approved", db_path=db)
        closed = check_and_close_open_trades(151.0, "USD/JPY", db)
        assert abs(closed[0]["pnl_pips"] - 100.0) < 0.01  # (151.0-150.0)/0.01 = 100

    def test_pips_non_jpy_pair(self, db):
        result = _make_result(symbol="EUR/USD", current_price=1.1000,
                               entry_price=1.1000, stop_loss=1.0950, take_profit=1.1100)
        save_approval(result, "buy_approved", db_path=db)
        closed = check_and_close_open_trades(1.1100, "EUR/USD", db)
        assert len(closed) == 1
        assert abs(closed[0]["pnl_pips"] - 100.0) < 0.01  # (1.1100-1.1000)/0.0001 = 100


class TestPerformanceStats:
    def test_win_rate_calculation(self, db):
        r1 = save_approval(_make_result(), "buy_approved", db_path=db)
        r2 = save_approval(_make_result(), "buy_approved", db_path=db)
        close_trade(r1, "win", 151.0, 100.0, db)
        close_trade(r2, "loss", 149.5, -50.0, db)
        stats = get_performance_stats(db)
        assert stats["win_count"] == 1
        assert stats["loss_count"] == 1
        assert abs(stats["win_rate"] - 50.0) < 0.01
        assert abs(stats["total_pips"] - 50.0) < 0.01

    def test_open_count(self, db):
        save_approval(_make_result(), "buy_approved", db_path=db)
        save_approval(_make_result(), "buy_approved", db_path=db)
        stats = get_performance_stats(db)
        assert stats["open_count"] == 2
        assert stats["win_rate"] is None
