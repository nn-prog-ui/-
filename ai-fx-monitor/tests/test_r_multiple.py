"""tests/test_r_multiple.py — Phase 50: R倍数・期待値分析テスト"""
from __future__ import annotations

import math
import pytest

from app.scripts.r_multiple import (
    RMultipleReport,
    _build_histogram,
    _sqn_grade,
    get_r_multiple_report,
)


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _insert(conn, created_at, symbol, outcome, pnl_pips):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, "BUY", "buy_approved", outcome, pnl_pips,
         3, 50.0, "上昇", "上昇", "上昇", 0),
    )


# ── _sqn_grade ────────────────────────────────────────────────────

class TestSqnGrade:
    def test_none_returns_na(self):
        assert _sqn_grade(None) == "N/A"

    def test_poor(self):
        assert _sqn_grade(1.0) == "Poor"

    def test_average(self):
        assert _sqn_grade(1.7) == "Average"

    def test_good(self):
        assert _sqn_grade(2.5) == "Good"

    def test_excellent(self):
        assert _sqn_grade(4.0) == "Excellent"

    def test_holy_grail(self):
        assert _sqn_grade(5.5) == "Holy Grail"

    def test_boundary_1_6(self):
        assert _sqn_grade(1.6) == "Average"

    def test_boundary_2_0(self):
        assert _sqn_grade(2.0) == "Good"


# ── _build_histogram ──────────────────────────────────────────────

class TestBuildHistogram:
    def test_empty(self):
        labels, counts = _build_histogram([])
        assert labels == []
        assert counts == []

    def test_single_value(self):
        labels, counts = _build_histogram([1.0])
        assert len(labels) == len(counts)
        assert sum(counts) == 1

    def test_total_count(self):
        vals = [1.0, 2.0, -1.0, 0.5, -0.5]
        _, counts = _build_histogram(vals)
        assert sum(counts) == 5

    def test_positive_r_in_positive_bucket(self):
        labels, counts = _build_histogram([1.0, 1.2], bucket_size=0.5)
        assert any(c > 0 for c in counts)

    def test_label_format(self):
        labels, _ = _build_histogram([1.0])
        assert any("R" in lbl for lbl in labels)


# ── get_r_multiple_report (empty DB) ─────────────────────────────

class TestRMultipleEmpty:
    def test_empty_db_returns_zero_trades(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_r_multiple_report(db_path=db)
        assert report.trades == 0
        assert report.mean_r is None
        assert report.sqn is None
        assert report.sqn_grade == "N/A"
        assert report.positive_r_count == 0
        assert report.negative_r_count == 0
        assert report.series == []
        assert report.histogram_labels == []
        assert report.by_symbol == []


# ── get_r_multiple_report (with data) ────────────────────────────

class TestRMultipleWithData:
    def _setup(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-01 10:00:00", "USD/JPY", "win", 20.0)
            _insert(conn, "2026-01-02 10:00:00", "USD/JPY", "loss", -10.0)
            _insert(conn, "2026-01-03 10:00:00", "USD/JPY", "win", 15.0)
            _insert(conn, "2026-01-04 10:00:00", "USD/JPY", "loss", -10.0)
        return db

    def test_trade_count(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        assert report.trades == 4

    def test_avg_loss_pips(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        assert report.avg_loss_pips == 10.0

    def test_mean_r_positive(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        assert report.mean_r is not None
        assert report.mean_r > 0

    def test_expectancy_equals_mean_r(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        assert report.expectancy == report.mean_r

    def test_positive_negative_counts(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        assert report.positive_r_count == 2
        assert report.negative_r_count == 2

    def test_series_length(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        assert len(report.series) == 4

    def test_r_values_normalized(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        r_vals = [t.r_value for t in report.series]
        assert r_vals[0] == pytest.approx(2.0)   # 20 / 10
        assert r_vals[1] == pytest.approx(-1.0)  # -10 / 10

    def test_histogram_non_empty(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        assert len(report.histogram_labels) > 0
        assert sum(report.histogram_counts) == report.trades

    def test_by_symbol_contains_usdjpy(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        syms = [s["symbol"] for s in report.by_symbol]
        assert "USD/JPY" in syms

    def test_sqn_computed(self, tmp_path):
        db = self._setup(tmp_path)
        report = get_r_multiple_report(db_path=db)
        assert report.sqn is not None
        expected = math.sqrt(4) * report.mean_r / report.std_r
        assert report.sqn == pytest.approx(expected, abs=0.01)

    def test_symbol_filter(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-01", "USD/JPY", "win", 20.0)
            _insert(conn, "2026-01-02", "EUR/USD", "loss", -10.0)
        report = get_r_multiple_report(symbol="USD/JPY", db_path=db)
        assert report.trades == 1
        syms = {t.symbol for t in report.series}
        assert syms == {"USD/JPY"}

    def test_single_trade_std_r_none(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert(conn, "2026-01-01", "USD/JPY", "win", 10.0)
        report = get_r_multiple_report(db_path=db)
        assert report.std_r is None
