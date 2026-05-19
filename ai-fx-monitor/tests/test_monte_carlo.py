"""tests/test_monte_carlo.py — Phase 43: モンテカルロ分析テスト"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.scripts.monte_carlo import (
    DEFAULT_N_SIMULATIONS,
    DEFAULT_RUIN_THRESHOLD,
    MonteCarloResult,
    PercentileStats,
    _assess,
    _cumulative,
    _max_drawdown,
    _percentile_stats,
    _wilson_ci,
    get_pnl_pips_from_db,
    run_monte_carlo,
)


# ── _cumulative ───────────────────────────────────────────────

class TestCumulative:
    def test_empty(self):
        assert _cumulative([]) == []

    def test_single(self):
        assert _cumulative([5.0]) == [5.0]

    def test_positive(self):
        result = _cumulative([1.0, 2.0, 3.0])
        assert result == [1.0, 3.0, 6.0]

    def test_mixed(self):
        result = _cumulative([10.0, -5.0, 3.0])
        assert result == [10.0, 5.0, 8.0]


# ── _max_drawdown ─────────────────────────────────────────────

class TestMaxDrawdown:
    def test_empty(self):
        assert _max_drawdown([]) == 0.0

    def test_all_positive_no_dd(self):
        assert _max_drawdown([1.0, 2.0, 3.0, 4.0]) == 0.0

    def test_simple_drawdown(self):
        # ピーク10→5、DD=-5
        dd = _max_drawdown([5.0, 10.0, 5.0])
        assert dd == -5.0

    def test_multiple_drawdowns_picks_largest(self):
        # ピーク10から最終2への下落がグローバル最大DD
        dd = _max_drawdown([0.0, 10.0, 5.0, 8.0, 2.0])
        assert dd == -8.0

    def test_only_decline(self):
        dd = _max_drawdown([10.0, 5.0, 0.0])
        assert dd == -10.0

    def test_recovery_after_drawdown(self):
        dd = _max_drawdown([0.0, 10.0, 0.0, 20.0])
        assert dd == -10.0


# ── _percentile_stats ─────────────────────────────────────────

class TestPercentileStats:
    def test_single_value(self):
        ps = _percentile_stats([5.0])
        assert ps.p50 == 5.0
        assert ps.minimum == 5.0
        assert ps.maximum == 5.0
        assert ps.mean == 5.0

    def test_median_of_odd(self):
        ps = _percentile_stats([1.0, 3.0, 5.0, 7.0, 9.0])
        assert ps.p50 == 5.0

    def test_mean_correct(self):
        ps = _percentile_stats([10.0, 20.0, 30.0])
        assert ps.mean == 20.0

    def test_min_max(self):
        ps = _percentile_stats([-10.0, 0.0, 10.0, 20.0])
        assert ps.minimum == -10.0
        assert ps.maximum == 20.0

    def test_p5_p95_ordering(self):
        values = list(range(1, 101))
        ps = _percentile_stats(values)
        assert ps.p5 < ps.p25 < ps.p50 < ps.p75 < ps.p95


# ── _wilson_ci ────────────────────────────────────────────────

class TestWilsonCi:
    def test_zero_n(self):
        lo, hi = _wilson_ci(0, 0)
        assert lo == 0.0
        assert hi == 0.0

    def test_all_wins(self):
        lo, hi = _wilson_ci(100, 100)
        assert hi <= 100.0
        assert lo > 90.0  # 100%に近い

    def test_all_losses(self):
        lo, hi = _wilson_ci(0, 100)
        assert lo == 0.0
        assert hi < 5.0

    def test_fifty_percent(self):
        lo, hi = _wilson_ci(500, 1000)
        assert lo < 50.0 < hi
        assert abs((lo + hi) / 2 - 50.0) < 2.0  # 中心が50%付近

    def test_returns_tuple_of_floats(self):
        lo, hi = _wilson_ci(30, 50)
        assert isinstance(lo, float)
        assert isinstance(hi, float)

    def test_lower_le_upper(self):
        lo, hi = _wilson_ci(40, 100)
        assert lo <= hi


# ── run_monte_carlo — 基本動作 ────────────────────────────────

class TestRunMonteCarlo:
    PIPS = [10.0, -5.0, 8.0, -3.0, 12.0, -7.0, 6.0, -4.0, 9.0, -2.0]

    def test_returns_monte_carlo_result(self):
        r = run_monte_carlo(self.PIPS, n_simulations=100, seed=42)
        assert isinstance(r, MonteCarloResult)

    def test_n_trades_matches_input(self):
        r = run_monte_carlo(self.PIPS, n_simulations=100, seed=42)
        assert r.n_trades == len(self.PIPS)

    def test_n_simulations_stored(self):
        r = run_monte_carlo(self.PIPS, n_simulations=200, seed=42)
        assert r.n_simulations == 200

    def test_final_pips_is_percentile_stats(self):
        r = run_monte_carlo(self.PIPS, n_simulations=100, seed=42)
        assert isinstance(r.final_pips, PercentileStats)

    def test_max_drawdown_is_percentile_stats(self):
        r = run_monte_carlo(self.PIPS, n_simulations=100, seed=42)
        assert isinstance(r.max_drawdown, PercentileStats)

    def test_ruin_probability_in_range(self):
        r = run_monte_carlo(self.PIPS, n_simulations=100, seed=42)
        assert 0.0 <= r.ruin_probability <= 1.0

    def test_profit_probability_in_range(self):
        r = run_monte_carlo(self.PIPS, n_simulations=100, seed=42)
        assert 0.0 <= r.profit_probability <= 1.0

    def test_win_rate_ci_set(self):
        r = run_monte_carlo(self.PIPS, n_simulations=100, seed=42)
        assert r.win_rate_ci_lower is not None
        assert r.win_rate_ci_upper is not None

    def test_assessment_not_empty(self):
        r = run_monte_carlo(self.PIPS, n_simulations=100, seed=42)
        assert r.assessment != ""

    def test_empty_trades_returns_no_data(self):
        r = run_monte_carlo([], n_simulations=100)
        assert r.n_trades == 0
        assert "ありません" in r.assessment

    def test_all_wins_high_profit_probability(self):
        all_wins = [10.0] * 50
        r = run_monte_carlo(all_wins, n_simulations=200, seed=42)
        assert r.profit_probability == 1.0

    def test_all_losses_low_profit_probability(self):
        all_losses = [-10.0] * 50
        r = run_monte_carlo(all_losses, n_simulations=200, seed=42)
        assert r.profit_probability == 0.0

    def test_ruin_threshold_respected(self):
        # 全部勝ちなら破産確率0
        all_wins = [10.0] * 20
        r = run_monte_carlo(all_wins, n_simulations=200, ruin_threshold=-200.0, seed=42)
        assert r.ruin_probability == 0.0

    def test_seed_reproducible(self):
        r1 = run_monte_carlo(self.PIPS, n_simulations=100, seed=123)
        r2 = run_monte_carlo(self.PIPS, n_simulations=100, seed=123)
        assert r1.ruin_probability == r2.ruin_probability
        assert r1.profit_probability == r2.profit_probability

    def test_max_drawdown_always_nonpositive(self):
        r = run_monte_carlo(self.PIPS, n_simulations=100, seed=42)
        assert r.max_drawdown.maximum <= 0.0

    def test_raw_win_rate_calculated(self):
        # PIPS に win が5件、loss が5件
        r = run_monte_carlo(self.PIPS, n_simulations=10, seed=42)
        assert r.raw_win_rate == 50.0


# ── _assess ───────────────────────────────────────────────────

class TestAssess:
    def _make_result(self, **kwargs) -> MonteCarloResult:
        base = dict(
            n_trades=10,
            n_simulations=1000,
            ruin_threshold=-200.0,
            raw_win_rate=50.0,
            raw_total_pips=20.0,
            raw_max_drawdown=-30.0,
            ruin_probability=0.03,
            profit_probability=0.75,
        )
        base.update(kwargs)
        return MonteCarloResult(**base)

    def test_low_ruin_label(self):
        r = self._make_result(ruin_probability=0.03)
        text = _assess(r)
        assert "低" in text

    def test_medium_ruin_label(self):
        r = self._make_result(ruin_probability=0.12)
        text = _assess(r)
        assert "中" in text

    def test_high_ruin_label(self):
        r = self._make_result(ruin_probability=0.30)
        text = _assess(r)
        assert "高" in text

    def test_high_profit_label(self):
        r = self._make_result(profit_probability=0.80)
        text = _assess(r)
        assert "高" in text

    def test_low_profit_label(self):
        r = self._make_result(profit_probability=0.40)
        text = _assess(r)
        assert "低" in text

    def test_parts_joined_by_slash(self):
        r = self._make_result()
        text = _assess(r)
        assert "/" in text


# ── get_pnl_pips_from_db ─────────────────────────────────────

class TestGetPnlPipsFromDb:
    def test_returns_list(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "mc_test.db"
        init_db(db)
        result = get_pnl_pips_from_db(db_path=db)
        assert isinstance(result, list)

    def test_empty_db_returns_empty(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "mc_test.db"
        init_db(db)
        result = get_pnl_pips_from_db(db_path=db)
        assert result == []

    def test_filters_by_symbol(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "mc_test.db"
        init_db(db)
        # 2件挿入（異なるシンボル）
        with get_db(db) as conn:
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, "
                "is_dummy_data, outcome, pnl_pips) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2024-01-01 00:00:00", "EUR/USD", "BUY", "buy_approved", 1, "win", 10.0),
            )
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, "
                "is_dummy_data, outcome, pnl_pips) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2024-01-02 00:00:00", "USD/JPY", "SELL", "sell_approved", 1, "loss", -5.0),
            )
        result = get_pnl_pips_from_db(symbol="EUR/USD", db_path=db)
        assert result == [10.0]

    def test_filters_backtest_only(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "mc_test.db"
        init_db(db)
        with get_db(db) as conn:
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, "
                "is_dummy_data, outcome, pnl_pips) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2024-01-01 00:00:00", "EUR/USD", "BUY", "buy_approved", 1, "win", 10.0),
            )
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, "
                "is_dummy_data, outcome, pnl_pips) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2024-01-02 00:00:00", "EUR/USD", "BUY", "buy_approved", 0, "win", 20.0),
            )
        backtest_only = get_pnl_pips_from_db(is_simulation=True, db_path=db)
        assert backtest_only == [10.0]
        real_only = get_pnl_pips_from_db(is_simulation=False, db_path=db)
        assert real_only == [20.0]

    def test_excludes_open_trades(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "mc_test.db"
        init_db(db)
        with get_db(db) as conn:
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, "
                "is_dummy_data, outcome, pnl_pips) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2024-01-01 00:00:00", "EUR/USD", "BUY", "buy_approved", 1, "open", None),
            )
        result = get_pnl_pips_from_db(db_path=db)
        assert result == []


# ── API エンドポイント ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_monte_carlo_api_no_data():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    with patch("app.web.routes.get_pnl_pips_from_db", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/monte-carlo")
    data = res.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_monte_carlo_api_with_data():
    pips = [10.0, -5.0, 8.0, -3.0, 12.0] * 10
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    with patch("app.web.routes.get_pnl_pips_from_db", return_value=pips):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/monte-carlo?n_simulations=100")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["n_trades"] == len(pips)
    assert "final_pips" in data
    assert "max_drawdown" in data
    assert "ruin_probability" in data
    assert "assessment" in data


@pytest.mark.asyncio
async def test_monte_carlo_api_response_fields():
    pips = [5.0, -3.0] * 20
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    with patch("app.web.routes.get_pnl_pips_from_db", return_value=pips):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/monte-carlo?n_simulations=50")
    data = res.json()
    for key in ("profit_probability", "win_rate_ci_lower", "win_rate_ci_upper",
                "raw_win_rate", "raw_total_pips", "raw_max_drawdown"):
        assert key in data


@pytest.mark.asyncio
async def test_monte_carlo_api_clamps_simulations():
    pips = [1.0] * 10
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    with patch("app.web.routes.get_pnl_pips_from_db", return_value=pips):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/monte-carlo?n_simulations=99999")
    data = res.json()
    assert data["ok"] is True
    assert data["n_simulations"] <= 5000


# ── バックテストページに MC セクションがあること ────────────────

@pytest.mark.asyncio
async def test_backtest_page_has_monte_carlo_section():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/backtest")
    assert res.status_code == 200
    assert "モンテカルロ" in res.text
    assert "mc-run-btn" in res.text
    assert "破産" in res.text
