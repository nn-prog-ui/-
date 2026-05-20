"""tests/test_multi_symbol.py — Phase 49: マルチシンボル比較分析テスト"""
from __future__ import annotations

import pytest

from app.scripts.multi_symbol import (
    MultiSymbolReport,
    _compute_symbol_stats,
    get_multi_symbol_report,
)


def _insert_trade(conn, created_at, symbol, human_action, outcome, pnl_pips, score=3, rsi=50.0):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            created_at, symbol,
            "BUY" if human_action == "buy_approved" else "SELL",
            human_action, outcome, pnl_pips,
            score, rsi, "上昇", "上昇", "上昇", 0,
        ),
    )


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


# ── _compute_symbol_stats ─────────────────────────────────────────

class TestComputeSymbolStats:
    def _row(self, human_action, outcome, pnl_pips, score=3, rsi=50.0):
        return {
            "human_action": human_action,
            "outcome": outcome,
            "pnl_pips": pnl_pips,
            "score": score,
            "rsi": rsi,
        }

    def test_empty_rows(self):
        s = _compute_symbol_stats([], "USD/JPY")
        assert s.trades == 0
        assert s.win_rate is None
        assert s.total_pips == 0.0

    def test_all_wins(self):
        rows = [self._row("buy_approved", "win", 10.0) for _ in range(3)]
        s = _compute_symbol_stats(rows, "USD/JPY")
        assert s.trades == 3
        assert s.win_count == 3
        assert s.loss_count == 0
        assert s.win_rate == 100.0
        assert s.total_pips == 30.0

    def test_mixed_outcomes(self):
        rows = [
            self._row("buy_approved", "win", 20.0),
            self._row("buy_approved", "loss", -10.0),
            self._row("sell_approved", "win", 15.0),
        ]
        s = _compute_symbol_stats(rows, "EUR/USD")
        assert s.trades == 3
        assert s.win_count == 2
        assert s.loss_count == 1
        assert s.win_rate == pytest.approx(66.7, abs=0.1)
        assert s.total_pips == pytest.approx(25.0)

    def test_profit_factor(self):
        rows = [
            self._row("buy_approved", "win", 30.0),
            self._row("buy_approved", "loss", -10.0),
        ]
        s = _compute_symbol_stats(rows, "GBP/JPY")
        assert s.profit_factor == pytest.approx(3.0)

    def test_open_trades_not_counted_in_closed(self):
        rows = [
            self._row("buy_approved", "win", 10.0),
            self._row("buy_approved", None, None),
        ]
        s = _compute_symbol_stats(rows, "USD/JPY")
        assert s.trades == 1
        assert s.open_count == 1

    def test_buy_sell_counts(self):
        rows = [
            self._row("buy_approved", "win", 10.0),
            self._row("buy_approved", "win", 10.0),
            self._row("sell_approved", "loss", -5.0),
        ]
        s = _compute_symbol_stats(rows, "USD/JPY")
        assert s.buy_count == 2
        assert s.sell_count == 1

    def test_avg_score_and_rsi(self):
        rows = [
            self._row("buy_approved", "win", 10.0, score=4, rsi=60.0),
            self._row("buy_approved", "loss", -5.0, score=2, rsi=40.0),
        ]
        s = _compute_symbol_stats(rows, "USD/JPY")
        assert s.avg_score == pytest.approx(3.0)
        assert s.avg_rsi == pytest.approx(50.0)


# ── get_multi_symbol_report ────────────────────────────────────────

class TestGetMultiSymbolReport:
    def test_empty_db(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_multi_symbol_report(db_path=db)
        assert isinstance(report, MultiSymbolReport)
        assert report.symbols == []
        assert report.total_trades == 0
        assert report.overall_win_rate is None

    def test_single_symbol(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0)
            _insert_trade(conn, "2024-01-02 10:00:00", "USD/JPY", "buy_approved", "loss", -5.0)

        report = get_multi_symbol_report(db_path=db)
        assert len(report.symbols) == 1
        s = report.symbols[0]
        assert s.symbol == "USD/JPY"
        assert s.trades == 2
        assert s.win_count == 1

    def test_multi_symbol_ranking(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 30.0)
            _insert_trade(conn, "2024-01-02 10:00:00", "EUR/USD", "buy_approved", "win", 10.0)
            _insert_trade(conn, "2024-01-03 10:00:00", "GBP/JPY", "sell_approved", "loss", -5.0)

        report = get_multi_symbol_report(sort_by="total_pips", db_path=db)
        assert len(report.symbols) == 3
        assert report.symbols[0].symbol == "USD/JPY"
        assert report.symbols[0].rank == 1
        assert report.symbols[-1].rank == 3

    def test_sort_by_win_rate(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 5.0)
            _insert_trade(conn, "2024-01-02 10:00:00", "EUR/USD", "buy_approved", "win", 10.0)
            _insert_trade(conn, "2024-01-03 10:00:00", "EUR/USD", "buy_approved", "loss", -10.0)

        report = get_multi_symbol_report(sort_by="win_rate", db_path=db)
        assert report.symbols[0].symbol == "USD/JPY"
        assert report.symbols[0].win_rate == 100.0

    def test_invalid_sort_by_defaults_to_total_pips(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0)

        report = get_multi_symbol_report(sort_by="invalid_key", db_path=db)
        assert report.sort_by == "total_pips"

    def test_overall_win_rate(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0)
            _insert_trade(conn, "2024-01-02 10:00:00", "EUR/USD", "buy_approved", "loss", -5.0)
            _insert_trade(conn, "2024-01-03 10:00:00", "GBP/JPY", "buy_approved", "win", 15.0)

        report = get_multi_symbol_report(db_path=db)
        assert report.total_trades == 3
        assert report.overall_win_rate == pytest.approx(66.7, abs=0.1)

    def test_skipped_trades_excluded(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0)
            conn.execute(
                """INSERT INTO approval_history
                   (created_at, symbol, signal, human_action, outcome, pnl_pips,
                    score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("2024-01-02 10:00:00", "USD/JPY", "BUY", "skipped", None, None,
                 3, 50.0, "上昇", "上昇", "上昇", 0),
            )

        report = get_multi_symbol_report(db_path=db)
        assert report.symbols[0].trades == 1
