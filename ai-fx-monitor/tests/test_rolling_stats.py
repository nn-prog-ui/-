"""tests/test_rolling_stats.py — Phase 55: ローリング成績分析テスト"""
from __future__ import annotations

import pytest

from app.scripts.rolling_stats import (
    DEFAULT_WINDOW,
    TREND_DECLINING,
    TREND_IMPROVING,
    TREND_INSUFFICIENT,
    TREND_STABLE,
    VALID_WINDOWS,
    RollingReport,
    get_rolling_report,
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


# ── constants ────────────────────────────────────────────────────────

class TestConstants:
    def test_default_window_in_valid(self):
        assert DEFAULT_WINDOW in VALID_WINDOWS

    def test_valid_windows_content(self):
        assert {10, 20, 30, 50} == VALID_WINDOWS


# ── empty DB ─────────────────────────────────────────────────────────

class TestEmptyDB:
    def test_empty_returns_zero_trades(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_rolling_report(db_path=db)
        assert report.total_trades == 0
        assert report.points == []
        assert report.labels == []
        assert report.trend == TREND_INSUFFICIENT

    def test_invalid_window_raises(self, tmp_path):
        db = _make_db(tmp_path)
        with pytest.raises(ValueError):
            get_rolling_report(window=7, db_path=db)


# ── basic rolling calculation ────────────────────────────────────────

class TestRollingCalculation:
    def _make_report(self, tmp_path, n_wins, n_losses, window=10):
        """勝ちトレードと負けトレードを一定数挿入してレポートを返す。"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            idx = 0
            for _ in range(n_wins):
                _insert_trade(conn, f"2026-01-{idx+1:02d} 10:00:00", "win", 10.0)
                idx += 1
            for _ in range(n_losses):
                _insert_trade(conn, f"2026-01-{idx+1:02d} 10:00:00", "loss", -5.0)
                idx += 1
        return get_rolling_report(window=window, db_path=db)

    def test_total_trades(self, tmp_path):
        report = self._make_report(tmp_path, n_wins=15, n_losses=5, window=10)
        assert report.total_trades == 20

    def test_overall_win_rate(self, tmp_path):
        report = self._make_report(tmp_path, n_wins=15, n_losses=5, window=10)
        assert report.overall_win_rate == pytest.approx(75.0)

    def test_overall_expectancy(self, tmp_path):
        # 15 wins × 10 + 5 losses × -5 = 150 - 25 = 125 / 20 = 6.25
        report = self._make_report(tmp_path, n_wins=15, n_losses=5, window=10)
        assert report.overall_expectancy == pytest.approx(6.25)

    def test_rolling_starts_from_window_index(self, tmp_path):
        """ウィンドウサイズ未満のポイントは win_rate が None。"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(15):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 10.0)
        report = get_rolling_report(window=10, db_path=db)
        # first 9 points: no rolling value
        for pt in report.points[:9]:
            assert pt.win_rate is None
        # from 10th point onward: rolling value exists
        for pt in report.points[9:]:
            assert pt.win_rate is not None

    def test_win_rate_series_length_matches_labels(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(20):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 10.0)
        report = get_rolling_report(window=10, db_path=db)
        assert len(report.labels) == report.total_trades
        assert len(report.win_rate_series) == report.total_trades
        assert len(report.expectancy_series) == report.total_trades
        assert len(report.profit_factor_series) == report.total_trades
        assert len(report.cumulative_series) == report.total_trades

    def test_cumulative_pips_accumulates(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 10.0)
            _insert_trade(conn, "2026-01-02", "win", 20.0)
            _insert_trade(conn, "2026-01-03", "loss", -5.0)
        report = get_rolling_report(window=10, db_path=db)
        assert report.cumulative_series[0] == pytest.approx(10.0)
        assert report.cumulative_series[1] == pytest.approx(30.0)
        assert report.cumulative_series[2] == pytest.approx(25.0)

    def test_last_window_stats_populated(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(15):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 10.0)
        report = get_rolling_report(window=10, db_path=db)
        assert report.last_win_rate == pytest.approx(100.0)
        assert report.last_expectancy == pytest.approx(10.0)

    def test_profit_factor_all_wins(self, tmp_path):
        """全勝の場合 profit_factor は None（分母がゼロ）。"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(15):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 10.0)
        report = get_rolling_report(window=10, db_path=db)
        # all wins → no losses → gross_loss=0 → profit_factor=None
        assert report.last_profit_factor is None


# ── symbol filter ─────────────────────────────────────────────────────

class TestSymbolFilter:
    def test_symbol_filter_excludes_others(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(5):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 10.0, "USD/JPY")
            for i in range(5):
                _insert_trade(conn, f"2026-01-{i+6:02d}", "loss", -5.0, "EUR/USD")
        report = get_rolling_report(symbol="USD/JPY", window=10, db_path=db)
        assert report.total_trades == 5

    def test_no_symbol_returns_all(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(5):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 10.0, "USD/JPY")
            for i in range(5):
                _insert_trade(conn, f"2026-01-{i+6:02d}", "win", 10.0, "EUR/USD")
        report = get_rolling_report(symbol=None, window=10, db_path=db)
        assert report.total_trades == 10


# ── trend detection ────────────────────────────────────────────────

class TestTrendDetection:
    def test_insufficient_when_too_few_trades(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for i in range(15):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 10.0)
        report = get_rolling_report(window=10, db_path=db)
        assert report.trend == TREND_INSUFFICIENT

    def test_improving_trend(self, tmp_path):
        """最初は負け続き → 後半は勝ち続きで期待値が改善。"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # 20 losses first
            for i in range(20):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "loss", -5.0)
            # then 20 wins
            for i in range(20):
                _insert_trade(conn, f"2026-02-{i+1:02d}", "win", 10.0)
        report = get_rolling_report(window=10, db_path=db)
        assert report.trend == TREND_IMPROVING

    def test_declining_trend(self, tmp_path):
        """最初は勝ち続き → 後半は負け続きで期待値が悪化。"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # 20 wins first
            for i in range(20):
                _insert_trade(conn, f"2026-01-{i+1:02d}", "win", 10.0)
            # then 20 losses
            for i in range(20):
                _insert_trade(conn, f"2026-02-{i+1:02d}", "loss", -5.0)
        report = get_rolling_report(window=10, db_path=db)
        assert report.trend == TREND_DECLINING

    def test_stable_trend(self, tmp_path):
        """一定の成績が続く → stable。"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # 40 trades alternating win/loss, consistent expectancy
            for i in range(40):
                outcome = "win" if i % 2 == 0 else "loss"
                pnl = 5.0 if outcome == "win" else -4.0
                _insert_trade(conn, f"2026-01-{i+1:02d} 10:00:00", outcome, pnl)
        report = get_rolling_report(window=10, db_path=db)
        assert report.trend == TREND_STABLE
