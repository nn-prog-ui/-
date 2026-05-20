"""tests/test_pattern_recognition.py — Phase 49: トレードパターン認識テスト"""
from __future__ import annotations

import pytest

from app.scripts.pattern_recognition import (
    PatternReport,
    _make_cluster,
    _rsi_bucket,
    _session_label,
    get_pattern_report,
)


def _insert_trade(conn, created_at, symbol, human_action, outcome, pnl_pips,
                  score=3, rsi=50.0, daily_trend="上昇", h4_trend="上昇", signal="BUY"):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, signal, human_action, outcome, pnl_pips,
         score, rsi, daily_trend, h4_trend, "上昇", 0),
    )


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


# ── _rsi_bucket ────────────────────────────────────────────────────

class TestRsiBucket:
    def test_none(self):
        assert _rsi_bucket(None) == "不明"

    def test_oversold(self):
        assert _rsi_bucket(20.0) == "売られ過ぎ (<30)"

    def test_boundary_30(self):
        assert _rsi_bucket(30.0) == "30–40"

    def test_mid_range(self):
        assert _rsi_bucket(55.0) == "50–60"

    def test_overbought(self):
        assert _rsi_bucket(75.0) == "買われ過ぎ (≥70)"

    def test_boundary_70(self):
        assert _rsi_bucket(70.0) == "買われ過ぎ (≥70)"


# ── _session_label ─────────────────────────────────────────────────

class TestSessionLabel:
    def test_tokyo_morning(self):
        # UTC 01:00 → JST 10:00 → 東京午後
        assert _session_label("2024-01-01 01:00:00") == "東京午後 (10–16時)"

    def test_tokyo_morning_early(self):
        # UTC 22:00 → JST 07:00 → 東京午前
        assert _session_label("2024-01-01 22:00:00") == "東京午前 (7–10時)"

    def test_european(self):
        # UTC 08:00 → JST 17:00 → 欧州
        assert _session_label("2024-01-01 08:00:00") == "欧州 (16–22時)"

    def test_ny(self):
        # UTC 14:00 → JST 23:00 → NY
        assert _session_label("2024-01-01 14:00:00") == "NY (22–24時)"

    def test_midnight(self):
        # UTC 18:00 → JST 03:00 → 深夜
        assert _session_label("2024-01-01 18:00:00") == "深夜 (0–7時)"

    def test_invalid_format(self):
        assert _session_label("invalid") == "不明"


# ── _make_cluster ──────────────────────────────────────────────────

class TestMakeCluster:
    def _row(self, outcome, pnl_pips):
        return {"outcome": outcome, "pnl_pips": pnl_pips}

    def test_all_wins(self):
        rows = [self._row("win", 10.0), self._row("win", 20.0)]
        c = _make_cluster("buy", "BUY", "signal", rows)
        assert c.win_count == 2
        assert c.loss_count == 0
        assert c.win_rate == 100.0
        assert c.total_pips == 30.0

    def test_profit_factor(self):
        rows = [self._row("win", 30.0), self._row("loss", -10.0)]
        c = _make_cluster("k", "l", "cat", rows)
        assert c.profit_factor == pytest.approx(3.0)

    def test_all_losses_pf_zero(self):
        # 勝ちpips=0、負けpips>0 のとき PF = 0.0
        rows = [self._row("loss", -10.0)]
        c = _make_cluster("k", "l", "cat", rows)
        assert c.profit_factor == pytest.approx(0.0)

    def test_empty(self):
        c = _make_cluster("k", "l", "cat", [])
        assert c.trades == 0
        assert c.win_rate is None


# ── get_pattern_report ─────────────────────────────────────────────

