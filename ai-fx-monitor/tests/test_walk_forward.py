"""tests/test_walk_forward.py — Phase 42: ウォークフォワード分析テスト"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from app.scripts.walk_forward import (
    WFWindow,
    WalkForwardResult,
    _assess,
    _fill_window_stats,
    _run_slice,
    run_walk_forward,
)


# ── _fill_window_stats ────────────────────────────────────────

class TestFillWindowStats:
    def _make_window(self, **kwargs) -> WFWindow:
        base = dict(
            window_num=1,
            is_start_bar=0, is_end_bar=350,
            oos_start_bar=350, oos_end_bar=500,
        )
        base.update(kwargs)
        return WFWindow(**base)

    def test_win_rate_calculated(self):
        w = self._make_window(is_wins=6, is_losses=4, is_total_pips=50.0)
        _fill_window_stats(w)
        assert w.is_win_rate == 60.0

    def test_win_rate_none_when_no_trades(self):
        w = self._make_window()
        _fill_window_stats(w)
        assert w.is_win_rate is None
        assert w.oos_win_rate is None

    def test_oos_win_rate_calculated(self):
        w = self._make_window(oos_wins=3, oos_losses=2, oos_total_pips=20.0)
        _fill_window_stats(w)
        assert w.oos_win_rate == 60.0

    def test_avg_pips_calculated(self):
        w = self._make_window(is_wins=4, is_losses=1, is_total_pips=25.0)
        _fill_window_stats(w)
        assert w.is_avg_pips == 5.0

    def test_oos_avg_pips_calculated(self):
        w = self._make_window(oos_wins=2, oos_losses=2, oos_total_pips=10.0)
        _fill_window_stats(w)
        assert w.oos_avg_pips == 2.5

    def test_overfitting_score_is_is_minus_oos(self):
        w = self._make_window(
            is_wins=7, is_losses=3, is_total_pips=60.0,
            oos_wins=5, oos_losses=5, oos_total_pips=10.0,
        )
        _fill_window_stats(w)
        # IS勝率=70%, OOS勝率=50%, スコア=20%pt
        assert w.overfitting_score == 20.0

    def test_overfitting_score_none_when_missing_data(self):
        w = self._make_window(is_wins=5, is_losses=5, is_total_pips=0.0)
        _fill_window_stats(w)
        assert w.overfitting_score is None  # OOS なし

    def test_robustness_ratio_oos_over_is(self):
        w = self._make_window(
            is_wins=6, is_losses=4, is_total_pips=100.0,
            oos_wins=3, oos_losses=2, oos_total_pips=80.0,
        )
        _fill_window_stats(w)
        assert w.robustness_ratio == 0.8

    def test_robustness_ratio_none_when_is_pips_zero(self):
        w = self._make_window(
            is_wins=5, is_losses=5, is_total_pips=0.0,
            oos_wins=3, oos_losses=2, oos_total_pips=20.0,
        )
        _fill_window_stats(w)
        assert w.robustness_ratio is None

    def test_win_rate_rounding(self):
        w = self._make_window(is_wins=2, is_losses=1, is_total_pips=10.0)
        _fill_window_stats(w)
        assert w.is_win_rate == 66.7


# ── _assess ───────────────────────────────────────────────────

class TestAssess:
    def _make_result(self, **kwargs) -> WalkForwardResult:
        base = dict(
            symbol="EUR/USD",
            n_windows=5, is_ratio=0.7, window_bars=500,
            step=24, total_data_bars=5000,
        )
        base.update(kwargs)
        return WalkForwardResult(**base)

    def test_low_overfitting_label(self):
        r = self._make_result(avg_overfitting_score=3.0)
        text = _assess(r)
        assert "低" in text

    def test_medium_overfitting_label(self):
        r = self._make_result(avg_overfitting_score=10.0)
        text = _assess(r)
        assert "中" in text

    def test_high_overfitting_label(self):
        r = self._make_result(avg_overfitting_score=20.0)
        text = _assess(r)
        assert "高" in text

    def test_high_robustness_label(self):
        r = self._make_result(avg_overfitting_score=3.0, avg_robustness_ratio=0.9)
        text = _assess(r)
        assert "高" in text

    def test_low_robustness_label(self):
        r = self._make_result(avg_overfitting_score=3.0, avg_robustness_ratio=0.3)
        text = _assess(r)
        assert "低" in text

    def test_good_oos_winrate_label(self):
        r = self._make_result(avg_oos_win_rate=58.0)
        text = _assess(r)
        assert "良好" in text

    def test_poor_oos_winrate_label(self):
        r = self._make_result(avg_oos_win_rate=44.0)
        text = _assess(r)
        assert "低調" in text

    def test_no_data_returns_insufficient_message(self):
        r = self._make_result()
        text = _assess(r)
        assert "不足" in text

    def test_multiple_parts_joined_by_slash(self):
        r = self._make_result(avg_overfitting_score=3.0, avg_oos_win_rate=56.0)
        text = _assess(r)
        assert "/" in text


# ── run_walk_forward — 無効シンボル ──────────────────────────

def test_run_walk_forward_invalid_symbol():
    with pytest.raises(ValueError):
        run_walk_forward("INVALID_PAIR")


# ── run_walk_forward — データ不足 ────────────────────────────

def test_run_walk_forward_insufficient_data():
    tiny_df = pd.DataFrame(
        {"open": [1.1], "high": [1.11], "low": [1.09], "close": [1.1], "volume": [100]},
        index=pd.date_range("2020-01-01", periods=1, freq="h"),
    )
    with patch("app.scripts.walk_forward.load_or_generate", return_value=(tiny_df, False)):
        result = run_walk_forward("EUR/USD", n_windows=5, window_bars=500)
    assert "不足" in result.assessment
    assert result.windows == []


# ── run_walk_forward — モックデータで正常実行 ─────────────────

def _make_dummy_df(n: int = 8000) -> pd.DataFrame:
    import numpy as np
    rng = np.random.default_rng(42)
    close = 1.1 + rng.normal(0, 0.001, n).cumsum()
    opens = close - rng.uniform(0, 0.0005, n)
    highs = close + rng.uniform(0, 0.001, n)
    lows  = close - rng.uniform(0, 0.001, n)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": close, "volume": 100},
        index=pd.date_range("2019-01-01", periods=n, freq="h"),
    )


class TestRunWalkForwardMock:
    def setup_method(self):
        self.dummy_df = _make_dummy_df(8000)

    def test_returns_walk_forward_result(self):
        with patch("app.scripts.walk_forward.load_or_generate", return_value=(self.dummy_df, False)):
            result = run_walk_forward("EUR/USD", n_windows=3, window_bars=500, step=48, future_bars=50)
        assert isinstance(result, WalkForwardResult)

    def test_symbol_matches(self):
        with patch("app.scripts.walk_forward.load_or_generate", return_value=(self.dummy_df, False)):
            result = run_walk_forward("EUR/USD", n_windows=3, window_bars=500, step=48, future_bars=50)
        assert result.symbol == "EUR/USD"

    def test_total_data_bars_set(self):
        with patch("app.scripts.walk_forward.load_or_generate", return_value=(self.dummy_df, False)):
            result = run_walk_forward("EUR/USD", n_windows=3, window_bars=500, step=48, future_bars=50)
        assert result.total_data_bars == len(self.dummy_df)

    def test_windows_created(self):
        with patch("app.scripts.walk_forward.load_or_generate", return_value=(self.dummy_df, False)):
            result = run_walk_forward("EUR/USD", n_windows=3, window_bars=500, step=48, future_bars=50)
        assert len(result.windows) > 0
        assert len(result.windows) <= 3

    def test_windows_sorted_by_num(self):
        with patch("app.scripts.walk_forward.load_or_generate", return_value=(self.dummy_df, False)):
            result = run_walk_forward("EUR/USD", n_windows=3, window_bars=500, step=48, future_bars=50)
        nums = [w.window_num for w in result.windows]
        assert nums == sorted(nums)

    def test_is_end_before_oos_start(self):
        with patch("app.scripts.walk_forward.load_or_generate", return_value=(self.dummy_df, False)):
            result = run_walk_forward("EUR/USD", n_windows=3, window_bars=500, step=48, future_bars=50)
        for w in result.windows:
            assert w.is_end_bar == w.oos_start_bar

    def test_assessment_not_empty(self):
        with patch("app.scripts.walk_forward.load_or_generate", return_value=(self.dummy_df, False)):
            result = run_walk_forward("EUR/USD", n_windows=3, window_bars=500, step=48, future_bars=50)
        assert result.assessment != ""

    def test_params_stored(self):
        with patch("app.scripts.walk_forward.load_or_generate", return_value=(self.dummy_df, False)):
            result = run_walk_forward("EUR/USD", n_windows=3, is_ratio=0.7, window_bars=500, step=48, future_bars=50)
        assert result.n_windows == 3
        assert result.is_ratio == 0.7
        assert result.window_bars == 500


# ── API エンドポイント ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_walk_forward_api_no_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/walk-forward")
    data = res.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_walk_forward_api_invalid_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/walk-forward?symbol=INVALID_PAIR")
    data = res.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_walk_forward_api_valid_symbol():
    dummy_df = _make_dummy_df(8000)
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    with patch("app.scripts.walk_forward.load_or_generate", return_value=(dummy_df, False)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/walk-forward?symbol=EUR/USD&n_windows=2&window_bars=500&step=48&future_bars=50")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["symbol"] == "EUR/USD"
    assert "windows" in data
    assert "assessment" in data


@pytest.mark.asyncio
async def test_walk_forward_api_response_has_aggregates():
    dummy_df = _make_dummy_df(8000)
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    with patch("app.scripts.walk_forward.load_or_generate", return_value=(dummy_df, False)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/walk-forward?symbol=EUR/USD&n_windows=2&window_bars=500&step=48&future_bars=50")
    data = res.json()
    for key in ("avg_is_win_rate", "avg_oos_win_rate", "combined_oos_pips", "total_oos_trades"):
        assert key in data


# ── バックテストページに WF セクションがあること ────────────────

@pytest.mark.asyncio
async def test_backtest_page_has_walk_forward_section():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/backtest")
    assert res.status_code == 200
    assert "ウォークフォワード" in res.text
    assert "wf-run-btn" in res.text
    assert "過学習" in res.text
