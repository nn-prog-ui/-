"""tests/test_scorecard.py — Phase 53: システムスコアカードテスト"""
from __future__ import annotations

import pytest

from app.scripts.scorecard import (
    GRADE_SCORE,
    MetricGrade,
    Scorecard,
    _grade_expectancy,
    _grade_max_drawdown_pct,
    _grade_monthly_positive_rate,
    _grade_profit_factor,
    _grade_recovery_factor,
    _grade_sqn,
    _grade_win_rate,
    _overall_grade,
    get_scorecard,
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


# ── グレーディング関数 ─────────────────────────────────────────────

class TestGradeWinRate:
    def test_a(self):
        assert _grade_win_rate(65)[0] == "A"

    def test_b(self):
        assert _grade_win_rate(55)[0] == "B"

    def test_c(self):
        assert _grade_win_rate(48)[0] == "C"

    def test_d(self):
        assert _grade_win_rate(40)[0] == "D"

    def test_f(self):
        assert _grade_win_rate(30)[0] == "F"

    def test_none_is_na(self):
        assert _grade_win_rate(None)[0] == "N/A"


class TestGradeExpectancy:
    def test_a(self):
        assert _grade_expectancy(6.0)[0] == "A"

    def test_b(self):
        assert _grade_expectancy(3.0)[0] == "B"

    def test_c(self):
        assert _grade_expectancy(0.5)[0] == "C"

    def test_f_negative(self):
        assert _grade_expectancy(-5.0)[0] == "F"


class TestGradeProfitFactor:
    def test_a(self):
        assert _grade_profit_factor(2.5)[0] == "A"

    def test_b(self):
        assert _grade_profit_factor(1.7)[0] == "B"

    def test_f(self):
        assert _grade_profit_factor(0.5)[0] == "F"


class TestGradeMaxDD:
    def test_a_small_dd(self):
        assert _grade_max_drawdown_pct(3.0)[0] == "A"

    def test_b(self):
        assert _grade_max_drawdown_pct(8.0)[0] == "B"

    def test_f_large_dd(self):
        assert _grade_max_drawdown_pct(40.0)[0] == "F"


class TestGradeSQN:
    def test_a(self):
        assert _grade_sqn(3.5)[0] == "A"

    def test_b(self):
        assert _grade_sqn(2.5)[0] == "B"

    def test_none_is_na(self):
        assert _grade_sqn(None)[0] == "N/A"


# ── _overall_grade ────────────────────────────────────────────────

class TestOverallGrade:
    def test_all_a_gives_a(self):
        grade, score = _overall_grade([5, 5, 5])
        assert grade == "A"
        assert score == pytest.approx(5.0)

    def test_all_f_gives_f(self):
        grade, _ = _overall_grade([1, 1, 1])
        assert grade == "F"

    def test_empty_gives_na(self):
        grade, score = _overall_grade([])
        assert grade == "N/A"
        assert score == 0.0

    def test_zeros_excluded(self):
        # N/A (score=0) はスキップ
        grade, _ = _overall_grade([0, 5, 5])
        assert grade == "A"


# ── get_scorecard ─────────────────────────────────────────────────

class TestGetScorecard:
    def test_empty_db(self, tmp_path):
        db = _make_db(tmp_path)
        sc = get_scorecard(db_path=db)
        assert sc.total_trades == 0
        assert sc.overall_grade == "N/A"
        assert sc.metrics == []

    def test_with_data_returns_scorecard(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(10):
                outcome = "win" if i % 2 == 0 else "loss"
                pnl = 20.0 if outcome == "win" else -10.0
                _insert(conn, f"2026-01-{i+1:02d} 10:00:00", outcome, pnl)
        sc = get_scorecard(db_path=db)
        assert sc.total_trades == 10
        assert sc.overall_grade in ("A", "B", "C", "D", "F")
        assert len(sc.metrics) == 9

    def test_metrics_have_correct_keys(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-01", "win", 10.0)
            _insert(conn, "2026-01-02", "loss", -5.0)
        sc = get_scorecard(db_path=db)
        keys = {m.key for m in sc.metrics}
        assert "win_rate" in keys
        assert "expectancy" in keys
        assert "profit_factor" in keys
        assert "max_dd" in keys

    def test_radar_labels_match_metrics(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-01", "win", 10.0)
            _insert(conn, "2026-01-02", "loss", -5.0)
        sc = get_scorecard(db_path=db)
        assert len(sc.radar_labels) == len(sc.metrics)
        assert len(sc.radar_values) == len(sc.metrics)

    def test_radar_values_in_range(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-01", "win", 10.0)
            _insert(conn, "2026-01-02", "loss", -5.0)
        sc = get_scorecard(db_path=db)
        for v in sc.radar_values:
            assert 0 <= v <= 5

    def test_symbol_filter(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-01", "win", 10.0, "USD/JPY")
            _insert(conn, "2026-01-02", "loss", -5.0, "EUR/USD")
        sc = get_scorecard(symbol="USD/JPY", db_path=db)
        assert sc.total_trades == 1

    def test_recommendation_is_string(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-01", "win", 10.0)
            _insert(conn, "2026-01-02", "loss", -5.0)
        sc = get_scorecard(db_path=db)
        assert isinstance(sc.recommendation, str)
        assert len(sc.recommendation) > 0
