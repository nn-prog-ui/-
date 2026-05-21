"""tests/test_period_stats.py — Phase 52: 月次・週次パフォーマンスサマリーテスト"""
from __future__ import annotations

import pytest

from app.scripts.period_stats import (
    PeriodReport,
    PeriodStat,
    _build_period_stats,
    _isoweek_label,
    _max_consecutive,
    _parse_dt,
    get_period_report,
)


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _insert(conn, created_at, outcome, pnl_pips, symbol="USD/JPY"):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, "BUY", "buy_approved", outcome, pnl_pips,
         3, 50.0, "上昇", "上昇", "上昇", 0),
    )


def _row(created_at, outcome, pnl_pips):
    return {"created_at": created_at, "outcome": outcome, "pnl_pips": pnl_pips}


# ── _parse_dt ─────────────────────────────────────────────────────

class TestParseDt:
    def test_full_datetime(self):
        dt = _parse_dt("2026-01-15 10:30:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 1

    def test_date_only(self):
        dt = _parse_dt("2026-03-20")
        assert dt is not None

    def test_invalid_returns_none(self):
        assert _parse_dt("not-a-date") is None

    def test_empty_returns_none(self):
        assert _parse_dt("") is None


# ── _isoweek_label ────────────────────────────────────────────────

class TestIsoweekLabel:
    def test_format(self):
        from datetime import datetime
        dt = datetime(2026, 1, 5)
        label = _isoweek_label(dt)
        assert label.startswith("2026-W")
        assert len(label) == 8  # "YYYY-WNN"

    def test_different_weeks_different_labels(self):
        from datetime import datetime
        d1 = datetime(2026, 1, 5)
        d2 = datetime(2026, 1, 12)
        assert _isoweek_label(d1) != _isoweek_label(d2)


# ── _build_period_stats ───────────────────────────────────────────

class TestBuildPeriodStats:
    def test_empty_rows(self):
        result = _build_period_stats([], lambda dt: dt.strftime("%Y-%m"))
        assert result == []

    def test_groups_by_month(self):
        rows = [
            _row("2026-01-10 10:00:00", "win", 10.0),
            _row("2026-01-20 10:00:00", "loss", -5.0),
            _row("2026-02-05 10:00:00", "win", 8.0),
        ]
        result = _build_period_stats(rows, lambda dt: dt.strftime("%Y-%m"))
        assert len(result) == 2
        labels = [s.label for s in result]
        assert "2026-01" in labels
        assert "2026-02" in labels

    def test_total_pips(self):
        rows = [
            _row("2026-01-10", "win", 15.0),
            _row("2026-01-20", "loss", -5.0),
        ]
        result = _build_period_stats(rows, lambda dt: dt.strftime("%Y-%m"))
        assert result[0].total_pips == pytest.approx(10.0)

    def test_win_rate(self):
        rows = [
            _row("2026-01-10", "win", 10.0),
            _row("2026-01-15", "win", 10.0),
            _row("2026-01-20", "loss", -5.0),
        ]
        result = _build_period_stats(rows, lambda dt: dt.strftime("%Y-%m"))
        assert result[0].win_rate == pytest.approx(2 / 3 * 100, abs=0.1)

    def test_ignores_open_trades(self):
        rows = [
            _row("2026-01-10", "win", 10.0),
            _row("2026-01-15", None, 0.0),  # open trade
        ]
        result = _build_period_stats(rows, lambda dt: dt.strftime("%Y-%m"))
        assert result[0].trades == 1


# ── _max_consecutive ─────────────────────────────────────────────

class TestMaxConsecutive:
    def _stat(self, total_pips):
        return PeriodStat(
            label="x", trades=1, wins=1, losses=0,
            win_rate=100.0, total_pips=total_pips, avg_pips=total_pips
        )

    def test_all_positive(self):
        stats = [self._stat(10), self._stat(5), self._stat(3)]
        assert _max_consecutive(stats, positive=True) == 3

    def test_all_negative(self):
        stats = [self._stat(-5), self._stat(-3)]
        assert _max_consecutive(stats, positive=False) == 2

    def test_alternating(self):
        stats = [self._stat(10), self._stat(-5), self._stat(8)]
        assert _max_consecutive(stats, positive=True) == 1

    def test_empty(self):
        assert _max_consecutive([], positive=True) == 0

    def test_streak_of_two(self):
        stats = [self._stat(10), self._stat(5), self._stat(-3), self._stat(8)]
        assert _max_consecutive(stats, positive=True) == 2


# ── get_period_report ─────────────────────────────────────────────

class TestGetPeriodReport:
    def test_empty_db(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_period_report(db_path=db)
        assert report.total_trades == 0
        assert report.monthly == []
        assert report.weekly == []
        assert report.best_month is None
        assert report.worst_month is None

    def test_multi_month_data(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-10 10:00:00", "win", 20.0)
            _insert(conn, "2026-01-20 10:00:00", "loss", -10.0)
            _insert(conn, "2026-02-05 10:00:00", "win", 15.0)
            _insert(conn, "2026-02-15 10:00:00", "win", 10.0)
        report = get_period_report(db_path=db)
        assert len(report.monthly) == 2
        assert report.total_trades == 4

    def test_best_and_worst_month(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-10", "win", 30.0)
            _insert(conn, "2026-02-10", "loss", -20.0)
        report = get_period_report(db_path=db)
        assert report.best_month.label == "2026-01"
        assert report.worst_month.label == "2026-02"

    def test_consecutive_positive(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-10", "win", 10.0)
            _insert(conn, "2026-02-10", "win", 15.0)
            _insert(conn, "2026-03-10", "loss", -20.0)
        report = get_period_report(db_path=db)
        assert report.max_consecutive_positive == 2

    def test_symbol_filter(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-10", "win", 10.0, "USD/JPY")
            _insert(conn, "2026-01-15", "loss", -5.0, "EUR/USD")
        report = get_period_report(symbol="USD/JPY", db_path=db)
        assert report.total_trades == 1

    def test_weekly_data_present(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-05 10:00:00", "win", 10.0)
            _insert(conn, "2026-01-12 10:00:00", "loss", -5.0)
        report = get_period_report(db_path=db)
        assert len(report.weekly) >= 1
