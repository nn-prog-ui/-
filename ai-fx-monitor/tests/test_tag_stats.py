"""tests/test_tag_stats.py — Phase 59: ジャーナルタグ別成績分析テスト"""
from __future__ import annotations

import pytest

from app.scripts.tag_stats import (
    TAG_MIN_TRADES,
    TagReport,
    _parse_tags,
    get_tag_report,
)


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _insert_trade(conn, symbol, outcome, pnl_pips):
    """approval_history に1件挿入してIDを返す。"""
    cur = conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("2026-01-10 10:00:00", symbol, "BUY", "buy_approved", outcome, pnl_pips,
         3, 50.0, "上昇", "上昇", "上昇", 0),
    )
    return cur.lastrowid


def _insert_journal(conn, approval_id, tags):
    """trade_journal に1件挿入する。"""
    conn.execute(
        """INSERT INTO trade_journal
           (approval_id, created_at, updated_at, notes, tags)
           VALUES (?, ?, ?, ?, ?)""",
        (approval_id, "2026-01-10 10:00:00", "2026-01-10 10:00:00", "テストメモ", tags),
    )


# ── _parse_tags ────────────────────────────────────────────────────

class TestParseTags:
    def test_single_tag(self):
        assert _parse_tags("trend") == ["trend"]

    def test_multiple_tags(self):
        assert _parse_tags("trend,breakout,retest") == ["trend", "breakout", "retest"]

    def test_with_spaces(self):
        assert _parse_tags("trend, breakout, retest") == ["trend", "breakout", "retest"]

    def test_none_returns_empty(self):
        assert _parse_tags(None) == []

    def test_empty_string_returns_empty(self):
        assert _parse_tags("") == []

    def test_only_commas_returns_empty(self):
        assert _parse_tags(",,,") == []

    def test_trailing_comma(self):
        assert _parse_tags("trend,") == ["trend"]


# ── empty DB ───────────────────────────────────────────────────────

