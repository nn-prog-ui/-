"""tests/test_signal_score.py — Phase 56: シグナルスコア分析テスト"""
from __future__ import annotations

import pytest

from app.scripts.signal_score import (
    SCORE_RANGE,
    ScoreBucket,
    ScoreReport,
    get_score_report,
)


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _insert_trade(conn, created_at, outcome, pnl_pips, symbol="USD/JPY", score=3):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, "BUY", "buy_approved", outcome, pnl_pips,
         score, 50.0, "上昇", "上昇", "上昇", 0),
    )


# ── constants ─────────────────────────────────────────────────────────

class TestConstants:
    def test_score_range_is_1_to_5(self):
        assert list(SCORE_RANGE) == [1, 2, 3, 4, 5]


# ── empty DB ──────────────────────────────────────────────────────────

class TestEmptyDB:
    def test_empty_returns_zero_trades(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_score_report(db_path=db)
        assert report.total_trades == 0

    def test_empty_buckets_have_five_entries(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_score_report(db_path=db)
        assert len(report.buckets) == 5
        assert [b.score for b in report.buckets] == [1, 2, 3, 4, 5]

    def test_empty_buckets_win_rate_is_none(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_score_report(db_path=db)
        for b in report.buckets:
            assert b.win_rate is None

    def test_empty_calibration_is_none(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_score_report(db_path=db)
        assert report.is_calibrated is None


# ── per-score aggregation ─────────────────────────────────────────────

class TestPerScoreAggregation:
    def test_trades_counted_per_score(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 10.0, score=3)
            _insert_trade(conn, "2026-01-02", "win", 10.0, score=3)
            _insert_trade(conn, "2026-01-03", "loss", -5.0, score=4)
        report = get_score_report(db_path=db)
        assert report.buckets[2].trades == 2   # score=3, index=2
        assert report.buckets[3].trades == 1   # score=4, index=3
        assert report.buckets[0].trades == 0   # score=1, index=0

    def test_win_rate_per_score(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 10.0, score=5)
            _insert_trade(conn, "2026-01-02", "win", 10.0, score=5)
            _insert_trade(conn, "2026-01-03", "loss", -5.0, score=5)
        report = get_score_report(db_path=db)
        b = report.buckets[4]   # score=5
        assert b.win_rate == pytest.approx(100 * 2 / 3, abs=0.1)

    def test_expectancy_per_score(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 20.0, score=4)
            _insert_trade(conn, "2026-01-02", "loss", -10.0, score=4)
        report = get_score_report(db_path=db)
        b = report.buckets[3]   # score=4
        assert b.expectancy == pytest.approx(5.0)

    def test_profit_factor_all_wins(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 10.0, score=2)
        report = get_score_report(db_path=db)
        b = report.buckets[1]   # score=2
        assert b.profit_factor is None   # no losses → denominator = 0

    def test_profit_factor_mixed(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 30.0, score=3)
            _insert_trade(conn, "2026-01-02", "loss", -10.0, score=3)
        report = get_score_report(db_path=db)
        b = report.buckets[2]
        assert b.profit_factor == pytest.approx(3.0)

    def test_total_pips_accumulates(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 15.0, score=1)
            _insert_trade(conn, "2026-01-02", "loss", -7.0, score=1)
        report = get_score_report(db_path=db)
        b = report.buckets[0]
        assert b.total_pips == pytest.approx(8.0)


# ── chart series ──────────────────────────────────────────────────────

class TestChartSeries:
    def test_series_length_is_five(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 10.0, score=3)
        report = get_score_report(db_path=db)
        assert len(report.score_labels) == 5
        assert len(report.win_rate_series) == 5
        assert len(report.expectancy_series) == 5
        assert len(report.trade_count_series) == 5
        assert len(report.profit_factor_series) == 5

    def test_score_labels_are_strings(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_score_report(db_path=db)
        assert report.score_labels == ["1", "2", "3", "4", "5"]

    def test_trade_count_series_correct(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 10.0, score=2)
            _insert_trade(conn, "2026-01-02", "win", 10.0, score=2)
            _insert_trade(conn, "2026-01-03", "win", 10.0, score=5)
        report = get_score_report(db_path=db)
        assert report.trade_count_series == [0, 2, 0, 0, 1]


# ── symbol filter ──────────────────────────────────────────────────────

class TestSymbolFilter:
    def test_filter_by_symbol(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 10.0, symbol="USD/JPY", score=5)
            _insert_trade(conn, "2026-01-02", "win", 10.0, symbol="EUR/USD", score=5)
        report = get_score_report(symbol="USD/JPY", db_path=db)
        assert report.total_trades == 1
        assert report.buckets[4].trades == 1

    def test_no_filter_includes_all(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 10.0, symbol="USD/JPY", score=3)
            _insert_trade(conn, "2026-01-02", "win", 10.0, symbol="EUR/USD", score=3)
        report = get_score_report(symbol=None, db_path=db)
        assert report.total_trades == 2


# ── calibration ────────────────────────────────────────────────────────

class TestCalibration:
    def test_calibrated_when_higher_score_higher_expectancy(self, tmp_path):
        """高スコア = 高期待値 → is_calibrated=True。"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # score 1: poor
            for i in range(5):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "loss", -10.0, score=1)
            # score 3: neutral
            for i in range(5):
                _insert_trade(conn, f"2026-02-{i+1:02d}", "win", 5.0, score=3)
            # score 5: good
            for i in range(5):
                _insert_trade(conn, f"2026-03-{i+1:02d}", "win", 20.0, score=5)
        report = get_score_report(db_path=db)
        assert report.is_calibrated is True

    def test_not_calibrated_when_inverted(self, tmp_path):
        """高スコア = 低期待値（逆転）→ is_calibrated=False。"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # score 1: best
            for i in range(5):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 20.0, score=1)
            # score 3: neutral
            for i in range(5):
                _insert_trade(conn, f"2026-02-{i+1:02d}", "win", 5.0, score=3)
            # score 5: worst
            for i in range(5):
                _insert_trade(conn, f"2026-03-{i+1:02d}", "loss", -15.0, score=5)
        report = get_score_report(db_path=db)
        assert report.is_calibrated is False

    def test_best_and_worst_score_set(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(5):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 20.0, score=5)
            for i in range(5):
                _insert_trade(conn, f"2026-02-{i+1:02d}", "loss", -10.0, score=1)
            for i in range(3):
                _insert_trade(conn, f"2026-03-{i+1:02d}", "win", 3.0, score=3)
        report = get_score_report(db_path=db)
        assert report.best_score == 5
        assert report.worst_score == 1

    def test_best_worst_none_when_insufficient(self, tmp_path):
        """各スコアのトレード数が 3 件未満 → best/worst=None。"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 10.0, score=3)
            _insert_trade(conn, "2026-01-02", "win", 10.0, score=5)
        report = get_score_report(db_path=db)
        assert report.best_score is None
        assert report.worst_score is None
