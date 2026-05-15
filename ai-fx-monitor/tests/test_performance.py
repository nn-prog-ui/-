"""価格追跡・勝率集計のテスト"""
from __future__ import annotations
from datetime import datetime

import pytest

from app.database.db import init_db
from app.database.repository import (
    check_and_close_open_trades,
    close_demo_order,
    close_trade,
    get_demo_performance_stats,
    get_open_trades,
    get_performance_stats,
    get_signal_pattern_stats,
    save_approval,
    save_demo_order,
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


# --------------------------------------------------------------------------- #
# get_demo_performance_stats
# --------------------------------------------------------------------------- #

def _save_demo(db, approval_id=1, symbol="USD/JPY", direction="BUY", units=1000,
               entry=150.0, sl=None, tp=None) -> int:
    return save_demo_order(
        approval_id=approval_id,
        symbol=symbol,
        direction=direction,
        units=units,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        oanda_trade_id="T001",
        oanda_order_id="O001",
        filled_price=entry,
        db_path=db,
    )


class TestGetDemoPerformanceStatsEmpty:
    def test_empty_db_returns_zeros(self, db):
        stats = get_demo_performance_stats(db)
        assert stats["total_orders"] == 0
        assert stats["open_count"] == 0
        assert stats["closed_count"] == 0
        assert stats["win_count"] == 0
        assert stats["loss_count"] == 0
        assert stats["win_rate"] is None
        assert stats["total_pips"] == 0.0
        assert stats["avg_pips"] is None

    def test_returns_all_keys(self, db):
        stats = get_demo_performance_stats(db)
        for key in ("total_orders", "open_count", "closed_count", "win_count",
                    "loss_count", "win_rate", "total_pips", "avg_pips"):
            assert key in stats


class TestGetDemoPerformanceStatsOpen:
    def test_open_order_counted(self, db):
        _save_demo(db)
        stats = get_demo_performance_stats(db)
        assert stats["total_orders"] == 1
        assert stats["open_count"] == 1
        assert stats["closed_count"] == 0
        assert stats["win_count"] == 0
        assert stats["win_rate"] is None

    def test_multiple_open_orders(self, db):
        _save_demo(db)
        _save_demo(db)
        stats = get_demo_performance_stats(db)
        assert stats["total_orders"] == 2
        assert stats["open_count"] == 2


class TestGetDemoPerformanceStatsClosed:
    def test_win_counted(self, db):
        demo_id = _save_demo(db)
        close_demo_order(demo_id, exit_price=151.0, pnl_pips=100.0, db_path=db)
        stats = get_demo_performance_stats(db)
        assert stats["closed_count"] == 1
        assert stats["win_count"] == 1
        assert stats["loss_count"] == 0
        assert abs(stats["win_rate"] - 100.0) < 0.01
        assert abs(stats["total_pips"] - 100.0) < 0.01
        assert abs(stats["avg_pips"] - 100.0) < 0.01

    def test_loss_counted(self, db):
        demo_id = _save_demo(db)
        close_demo_order(demo_id, exit_price=149.5, pnl_pips=-50.0, db_path=db)
        stats = get_demo_performance_stats(db)
        assert stats["win_count"] == 0
        assert stats["loss_count"] == 1
        assert abs(stats["win_rate"] - 0.0) < 0.01
        assert abs(stats["total_pips"] - (-50.0)) < 0.01

    def test_win_rate_fifty_percent(self, db):
        d1 = _save_demo(db)
        d2 = _save_demo(db)
        close_demo_order(d1, exit_price=151.0, pnl_pips=100.0, db_path=db)
        close_demo_order(d2, exit_price=149.5, pnl_pips=-50.0, db_path=db)
        stats = get_demo_performance_stats(db)
        assert stats["win_count"] == 1
        assert stats["loss_count"] == 1
        assert abs(stats["win_rate"] - 50.0) < 0.01
        assert abs(stats["total_pips"] - 50.0) < 0.01

    def test_avg_pips_calculation(self, db):
        d1 = _save_demo(db)
        d2 = _save_demo(db)
        close_demo_order(d1, exit_price=151.0, pnl_pips=100.0, db_path=db)
        close_demo_order(d2, exit_price=151.5, pnl_pips=60.0, db_path=db)
        stats = get_demo_performance_stats(db)
        assert abs(stats["avg_pips"] - 80.0) < 0.01

    def test_open_plus_closed_total(self, db):
        d1 = _save_demo(db)
        _save_demo(db)  # stays open
        close_demo_order(d1, exit_price=151.0, pnl_pips=100.0, db_path=db)
        stats = get_demo_performance_stats(db)
        assert stats["total_orders"] == 2
        assert stats["open_count"] == 1
        assert stats["closed_count"] == 1


class TestGetSignalPatternStats:
    """Phase 20: 過去トレードからの学習データ取得テスト"""

    def test_empty_db_returns_zero_counts(self, db):
        stats = get_signal_pattern_stats("BUY", "上昇", "上昇", db)
        assert stats["overall_closed"] == 0
        assert stats["pattern_closed"] == 0
        assert stats["overall_win_rate"] is None
        assert stats["pattern_win_rate"] is None
        assert stats["recent_outcomes"] == []

    def test_returns_all_keys(self, db):
        stats = get_signal_pattern_stats(db_path=db)
        for key in ("overall_win_rate", "overall_closed", "pattern_win_rate",
                    "pattern_closed", "recent_outcomes"):
            assert key in stats

    def test_overall_win_rate_calculated(self, db):
        # Save 2 BUY trades: 1 win, 1 loss
        r1 = _make_result(signal="BUY")
        r2 = _make_result(signal="BUY")
        id1 = save_approval(r1, "buy_approved", db_path=db)
        id2 = save_approval(r2, "buy_approved", db_path=db)
        close_trade(id1, "win", 151.0, 50.0, db)
        close_trade(id2, "loss", 149.5, -50.0, db)
        stats = get_signal_pattern_stats("BUY", db_path=db)
        assert stats["overall_closed"] == 2
        assert abs(stats["overall_win_rate"] - 50.0) < 0.01

    def test_pattern_win_rate_filters_by_trend(self, db):
        # 2 BUY wins with 上昇/上昇
        r_up = _make_result(signal="BUY", daily_trend="上昇", h4_trend="上昇")
        id1 = save_approval(r_up, "buy_approved", db_path=db)
        id2 = save_approval(r_up, "buy_approved", db_path=db)
        close_trade(id1, "win", 151.0, 50.0, db)
        close_trade(id2, "win", 151.0, 50.0, db)
        # 1 BUY loss with different pattern
        r_down = _make_result(signal="BUY", daily_trend="下降", h4_trend="上昇")
        id3 = save_approval(r_down, "buy_approved", db_path=db)
        close_trade(id3, "loss", 149.5, -50.0, db)
        stats = get_signal_pattern_stats("BUY", "上昇", "上昇", db)
        assert stats["pattern_closed"] == 2
        assert abs(stats["pattern_win_rate"] - 100.0) < 0.01
        assert stats["overall_closed"] == 3

    def test_recent_outcomes_returns_list(self, db):
        r = _make_result(signal="SELL", daily_trend="下降", h4_trend="下降")
        for _ in range(3):
            rid = save_approval(r, "sell_approved", db_path=db)
            close_trade(rid, "win", 149.0, 50.0, db)
        rid = save_approval(r, "sell_approved", db_path=db)
        close_trade(rid, "loss", 150.5, -50.0, db)
        stats = get_signal_pattern_stats("SELL", "下降", "下降", db)
        assert len(stats["recent_outcomes"]) == 4
        assert set(stats["recent_outcomes"]) == {"win", "loss"}
