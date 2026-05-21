"""tests/test_rr_analysis.py — Phase 57: R:R実績分析テスト"""
from __future__ import annotations

import pytest

from app.scripts.rr_analysis import (
    EXIT_EARLY,
    EXIT_HIT_SL,
    EXIT_HIT_TP,
    EXIT_UNKNOWN,
    HIT_TOLERANCE_PIPS,
    RRReport,
    get_rr_report,
    _pip_size,
)


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _insert_trade(
    conn,
    created_at,
    outcome,
    pnl_pips,
    symbol="USD/JPY",
    signal="BUY",
    entry_price=150.00,
    stop_loss=149.50,    # 50 pips risk for USD/JPY
    take_profit=151.00,  # 100 pips reward → R:R = 2.0
    exit_price=None,
):
    if exit_price is None:
        exit_price = take_profit if outcome == "win" else stop_loss
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            entry_price, stop_loss, take_profit, exit_price,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, signal,
         "buy_approved" if signal == "BUY" else "sell_approved",
         outcome, pnl_pips,
         entry_price, stop_loss, take_profit, exit_price,
         3, 50.0, "上昇", "上昇", "上昇", 0),
    )


# ── helpers ───────────────────────────────────────────────────────────

class TestPipSize:
    def test_jpy_pair(self):
        assert _pip_size("USD/JPY") == pytest.approx(0.01)

    def test_non_jpy_pair(self):
        assert _pip_size("EUR/USD") == pytest.approx(0.0001)

    def test_jpy_case_insensitive(self):
        assert _pip_size("usdjpy") == pytest.approx(0.01)


# ── empty DB ──────────────────────────────────────────────────────────

