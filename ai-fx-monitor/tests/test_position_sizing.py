"""tests/test_position_sizing.py — Phase 51: ポジションサイジング計算機テスト"""
from __future__ import annotations

import pytest

from app.scripts.position_sizing import (
    SizingInput,
    SizingResult,
    _round_lot,
    calculate_sizing,
    get_historical_stats,
)


def _inp(**kwargs) -> SizingInput:
    defaults = dict(
        balance=100_000,
        risk_pct=1.0,
        stop_pips=20,
        pip_value=1_000,
        win_rate=55,
        avg_win_pips=20,
        avg_loss_pips=10,
        min_lot=0.01,
        lot_step=0.01,
    )
    defaults.update(kwargs)
    return SizingInput(**defaults)


def _make_db(tmp_path):
    from app.database.db import init_db
    db = tmp_path / "test.db"
    init_db(db)
    return db


# ── _round_lot ────────────────────────────────────────────────────

class TestRoundLot:
    def test_exact_step(self):
        assert _round_lot(1.0, 0.01, 0.01) == pytest.approx(1.0)

    def test_rounds_down(self):
        assert _round_lot(1.059, 0.01, 0.01) == pytest.approx(1.05)

    def test_below_min_returns_min(self):
        assert _round_lot(0.001, 0.01, 0.01) == pytest.approx(0.01)

    def test_invalid_step_uses_default(self):
        result = _round_lot(1.0, 0.01, 0.0)
        assert result >= 0.01


# ── calculate_sizing: 固定リスク法 ────────────────────────────────

class TestFixedRisk:
    def test_standard_case(self):
        # lot = (100000 × 1%) / (20 × 1000) = 1000 / 20000 = 0.05
        r = calculate_sizing(_inp())
        assert r.fixed_risk_lot == pytest.approx(0.05)

    def test_risk_amount(self):
        r = calculate_sizing(_inp(balance=100_000, risk_pct=2.0))
        assert r.fixed_risk_amount == pytest.approx(2_000.0)

    def test_higher_risk_larger_lot(self):
        r1 = calculate_sizing(_inp(risk_pct=1.0))
        r2 = calculate_sizing(_inp(risk_pct=2.0))
        assert r2.fixed_risk_lot > r1.fixed_risk_lot

    def test_wider_stop_smaller_lot(self):
        r1 = calculate_sizing(_inp(stop_pips=10))
        r2 = calculate_sizing(_inp(stop_pips=40))
        assert r1.fixed_risk_lot > r2.fixed_risk_lot

    def test_returns_sizing_result(self):
        r = calculate_sizing(_inp())
        assert isinstance(r, SizingResult)


# ── calculate_sizing: ケリー基準 ─────────────────────────────────

class TestKellyCriterion:
    def test_positive_kelly_when_edge_exists(self):
        # p=0.55, R=2.0 → f* = 0.55 - 0.45/2.0 = 0.325
        r = calculate_sizing(_inp(win_rate=55, avg_win_pips=20, avg_loss_pips=10))
        assert r.kelly_fraction is not None
        assert r.kelly_fraction == pytest.approx(0.55 - 0.45 / 2.0, abs=0.001)

    def test_negative_kelly_when_no_edge(self):
        # p=0.4, R=1.0 → f* = 0.4 - 0.6/1.0 = -0.2 (負)
        r = calculate_sizing(_inp(win_rate=40, avg_win_pips=10, avg_loss_pips=10))
        assert r.kelly_fraction is not None
        assert r.kelly_fraction < 0
        assert r.kelly_grade == "負の期待値"

    def test_half_kelly_is_half_of_kelly(self):
        r = calculate_sizing(_inp(win_rate=60, avg_win_pips=20, avg_loss_pips=10))
        if r.kelly_lot is not None and r.half_kelly_lot is not None:
            assert r.half_kelly_lot <= r.kelly_lot

    def test_kelly_grade_good_range(self):
        # p=0.55, R=20/15≈1.333 → f* = 0.55 - 0.45/1.333 ≈ 0.2125 → "適正"
        r = calculate_sizing(_inp(win_rate=55, avg_win_pips=20, avg_loss_pips=15))
        assert r.kelly_fraction is not None
        assert 0.1 < r.kelly_fraction < 0.25
        assert r.kelly_grade == "適正"

    def test_high_kelly_grade_excessive(self):
        # p=0.8, R=3 → f* = 0.8 - 0.2/3 ≈ 0.73 > 0.25 → "過大"
        r = calculate_sizing(_inp(win_rate=80, avg_win_pips=30, avg_loss_pips=10))
        assert r.kelly_grade == "過大"


# ── calculate_sizing: 期待値・警告 ───────────────────────────────

class TestExpectancyAndWarnings:
    def test_expectancy_positive(self):
        # E = 0.55*20 - 0.45*10 = 11 - 4.5 = 6.5
        r = calculate_sizing(_inp(win_rate=55, avg_win_pips=20, avg_loss_pips=10))
        assert r.expectancy_pips == pytest.approx(6.5)

    def test_payoff_ratio(self):
        r = calculate_sizing(_inp(avg_win_pips=20, avg_loss_pips=10))
        assert r.payoff_ratio == pytest.approx(2.0)

    def test_high_risk_warning(self):
        r = calculate_sizing(_inp(risk_pct=10.0))
        assert any("10" in w or "%" in w for w in r.warnings)

    def test_no_warnings_on_normal_input(self):
        r = calculate_sizing(_inp(risk_pct=1.0, win_rate=55, avg_win_pips=20, avg_loss_pips=10))
        risk_warnings = [w for w in r.warnings if "リスク" in w and "%" in w]
        assert len(risk_warnings) == 0


# ── get_historical_stats ─────────────────────────────────────────

class TestGetHistoricalStats:
    def test_empty_db(self, tmp_path):
        db = _make_db(tmp_path)
        stats = get_historical_stats(db_path=db)
        assert stats["trades"] == 0
        assert stats["win_rate"] is None
        assert stats["avg_win_pips"] is None
        assert stats["avg_loss_pips"] is None

    def test_with_data(self, tmp_path):
        from app.database.db import get_db
        db = _make_db(tmp_path)
        with get_db(db) as conn:
            for outcome, pnl in [("win", 20.0), ("loss", -10.0), ("win", 15.0)]:
                conn.execute(
                    """INSERT INTO approval_history
                       (created_at, symbol, signal, human_action, outcome, pnl_pips,
                        score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("2026-01-01", "USD/JPY", "BUY", "buy_approved",
                     outcome, pnl, 3, 50.0, "上昇", "上昇", "上昇", 0),
                )
        stats = get_historical_stats(db_path=db)
        assert stats["trades"] == 3
        assert stats["win_rate"] == pytest.approx(2 / 3 * 100, abs=0.1)
        assert stats["avg_win_pips"] == pytest.approx(17.5, abs=0.1)
        assert stats["avg_loss_pips"] == pytest.approx(10.0, abs=0.1)
