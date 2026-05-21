"""tests/test_session_stats.py — Phase 58: FXセッション別分析テスト"""
from __future__ import annotations

import pytest

from app.scripts.session_stats import (
    SESSION_LONDON,
    SESSION_NY,
    SESSION_ORDER,
    SESSION_OVERLAP,
    SESSION_TOKYO,
    SessionReport,
    _classify_hour,
    get_session_report,
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


# ── _classify_hour ─────────────────────────────────────────────────

class TestClassifyHour:
    @pytest.mark.parametrize("hour", range(9, 17))
    def test_tokyo_hours(self, hour):
        assert _classify_hour(hour) == SESSION_TOKYO

    @pytest.mark.parametrize("hour", range(17, 21))
    def test_london_hours(self, hour):
        assert _classify_hour(hour) == SESSION_LONDON

    @pytest.mark.parametrize("hour", [21, 22, 23, 0])
    def test_overlap_hours(self, hour):
        assert _classify_hour(hour) == SESSION_OVERLAP

    @pytest.mark.parametrize("hour", range(1, 9))
    def test_ny_hours(self, hour):
        assert _classify_hour(hour) == SESSION_NY

    def test_all_24_hours_covered(self):
        for h in range(24):
            result = _classify_hour(h)
            assert result in SESSION_ORDER, f"Hour {h} not mapped to a known session"


# ── empty DB ───────────────────────────────────────────────────────

class TestEmptyDB:
    def test_empty_returns_zero_trades(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_session_report(db_path=db)
        assert report.total_trades == 0

    def test_empty_has_four_buckets(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_session_report(db_path=db)
        assert len(report.buckets) == 4
        assert [b.session for b in report.buckets] == SESSION_ORDER

    def test_empty_series_length(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_session_report(db_path=db)
        assert len(report.session_labels) == 4
        assert len(report.win_rate_series) == 4
        assert len(report.trade_count_series) == 4
        assert len(report.hourly_counts) == 24
        assert len(report.hourly_win_rates) == 24


# ── session classification ─────────────────────────────────────────

class TestSessionClassification:
    def test_tokyo_trade_counted(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0)  # hour=10 → Tokyo
        report = get_session_report(db_path=db)
        tokyo = next(b for b in report.buckets if b.session == SESSION_TOKYO)
        assert tokyo.trades == 1

    def test_london_trade_counted(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 18:00:00", "win", 10.0)  # hour=18 → London
        report = get_session_report(db_path=db)
        london = next(b for b in report.buckets if b.session == SESSION_LONDON)
        assert london.trades == 1

    def test_overlap_trade_counted(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 21:00:00", "loss", -5.0)  # hour=21 → Overlap
        report = get_session_report(db_path=db)
        overlap = next(b for b in report.buckets if b.session == SESSION_OVERLAP)
        assert overlap.trades == 1

    def test_midnight_classified_as_overlap(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 00:30:00", "win", 5.0)   # hour=0 → Overlap
        report = get_session_report(db_path=db)
        overlap = next(b for b in report.buckets if b.session == SESSION_OVERLAP)
        assert overlap.trades == 1

    def test_ny_trade_counted(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 03:00:00", "win", 15.0)  # hour=3 → NY
        report = get_session_report(db_path=db)
        ny = next(b for b in report.buckets if b.session == SESSION_NY)
        assert ny.trades == 1

    def test_multiple_sessions(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0)   # Tokyo
            _insert_trade(conn, "2026-01-10 18:00:00", "loss", -5.0)  # London
            _insert_trade(conn, "2026-01-10 22:00:00", "win", 8.0)    # Overlap
            _insert_trade(conn, "2026-01-10 04:00:00", "win", 6.0)    # NY
        report = get_session_report(db_path=db)
        assert report.total_trades == 4
        for b in report.buckets:
            assert b.trades == 1


# ── per-session stats ─────────────────────────────────────────────

class TestSessionStats:
    def test_win_rate_calculated(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0)
            _insert_trade(conn, "2026-01-10 11:00:00", "win", 10.0)
            _insert_trade(conn, "2026-01-10 12:00:00", "loss", -5.0)
        report = get_session_report(db_path=db)
        tokyo = next(b for b in report.buckets if b.session == SESSION_TOKYO)
        assert tokyo.win_rate == pytest.approx(100 * 2 / 3, abs=0.1)

    def test_expectancy_calculated(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 20.0)
            _insert_trade(conn, "2026-01-10 11:00:00", "loss", -10.0)
        report = get_session_report(db_path=db)
        tokyo = next(b for b in report.buckets if b.session == SESSION_TOKYO)
        assert tokyo.expectancy == pytest.approx(5.0)

    def test_no_trades_win_rate_is_none(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0)  # Tokyo only
        report = get_session_report(db_path=db)
        london = next(b for b in report.buckets if b.session == SESSION_LONDON)
        assert london.win_rate is None
        assert london.trades == 0


# ── chart series ──────────────────────────────────────────────────

class TestChartSeries:
    def test_series_follow_session_order(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0)
        report = get_session_report(db_path=db)
        assert report.session_labels == SESSION_ORDER
        assert len(report.win_rate_series) == 4
        assert len(report.expectancy_series) == 4
        assert len(report.trade_count_series) == 4

    def test_hourly_counts_length(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0)
        report = get_session_report(db_path=db)
        assert len(report.hourly_counts) == 24
        assert len(report.hourly_win_rates) == 24

    def test_hourly_count_correct(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0)
            _insert_trade(conn, "2026-01-10 10:30:00", "win", 5.0)
            _insert_trade(conn, "2026-01-10 14:00:00", "loss", -5.0)
        report = get_session_report(db_path=db)
        assert report.hourly_counts[10] == 2
        assert report.hourly_counts[14] == 1
        assert report.hourly_counts[0] == 0


# ── best / worst ──────────────────────────────────────────────────

class TestBestWorst:
    def test_best_session_highest_expectancy(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # Tokyo: good (3 trades)
            for i in range(3):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", "win", 20.0)
            # London: bad (3 trades)
            for i in range(3):
                _insert_trade(conn, f"2026-01-{i+1:02d} 18:00:00", "loss", -10.0)
            # NY: neutral (3 trades)
            for i in range(3):
                _insert_trade(conn, f"2026-01-{i+1:02d} 04:00:00", "win", 5.0)
        report = get_session_report(db_path=db)
        assert report.best_session == SESSION_TOKYO
        assert report.worst_session == SESSION_LONDON

    def test_best_worst_none_when_insufficient(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # Only 2 trades in Tokyo — below min 3
            _insert_trade(conn, "2026-01-01 10:00:00", "win", 10.0)
            _insert_trade(conn, "2026-01-02 10:00:00", "win", 10.0)
        report = get_session_report(db_path=db)
        assert report.best_session is None
        assert report.worst_session is None


# ── symbol filter ──────────────────────────────────────────────────

class TestSymbolFilter:
    def test_filter_by_symbol(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0, "USD/JPY")
            _insert_trade(conn, "2026-01-10 11:00:00", "win", 10.0, "EUR/USD")
        report = get_session_report(symbol="USD/JPY", db_path=db)
        assert report.total_trades == 1

    def test_no_filter_includes_all(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 10.0, "USD/JPY")
            _insert_trade(conn, "2026-01-10 11:00:00", "win", 10.0, "EUR/USD")
        report = get_session_report(symbol=None, db_path=db)
        assert report.total_trades == 2