class TestEmptyDB:
    def test_empty_returns_zero(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_rr_report(db_path=db)
        assert report.total_trades == 0
        assert report.trades == []

    def test_empty_assessment(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_rr_report(db_path=db)
        assert "データがありません" in report.assessment


# ── trades without R:R data are excluded ────────────────────────────

class TestIncompleteDataExcluded:
    def test_trade_without_exit_price_excluded(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # no exit_price column — will be NULL
            conn.execute(
                """INSERT INTO approval_history
                   (created_at, symbol, signal, human_action, outcome, pnl_pips,
                    entry_price, stop_loss, take_profit,
                    score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("2026-01-01", "USD/JPY", "BUY", "buy_approved",
                 "win", 100.0, 150.0, 149.5, 151.0,
                 3, 50.0, "上昇", "上昇", "上昇", 0),
            )
        report = get_rr_report(db_path=db)
        assert report.total_trades == 0


# ── planned R:R calculation ──────────────────────────────────────────

class TestPlannedRR:
    def test_planned_rr_buy(self, tmp_path):
        """entry=150.00, SL=149.50, TP=151.00 → risk=50pips, reward=100pips → R:R=2.0"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 100.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=151.00)
        report = get_rr_report(db_path=db)
        assert report.total_trades == 1
        t = report.trades[0]
        assert t.planned_rr == pytest.approx(2.0, abs=0.01)
        assert t.planned_risk_pips == pytest.approx(50.0, abs=0.1)
        assert t.planned_reward_pips == pytest.approx(100.0, abs=0.1)

    def test_avg_planned_rr(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # R:R=2.0
            _insert_trade(conn, "2026-01-01", "win", 100.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=151.00)
            # R:R=1.0
            _insert_trade(conn, "2026-01-02", "loss", -50.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=150.50,
                          exit_price=149.50)
        report = get_rr_report(db_path=db)
        assert report.avg_planned_rr == pytest.approx(1.5, abs=0.01)


# ── actual R calculation ─────────────────────────────────────────────

class TestActualR:
    def test_actual_r_win(self, tmp_path):
        """pnl=100pips, risk=50pips → actual_R = 2.0"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 100.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=151.00)
        report = get_rr_report(db_path=db)
        assert report.trades[0].actual_r == pytest.approx(2.0, abs=0.01)

    def test_actual_r_loss(self, tmp_path):
        """pnl=-50pips, risk=50pips → actual_R = -1.0"""
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "loss", -50.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=149.50)
        report = get_rr_report(db_path=db)
        assert report.trades[0].actual_r == pytest.approx(-1.0, abs=0.01)

    def test_avg_actual_r(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 100.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=151.00)
            _insert_trade(conn, "2026-01-02", "loss", -50.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=149.50)
        report = get_rr_report(db_path=db)
        # (2.0 + -1.0) / 2 = 0.5
        assert report.avg_actual_r == pytest.approx(0.5, abs=0.01)


# ── exit type inference ──────────────────────────────────────────────

class TestExitType:
    def test_hit_tp_when_exit_near_tp(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 100.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=151.00)   # exactly TP
        report = get_rr_report(db_path=db)
        assert report.trades[0].exit_type == EXIT_HIT_TP
        assert report.tp_count == 1

    def test_hit_sl_when_exit_near_sl(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "loss", -50.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=149.50)   # exactly SL
        report = get_rr_report(db_path=db)
        assert report.trades[0].exit_type == EXIT_HIT_SL
        assert report.sl_count == 1

    def test_early_exit_when_not_near_tp_or_sl(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 30.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=150.30)   # nowhere near TP or SL
        report = get_rr_report(db_path=db)
        assert report.trades[0].exit_type == EXIT_EARLY
        assert report.early_count == 1

    def test_exit_type_counts(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 100.0,
                          exit_price=151.00)   # TP
            _insert_trade(conn, "2026-01-02", "loss", -50.0,
                          exit_price=149.50)   # SL
            _insert_trade(conn, "2026-01-03", "win", 20.0,
                          exit_price=150.20)   # early
        report = get_rr_report(db_path=db)
        assert report.tp_count == 1
        assert report.sl_count == 1
        assert report.early_count == 1


# ── per-outcome planned R:R ──────────────────────────────────────────

class TestPerOutcomeRR:
    def test_avg_planned_rr_wins_vs_losses(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            # wins: R:R=2.0
            _insert_trade(conn, "2026-01-01", "win", 100.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=151.00,
                          exit_price=151.00)
            # losses: R:R=1.0
            _insert_trade(conn, "2026-01-02", "loss", -50.0,
                          entry_price=150.00, stop_loss=149.50, take_profit=150.50,
                          exit_price=149.50)
        report = get_rr_report(db_path=db)
        assert report.avg_planned_rr_wins == pytest.approx(2.0, abs=0.01)
        assert report.avg_planned_rr_losses == pytest.approx(1.0, abs=0.01)


# ── histogram ────────────────────────────────────────────────────────

class TestHistogram:
    def test_histogram_labels_and_counts_same_length(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 100.0, exit_price=151.00)
        report = get_rr_report(db_path=db)
        assert len(report.hist_labels) == len(report.hist_counts)
        assert len(report.hist_labels) > 0

    def test_histogram_total_equals_trades(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 100.0, exit_price=151.00)
            _insert_trade(conn, "2026-01-02", "loss", -50.0, exit_price=149.50)
        report = get_rr_report(db_path=db)
        assert sum(report.hist_counts) == report.total_trades


# ── symbol filter ──────────────────────────────────────────────────────

class TestSymbolFilter:
    def test_filter_excludes_other_symbols(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 100.0,
                          symbol="USD/JPY", exit_price=151.00)
            _insert_trade(conn, "2026-01-02", "win", 10.0,
                          symbol="EUR/USD",
                          entry_price=1.1000, stop_loss=1.0990,
                          take_profit=1.1020, exit_price=1.1020)
        report = get_rr_report(symbol="USD/JPY", db_path=db)
        assert report.total_trades == 1
        assert report.trades[0].symbol == "USD/JPY"

    def test_no_filter_includes_all(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            _insert_trade(conn, "2026-01-01", "win", 100.0,
                          symbol="USD/JPY", exit_price=151.00)
            _insert_trade(conn, "2026-01-02", "win", 10.0,
                          symbol="EUR/USD",
                          entry_price=1.1000, stop_loss=1.0990,
                          take_profit=1.1020, exit_price=1.1020)
        report = get_rr_report(symbol=None, db_path=db)
        assert report.total_trades == 2
