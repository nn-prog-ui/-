"""tests/test_streak_stats.py — Phase 61: 連勝・連敗ストリーク分析テスト"""
from __future__ import annotations

import pytest

from app.scripts.streak_stats import (
    StreakReport,
    StreakRun,
    get_streak_report,
)


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _insert_trade(conn, created_at, outcome, symbol="USD/JPY"):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, "BUY", "buy_approved", outcome,
         10.0 if outcome == "win" else -5.0,
         3, 50.0, "上昇", "上昇", "上昇", 0),
    )


# ── empty DB ───────────────────────────────────────────────────────

class TestEmptyDB:
    def test_empty_returns_zero_trades(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_streak_report(db_path=db)
        assert report.total_trades == 0

    def test_empty_current_streak_zero(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_streak_report(db_path=db)
        assert report.current_streak == 0
        assert report.current_outcome is None

    def test_empty_max_streaks_zero(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_streak_report(db_path=db)
        assert report.max_win_streak == 0
        assert report.max_loss_streak == 0

    def test_empty_avg_none(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_streak_report(db_path=db)
        assert report.avg_win_streak is None
        assert report.avg_loss_streak is None

    def test_empty_timeline_empty(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_streak_report(db_path=db)
        assert report.streak_timeline == []
        assert report.timeline_labels == []


# ── current streak ────────────────────────────────────────────────

class TestCurrentStreak:
    def test_single_win(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win")
        report = get_streak_report(db_path=db)
        assert report.current_outcome == "win"
        assert report.current_streak == 1

    def test_three_consecutive_wins(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win")
            _insert_trade(conn, "2026-01-06 10:00:00", "win")
            _insert_trade(conn, "2026-01-07 10:00:00", "win")
        report = get_streak_report(db_path=db)
        assert report.current_outcome == "win"
        assert report.current_streak == 3

    def test_current_after_switch(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win")
            _insert_trade(conn, "2026-01-06 10:00:00", "win")
            _insert_trade(conn, "2026-01-07 10:00:00", "loss")
            _insert_trade(conn, "2026-01-08 10:00:00", "loss")
        report = get_streak_report(db_path=db)
        assert report.current_outcome == "loss"
        assert report.current_streak == 2

    def test_single_loss(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "loss")
        report = get_streak_report(db_path=db)
        assert report.current_outcome == "loss"
        assert report.current_streak == 1


# ── max streak ────────────────────────────────────────────────────

class TestMaxStreak:
    def test_max_win_streak(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # W W W L W W  → max win=3
            for i, oc in enumerate(["win","win","win","loss","win","win"]):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", oc)
        report = get_streak_report(db_path=db)
        assert report.max_win_streak == 3

    def test_max_loss_streak(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # L L L L W L  → max loss=4
            for i, oc in enumerate(["loss","loss","loss","loss","win","loss"]):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", oc)
        report = get_streak_report(db_path=db)
        assert report.max_loss_streak == 4

    def test_max_streaks_separate(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i, oc in enumerate(["win","win","loss","loss","loss","win"]):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", oc)
        report = get_streak_report(db_path=db)
        assert report.max_win_streak == 2
        assert report.max_loss_streak == 3

    def test_all_wins(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(5):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", "win")
        report = get_streak_report(db_path=db)
        assert report.max_win_streak == 5
        assert report.max_loss_streak == 0


# ── average streak ────────────────────────────────────────────────

class TestAvgStreak:
    def test_avg_win_streak_excludes_current(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # W W L → completed win run: length 2, current run: loss=1
            # avg_win = 2.0 (only completed)
            for i, oc in enumerate(["win","win","loss"]):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", oc)
        report = get_streak_report(db_path=db)
        assert report.avg_win_streak == pytest.approx(2.0)

    def test_avg_none_when_no_completed_runs(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # All wins — only one run, which is current → no completed runs
            for i in range(3):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", "win")
        report = get_streak_report(db_path=db)
        assert report.avg_win_streak is None   # no completed win run
        assert report.avg_loss_streak is None


# ── streak distribution ───────────────────────────────────────────

class TestStreakDist:
    def test_dist_length(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_streak_report(db_path=db)
        assert len(report.win_streak_dist) == StreakReport.DIST_MAX
        assert len(report.loss_streak_dist) == StreakReport.DIST_MAX

    def test_single_wins_dist(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # W L W L W  → three single-win runs
            for i, oc in enumerate(["win","loss","win","loss","win"]):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", oc)
        report = get_streak_report(db_path=db)
        assert report.win_streak_dist[0] == 3   # three runs of length 1

    def test_long_run_bucketed_at_max(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # 7 consecutive wins → bucketed at DIST_MAX (index=4 = "5+")
            for i in range(7):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", "win")
        report = get_streak_report(db_path=db)
        assert report.win_streak_dist[StreakReport.DIST_MAX - 1] == 1


# ── streak timeline ───────────────────────────────────────────────

class TestStreakTimeline:
    def test_timeline_length_matches_trades(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i, oc in enumerate(["win","win","loss","win"]):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", oc)
        report = get_streak_report(db_path=db)
        assert len(report.streak_timeline) == 4
        assert len(report.timeline_labels) == 4

    def test_timeline_values(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i, oc in enumerate(["win","win","loss","loss","win"]):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", oc)
        report = get_streak_report(db_path=db)
        # +1, +2, -1, -2, +1
        assert report.streak_timeline == [1, 2, -1, -2, 1]

    def test_timeline_all_wins_positive(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(4):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", "win")
        report = get_streak_report(db_path=db)
        assert all(v > 0 for v in report.streak_timeline)

    def test_timeline_all_losses_negative(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(4):
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", "loss")
        report = get_streak_report(db_path=db)
        assert all(v < 0 for v in report.streak_timeline)


# ── symbol filter ─────────────────────────────────────────────────

class TestSymbolFilter:
    def test_filter_by_symbol(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", "USD/JPY")
            _insert_trade(conn, "2026-01-06 10:00:00", "win", "EUR/USD")
        report = get_streak_report(symbol="USD/JPY", db_path=db)
        assert report.total_trades == 1

    def test_no_filter_includes_all(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-05 10:00:00", "win", "USD/JPY")
            _insert_trade(conn, "2026-01-06 10:00:00", "loss", "EUR/USD")
        report = get_streak_report(symbol=None, db_path=db)
        assert report.total_trades == 2
