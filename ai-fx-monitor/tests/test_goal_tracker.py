"""tests/test_goal_tracker.py — Phase 54: 月次・週次目標管理テスト"""
from __future__ import annotations

import pytest

from app.scripts.goal_tracker import (
    TradeGoal,
    VALID_PERIOD_TYPES,
    create_goal,
    current_month_label,
    current_week_label,
    delete_goal,
    get_goal_by_id,
    get_goals,
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


# ── current_*_label ───────────────────────────────────────────────

class TestCurrentLabels:
    def test_month_label_format(self):
        label = current_month_label()
        assert len(label) == 7
        assert label[4] == "-"

    def test_week_label_format(self):
        label = current_week_label()
        assert "-W" in label
        year, week = label.split("-W")
        assert len(year) == 4
        assert 1 <= int(week) <= 53


# ── create_goal / get_goals ───────────────────────────────────────

class TestCreateGoal:
    def test_creates_and_returns_id(self, tmp_path):
        db = _make_db(tmp_path)
        gid = create_goal("monthly", "2026-01", 100.0, db_path=db)
        assert isinstance(gid, int)
        assert gid > 0

    def test_invalid_period_type_raises(self, tmp_path):
        db = _make_db(tmp_path)
        with pytest.raises(ValueError):
            create_goal("yearly", "2026", 100.0, db_path=db)

    def test_zero_target_raises(self, tmp_path):
        db = _make_db(tmp_path)
        with pytest.raises(ValueError):
            create_goal("monthly", "2026-01", 0.0, db_path=db)

    def test_duplicate_upserts(self, tmp_path):
        db = _make_db(tmp_path)
        create_goal("monthly", "2026-01", 100.0, db_path=db)
        create_goal("monthly", "2026-01", 200.0, db_path=db)  # 上書き
        goals = get_goals(db_path=db)
        assert len(goals) == 1
        assert goals[0].target_pips == 200.0

    def test_different_symbol_different_row(self, tmp_path):
        db = _make_db(tmp_path)
        create_goal("monthly", "2026-01", 100.0, symbol="USD/JPY", db_path=db)
        create_goal("monthly", "2026-01", 80.0, symbol="EUR/USD", db_path=db)
        goals = get_goals(db_path=db)
        assert len(goals) == 2


# ── get_goals with actual pips ────────────────────────────────────

class TestGetGoalsWithActual:
    def test_actual_pips_from_history(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10 10:00:00", "win", 20.0)
            _insert_trade(conn, "2026-01-15 10:00:00", "loss", -8.0)
        create_goal("monthly", "2026-01", 50.0, db_path=db)
        goals = get_goals(db_path=db)
        assert len(goals) == 1
        assert goals[0].actual_pips == pytest.approx(12.0)
        assert goals[0].actual_trades == 2

    def test_progress_pct_calculation(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10", "win", 25.0)
        create_goal("monthly", "2026-01", 100.0, db_path=db)
        goals = get_goals(db_path=db)
        assert goals[0].progress_pct == pytest.approx(25.0)

    def test_achieved_when_actual_gte_target(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10", "win", 120.0)
        create_goal("monthly", "2026-01", 100.0, db_path=db)
        goals = get_goals(db_path=db)
        assert goals[0].achieved is True

    def test_not_achieved_when_below_target(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10", "win", 50.0)
        create_goal("monthly", "2026-01", 100.0, db_path=db)
        goals = get_goals(db_path=db)
        assert goals[0].achieved is False

    def test_symbol_filter_actual_pips(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-10", "win", 30.0, "USD/JPY")
            _insert_trade(conn, "2026-01-11", "win", 20.0, "EUR/USD")
        create_goal("monthly", "2026-01", 50.0, symbol="USD/JPY", db_path=db)
        goals = get_goals(db_path=db)
        assert goals[0].actual_pips == pytest.approx(30.0)

    def test_empty_history_zero_actual(self, tmp_path):
        db = _make_db(tmp_path)
        create_goal("monthly", "2026-01", 100.0, db_path=db)
        goals = get_goals(db_path=db)
        assert goals[0].actual_pips == 0.0
        assert goals[0].actual_trades == 0


# ── delete_goal ───────────────────────────────────────────────────

class TestDeleteGoal:
    def test_delete_existing(self, tmp_path):
        db = _make_db(tmp_path)
        gid = create_goal("monthly", "2026-01", 100.0, db_path=db)
        result = delete_goal(gid, db_path=db)
        assert result is True
        assert get_goals(db_path=db) == []

    def test_delete_nonexistent_returns_false(self, tmp_path):
        db = _make_db(tmp_path)
        result = delete_goal(9999, db_path=db)
        assert result is False


# ── get_goal_by_id ────────────────────────────────────────────────

class TestGetGoalById:
    def test_returns_goal(self, tmp_path):
        db = _make_db(tmp_path)
        gid = create_goal("weekly", "2026-W03", 50.0, db_path=db)
        g = get_goal_by_id(gid, db_path=db)
        assert g is not None
        assert g.period_type == "weekly"
        assert g.target_pips == 50.0

    def test_nonexistent_returns_none(self, tmp_path):
        db = _make_db(tmp_path)
        assert get_goal_by_id(9999, db_path=db) is None
