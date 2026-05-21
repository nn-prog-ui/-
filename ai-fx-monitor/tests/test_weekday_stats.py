"""tests/test_weekday_stats.py — Phase 60: 曜日別成績分析テスト"""
from __future__ import annotations

import pytest

from app.scripts.weekday_stats import (
    WEEKDAY_MIN_TRADES,
    WEEKDAY_NAMES,
    WeekdayReport,
    get_weekday_report,
)


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _insert_trade(conn, created_at, outcome, pnl_pips, symbol="USD/JPY"):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, "BUY", "buy_approved", outcome, pnl_pips,
         3, 50.0, "上昇", "上昇", "上昇", 0),
    )


# ── empty DB ───────────────────────────────────────────────────────

class TestEmptyDB:
    def test_empty_returns_zero_trades(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_weekday_report(db_path=db)
        assert report.total_trades == 0

    def test_empty_has_seven_buckets(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_weekday_report(db_path=db)
        assert len(report.buckets) == 7

    def test_empty_buckets_in_mon_sun_order(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_weekday_report(db_path=db)
        assert [b.name for b in report.buckets] == WEEKDAY_NAMES

    def test_empty_series_lengths(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_weekday_report(db_path=db)
        assert len(report.weekday_labels) == 7
        assert len(report.win_rate_series) == 7
        assert len(report.expectancy_series) == 7
        assert len(report.trade_count_series) == 7
        assert len(report.profit_factor_series) == 7

    def test_empty_series_are_none_or_zero(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_weekday_report(db_path=db)
        assert all(v is None for v in report.win_rate_series)
        assert all(c == 0 for c in report.trade_count_series)

    def test_empty_best_worst_none(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_weekday_report(db_path=db)
        assert report.best_weekday is None
        assert report.worst_weekday is None


# ── weekday classification ─────────────────────────────────────────

class TestWeekdayClassification:
    # 2026-01-05 is Monday (weekday=0)
    def test_monday_counted(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 10.0)
        report = get_weekday_report(db_path=db)
        assert report.buckets[0].trades == 1   # Monday index=0
        assert report.buckets[0].name == "月"

    # 2026-01-06 is Tuesday
    def test_tuesday_counted(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-06 10:00:00", "win", 10.0)
        report = get_weekday_report(db_path=db)
        assert report.buckets[1].trades == 1

    # 2026-01-10 is Saturday
    def test_saturday_counted(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0)
        report = get_weekday_report(db_path=db)
        assert report.buckets[5].trades == 1   # Saturday index=5
        assert report.buckets[5].name == "土"

    # 2026-01-11 is Sunday
    def test_sunday_counted(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-11 10:00:00", "win", 10.0)
        report = get_weekday_report(db_path=db)
        assert report.buckets[6].trades == 1   # Sunday index=6
        assert report.buckets[6].name == "日"

    def test_total_trades_correct(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 10.0)   # Mon
            _insert_trade(conn, "2026-01-06 10:00:00", "loss", -5.0)  # Tue
            _insert_trade(conn, "2026-01-07 10:00:00", "win", 8.0)    # Wed
        report = get_weekday_report(db_path=db)
        assert report.total_trades == 3
        assert report.buckets[0].trades == 1
        assert report.buckets[1].trades == 1
        assert report.buckets[2].trades == 1


# ── per-weekday stats ──────────────────────────────────────────────

class TestWeekdayStats:
    def test_win_rate_calculated(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # All Monday trades
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 10.0)
            _insert_trade(conn, "2026-01-12 10:00:00", "win", 10.0)
            _insert_trade(conn, "2026-01-19 10:00:00", "loss", -5.0)
        report = get_weekday_report(db_path=db)
        mon = report.buckets[0]
        assert mon.win_rate == pytest.approx(100 * 2 / 3, abs=0.1)

    def test_expectancy_calculated(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 20.0)   # Mon
            _insert_trade(conn, "2026-01-12 10:00:00", "loss", -10.0) # Mon
        report = get_weekday_report(db_path=db)
        assert report.buckets[0].expectancy == pytest.approx(5.0)

    def test_profit_factor_calculated(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 30.0)   # Mon
            _insert_trade(conn, "2026-01-12 10:00:00", "loss", -10.0) # Mon
        report = get_weekday_report(db_path=db)
        assert report.buckets[0].profit_factor == pytest.approx(3.0, abs=0.01)

    def test_no_trades_stats_none(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 10.0)   # Mon only
        report = get_weekday_report(db_path=db)
        for b in report.buckets[1:]:  # Tue..Sun
            assert b.win_rate is None
            assert b.expectancy is None
            assert b.trades == 0


# ── chart series ──────────────────────────────────────────────────

class TestChartSeries:
    def test_labels_are_weekday_names(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_weekday_report(db_path=db)
        assert report.weekday_labels == WEEKDAY_NAMES

    def test_series_length_always_seven(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 10.0)
        report = get_weekday_report(db_path=db)
        assert len(report.win_rate_series) == 7
        assert len(report.expectancy_series) == 7
        assert len(report.trade_count_series) == 7
        assert len(report.profit_factor_series) == 7

    def test_trade_count_in_correct_slot(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 10.0)   # Mon
            _insert_trade(conn, "2026-01-05 11:00:00", "win", 10.0)   # Mon
            _insert_trade(conn, "2026-01-07 10:00:00", "loss", -5.0)  # Wed
        report = get_weekday_report(db_path=db)
        assert report.trade_count_series[0] == 2   # Mon
        assert report.trade_count_series[2] == 1   # Wed
        assert report.trade_count_series[1] == 0   # Tue


# ── best / worst ──────────────────────────────────────────────────

class TestBestWorst:
    def test_best_worst_by_expectancy(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # Monday: +20 each (3 trades)
            for w in range(3):
                _insert_trade(conn, f"2026-01-{5 + w*7:02d} 10:00:00", "win", 20.0)
            # Tuesday: -10 each (3 trades)
            for w in range(3):
                _insert_trade(conn, f"2026-01-{6 + w*7:02d} 10:00:00", "loss", -10.0)
            # Wednesday: small positive (3 trades)
            for w in range(3):
                _insert_trade(conn, f"2026-01-{7 + w*7:02d} 10:00:00", "win", 5.0)
        report = get_weekday_report(db_path=db)
        assert report.best_weekday == "月"
        assert report.worst_weekday == "火"

    def test_best_worst_none_when_insufficient(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # Only 2 trades — below WEEKDAY_MIN_TRADES=3
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 10.0)
            _insert_trade(conn, "2026-01-12 10:00:00", "win", 10.0)
        report = get_weekday_report(db_path=db)
        assert report.best_weekday is None
        assert report.worst_weekday is None


# ── symbol filter ──────────────────────────────────────────────────

class TestSymbolFilter:
    def test_filter_by_symbol(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 10.0, "USD/JPY")
            _insert_trade(conn, "2026-01-06 10:00:00", "win", 10.0, "EUR/USD")
        report = get_weekday_report(symbol="USD/JPY", db_path=db)
        assert report.total_trades == 1

    def test_no_filter_includes_all(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", 10.0, "USD/JPY")
            _insert_trade(conn, "2026-01-06 10:00:00", "win", 10.0, "EUR/USD")
        report = get_weekday_report(symbol=None, db_path=db)
        assert report.total_trades == 2