class TestGetPatternReport:
    def test_empty_db(self, tmp_path):
        db = _make_db(tmp_path)
        report = get_pattern_report(db_path=db)
        assert isinstance(report, PatternReport)
        assert report.total_closed == 0
        assert report.by_signal == []

    def test_by_signal_clusters(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0, signal="BUY")
            _insert_trade(conn, "2024-01-02 10:00:00", "USD/JPY", "buy_approved", "loss", -5.0, signal="BUY")
            _insert_trade(conn, "2024-01-03 10:00:00", "USD/JPY", "sell_approved", "win", 8.0, signal="SELL")

        report = get_pattern_report(db_path=db)
        assert report.total_closed == 3
        signals = {c.label: c for c in report.by_signal}
        assert "BUY" in signals
        assert signals["BUY"].trades == 2

    def test_by_rsi_buckets(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0, rsi=25.0)
            _insert_trade(conn, "2024-01-02 10:00:00", "USD/JPY", "buy_approved", "win", 10.0, rsi=55.0)
            _insert_trade(conn, "2024-01-03 10:00:00", "USD/JPY", "buy_approved", "loss", -5.0, rsi=55.0)

        report = get_pattern_report(db_path=db)
        labels = {c.label for c in report.by_rsi}
        assert "売られ過ぎ (<30)" in labels
        assert "50–60" in labels

    def test_by_trend_clusters(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0,
                          daily_trend="上昇", h4_trend="上昇")
            _insert_trade(conn, "2024-01-02 10:00:00", "USD/JPY", "buy_approved", "loss", -5.0,
                          daily_trend="下降", h4_trend="下降")

        report = get_pattern_report(db_path=db)
        labels = {c.label for c in report.by_trend}
        assert "上昇 / 上昇" in labels
        assert "下降 / 下降" in labels

    def test_by_score_clusters(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0, score=5)
            _insert_trade(conn, "2024-01-02 10:00:00", "USD/JPY", "buy_approved", "loss", -5.0, score=1)

        report = get_pattern_report(db_path=db)
        labels = {c.label for c in report.by_score}
        assert "スコア 5" in labels
        assert "スコア 1" in labels

    def test_symbol_filter(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0)
            _insert_trade(conn, "2024-01-02 10:00:00", "EUR/USD", "buy_approved", "win", 20.0)

        report = get_pattern_report(symbol="USD/JPY", db_path=db)
        assert report.total_closed == 1

    def test_open_trades_excluded(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 10:00:00", "USD/JPY", "buy_approved", "win", 10.0)
            conn.execute(
                """INSERT INTO approval_history
                   (created_at, symbol, signal, human_action, outcome, pnl_pips,
                    score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("2024-01-02 10:00:00", "USD/JPY", "BUY", "buy_approved", None, None,
                 3, 50.0, "上昇", "上昇", "上昇", 0),
            )

        report = get_pattern_report(db_path=db)
        assert report.total_closed == 1

    def test_by_session_clusters(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            # UTC 08:00 → JST 17:00 → 欧州
            _insert_trade(conn, "2024-01-01 08:00:00", "USD/JPY", "buy_approved", "win", 10.0)
            # UTC 01:00 → JST 10:00 → 東京午後
            _insert_trade(conn, "2024-01-02 01:00:00", "USD/JPY", "buy_approved", "loss", -5.0)

        report = get_pattern_report(db_path=db)
        labels = {c.label for c in report.by_session}
        assert "欧州 (16–22時)" in labels
        assert "東京午後 (10–16時)" in labels

    def test_trend_sorted_by_trades_desc(self, tmp_path):
        db = _make_db(tmp_path)
        from app.database.db import get_db
        with get_db(db) as conn:
            for i in range(3):
                _insert_trade(conn, f"2024-01-0{i+1} 10:00:00", "USD/JPY",
                              "buy_approved", "win", 10.0, daily_trend="上昇", h4_trend="上昇")
            _insert_trade(conn, "2024-01-04 10:00:00", "USD/JPY",
                          "sell_approved", "loss", -5.0, daily_trend="下降", h4_trend="下降")

        report = get_pattern_report(db_path=db)
        assert report.by_trend[0].trades >= report.by_trend[-1].trades