class TestEmptyDB:
    def test_empty_returns_zero_trades(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_tag_report(db_path=db)
        assert report.total_trades == 0

    def test_empty_returns_zero_tags(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_tag_report(db_path=db)
        assert report.total_tags == 0

    def test_empty_has_no_buckets(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_tag_report(db_path=db)
        assert report.buckets == []

    def test_empty_series_are_empty(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_tag_report(db_path=db)
        assert report.tag_labels == []
        assert report.win_rate_series == []
        assert report.expectancy_series == []
        assert report.trade_count_series == []

    def test_empty_best_worst_none(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_tag_report(db_path=db)
        assert report.best_tag is None
        assert report.worst_tag is None


# ── tag aggregation ────────────────────────────────────────────────

class TestTagAggregation:
    def test_single_tag_counted(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            aid = _insert_trade(conn, "USD/JPY", "win", 10.0)
            _insert_journal(conn, aid, "trend")
        report = get_tag_report(db_path=db)
        assert report.total_tags == 1
        assert report.total_trades == 1
        assert report.buckets[0].tag == "trend"
        assert report.buckets[0].trades == 1

    def test_multi_tag_trade_counted_in_each(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            aid = _insert_trade(conn, "USD/JPY", "win", 10.0)
            _insert_journal(conn, aid, "trend,breakout")
        report = get_tag_report(db_path=db)
        assert report.total_tags == 2
        tags = {b.tag for b in report.buckets}
        assert "trend" in tags
        assert "breakout" in tags
        for b in report.buckets:
            assert b.trades == 1

    def test_win_rate_calculated(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for _ in range(2):
                aid = _insert_trade(conn, "USD/JPY", "win", 10.0)
                _insert_journal(conn, aid, "trend")
            aid = _insert_trade(conn, "USD/JPY", "loss", -5.0)
            _insert_journal(conn, aid, "trend")
        report = get_tag_report(db_path=db)
        trend = next(b for b in report.buckets if b.tag == "trend")
        assert trend.win_rate == pytest.approx(100 * 2 / 3, abs=0.1)

    def test_expectancy_calculated(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            aid = _insert_trade(conn, "USD/JPY", "win", 20.0)
            _insert_journal(conn, aid, "breakout")
            aid = _insert_trade(conn, "USD/JPY", "loss", -10.0)
            _insert_journal(conn, aid, "breakout")
        report = get_tag_report(db_path=db)
        breakout = next(b for b in report.buckets if b.tag == "breakout")
        assert breakout.expectancy == pytest.approx(5.0)

    def test_profit_factor_calculated(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            aid = _insert_trade(conn, "USD/JPY", "win", 30.0)
            _insert_journal(conn, aid, "trend")
            aid = _insert_trade(conn, "USD/JPY", "loss", -10.0)
            _insert_journal(conn, aid, "trend")
        report = get_tag_report(db_path=db)
        trend = next(b for b in report.buckets if b.tag == "trend")
        assert trend.profit_factor == pytest.approx(3.0, abs=0.01)

    def test_no_trades_no_journal(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # trade without journal entry
            _insert_trade(conn, "USD/JPY", "win", 10.0)
        report = get_tag_report(db_path=db)
        assert report.total_trades == 0
        assert report.total_tags == 0

    def test_empty_tags_excluded(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            aid = _insert_trade(conn, "USD/JPY", "win", 10.0)
            _insert_journal(conn, aid, "")
        report = get_tag_report(db_path=db)
        assert report.total_tags == 0


# ── chart series ──────────────────────────────────────────────────

class TestChartSeries:
    def test_min_trades_filter(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # "rare" tag: only 1 trade — should NOT appear in chart
            aid = _insert_trade(conn, "USD/JPY", "win", 10.0)
            _insert_journal(conn, aid, "rare")
            # "common" tag: 2 trades — SHOULD appear in chart (TAG_MIN_TRADES=2)
            for _ in range(TAG_MIN_TRADES):
                aid = _insert_trade(conn, "USD/JPY", "win", 10.0)
                _insert_journal(conn, aid, "common")
        report = get_tag_report(db_path=db)
        assert "common" in report.tag_labels
        assert "rare" not in report.tag_labels

    def test_series_sorted_by_expectancy_desc(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # "good" tag: high expectancy
            for _ in range(TAG_MIN_TRADES):
                aid = _insert_trade(conn, "USD/JPY", "win", 20.0)
                _insert_journal(conn, aid, "good")
            # "bad" tag: negative expectancy
            for _ in range(TAG_MIN_TRADES):
                aid = _insert_trade(conn, "USD/JPY", "loss", -10.0)
                _insert_journal(conn, aid, "bad")
        report = get_tag_report(db_path=db)
        assert report.tag_labels[0] == "good"
        assert report.tag_labels[-1] == "bad"

    def test_series_lengths_match(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for _ in range(TAG_MIN_TRADES):
                aid = _insert_trade(conn, "USD/JPY", "win", 10.0)
                _insert_journal(conn, aid, "trend")
        report = get_tag_report(db_path=db)
        n = len(report.tag_labels)
        assert len(report.win_rate_series) == n
        assert len(report.expectancy_series) == n
        assert len(report.trade_count_series) == n
        assert len(report.profit_factor_series) == n


# ── best / worst ──────────────────────────────────────────────────

class TestBestWorst:
    def test_best_worst_by_expectancy(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # "good": +20 each
            for _ in range(TAG_MIN_TRADES):
                aid = _insert_trade(conn, "USD/JPY", "win", 20.0)
                _insert_journal(conn, aid, "good")
            # "bad": -10 each
            for _ in range(TAG_MIN_TRADES):
                aid = _insert_trade(conn, "USD/JPY", "loss", -10.0)
                _insert_journal(conn, aid, "bad")
        report = get_tag_report(db_path=db)
        assert report.best_tag == "good"
        assert report.worst_tag == "bad"

    def test_best_worst_none_when_insufficient(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # Only 1 trade per tag — below TAG_MIN_TRADES
            aid = _insert_trade(conn, "USD/JPY", "win", 10.0)
            _insert_journal(conn, aid, "trend")
        report = get_tag_report(db_path=db)
        assert report.best_tag is None
        assert report.worst_tag is None


# ── symbol filter ──────────────────────────────────────────────────

class TestSymbolFilter:
    def test_filter_by_symbol(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            aid1 = _insert_trade(conn, "USD/JPY", "win", 10.0)
            _insert_journal(conn, aid1, "trend")
            aid2 = _insert_trade(conn, "EUR/USD", "win", 10.0)
            _insert_journal(conn, aid2, "trend")
        report = get_tag_report(symbol="USD/JPY", db_path=db)
        assert report.total_trades == 1

    def test_no_filter_includes_all(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            aid1 = _insert_trade(conn, "USD/JPY", "win", 10.0)
            _insert_journal(conn, aid1, "trend")
            aid2 = _insert_trade(conn, "EUR/USD", "win", 10.0)
            _insert_journal(conn, aid2, "trend")
        report = get_tag_report(symbol=None, db_path=db)
        assert report.total_trades == 2
