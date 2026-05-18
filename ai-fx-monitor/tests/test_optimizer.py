"""tests/test_optimizer.py — Phase 36: 戦略パラメータ最適化テスト"""
import pytest
import pandas as pd
import numpy as np

from app.scripts.optimizer import (
    OptimizeParams,
    OptimizeResult,
    VALID_METRICS,
    MAX_COMBINATIONS,
    DEFAULT_MA_SHORT,
    DEFAULT_MA_LONG,
    DEFAULT_RSI_BUY_MAX,
    _analyze_with_params,
    _pip_size,
    _compute_score,
    optimize,
)
from app.strategy.rules import SIGNAL_BUY, SIGNAL_SELL, SIGNAL_SKIP


# ── ヘルパー ──────────────────────────────────────────────────
def _make_ohlcv(n: int, base: float = 150.0, trend: str = "up") -> pd.DataFrame:
    """シンプルなOHLCVデータを生成。trend='up'|'down'|'flat'"""
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    if trend == "up":
        close = base + np.arange(n) * 0.01
    elif trend == "down":
        close = base - np.arange(n) * 0.01
    else:
        close = np.full(n, base)
    df = pd.DataFrame({
        "open":   close - 0.005,
        "high":   close + 0.02,
        "low":    close - 0.02,
        "close":  close,
        "volume": np.ones(n) * 1000,
    }, index=idx)
    return df


def _make_df_daily(n: int, trend: str = "up") -> pd.DataFrame:
    return _make_ohlcv(n, base=150.0, trend=trend)


def _make_df_4h(n: int, trend: str = "up") -> pd.DataFrame:
    return _make_ohlcv(n, base=150.0, trend=trend)


def _make_df_1h(n: int, trend: str = "up") -> pd.DataFrame:
    return _make_ohlcv(n, base=150.0, trend=trend)


# ── OptimizeParams ──────────────────────────────────────────
class TestOptimizeParams:
    def test_default_values(self):
        p = OptimizeParams()
        assert p.ma_short == 20
        assert p.ma_long == 75
        assert p.rsi_buy_max == 70
        assert p.rsi_buy_min == 40
        assert p.rsi_sell_min == 30
        assert p.rsi_sell_max == 60

    def test_custom_values(self):
        p = OptimizeParams(ma_short=10, ma_long=50, rsi_buy_max=65)
        assert p.ma_short == 10
        assert p.ma_long == 50
        assert p.rsi_buy_max == 65


# ── OptimizeResult ──────────────────────────────────────────
class TestOptimizeResult:
    def test_closed_property(self):
        r = OptimizeResult(params=OptimizeParams(), symbol="USD/JPY", wins=5, losses=3)
        assert r.closed == 8

    def test_closed_zero(self):
        r = OptimizeResult(params=OptimizeParams(), symbol="USD/JPY")
        assert r.closed == 0

    def test_default_fields(self):
        r = OptimizeResult(params=OptimizeParams(), symbol="USD/JPY")
        assert r.total_pips == 0.0
        assert r.win_rate is None
        assert r.avg_pips is None
        assert r.trade_count == 0


# ── 定数 ────────────────────────────────────────────────────
class TestConstants:
    def test_valid_metrics(self):
        assert "win_rate" in VALID_METRICS
        assert "total_pips" in VALID_METRICS
        assert "avg_pips" in VALID_METRICS
        assert len(VALID_METRICS) == 3

    def test_max_combinations(self):
        assert MAX_COMBINATIONS == 200

    def test_default_grids_not_empty(self):
        assert len(DEFAULT_MA_SHORT) > 0
        assert len(DEFAULT_MA_LONG) > 0
        assert len(DEFAULT_RSI_BUY_MAX) > 0


# ── _pip_size ───────────────────────────────────────────────
class TestPipSize:
    def test_jpy_pair(self):
        assert _pip_size("USD/JPY") == 0.01

    def test_non_jpy_pair(self):
        assert _pip_size("EUR/USD") == 0.0001

    def test_jpy_uppercase(self):
        assert _pip_size("GBP/JPY") == 0.01


# ── _compute_score ──────────────────────────────────────────
class TestComputeScore:
    def _make_result(self, win_rate=60.0, total_pips=100.0, avg_pips=5.0):
        r = OptimizeResult(params=OptimizeParams(), symbol="USD/JPY",
                           win_rate=win_rate, total_pips=total_pips, avg_pips=avg_pips)
        return r

    def test_win_rate_metric(self):
        r = self._make_result(win_rate=65.0)
        assert _compute_score(r, "win_rate") == 65.0

    def test_total_pips_metric(self):
        r = self._make_result(total_pips=250.0)
        assert _compute_score(r, "total_pips") == 250.0

    def test_avg_pips_metric(self):
        r = self._make_result(avg_pips=12.5)
        assert _compute_score(r, "avg_pips") == 12.5

    def test_win_rate_none_returns_minus1(self):
        r = OptimizeResult(params=OptimizeParams(), symbol="USD/JPY", win_rate=None)
        assert _compute_score(r, "win_rate") == -1.0

    def test_avg_pips_none_returns_large_negative(self):
        r = OptimizeResult(params=OptimizeParams(), symbol="USD/JPY", avg_pips=None)
        assert _compute_score(r, "avg_pips") == -9999.0

    def test_unknown_metric_returns_zero(self):
        r = self._make_result()
        assert _compute_score(r, "unknown") == 0.0


# ── _analyze_with_params ────────────────────────────────────
class TestAnalyzeWithParams:
    def test_skip_on_empty_daily(self):
        params = OptimizeParams(ma_short=20, ma_long=75)
        result = _analyze_with_params(pd.DataFrame(), _make_df_4h(200), _make_df_1h(200), params)
        assert result == SIGNAL_SKIP

    def test_skip_on_empty_4h(self):
        params = OptimizeParams(ma_short=20, ma_long=75)
        result = _analyze_with_params(_make_df_daily(200), pd.DataFrame(), _make_df_1h(200), params)
        assert result == SIGNAL_SKIP

    def test_skip_on_empty_1h(self):
        params = OptimizeParams(ma_short=20, ma_long=75)
        result = _analyze_with_params(_make_df_daily(200), _make_df_4h(200), pd.DataFrame(), params)
        assert result == SIGNAL_SKIP

    def test_skip_on_insufficient_data(self):
        params = OptimizeParams(ma_short=20, ma_long=75)
        result = _analyze_with_params(
            _make_df_daily(10), _make_df_4h(10), _make_df_1h(10), params
        )
        assert result == SIGNAL_SKIP

    def test_returns_valid_signal(self):
        params = OptimizeParams(ma_short=20, ma_long=75)
        df_d = _make_df_daily(200, trend="up")
        df_4h = _make_df_4h(200, trend="up")
        df_1h = _make_df_1h(200, trend="up")
        result = _analyze_with_params(df_d, df_4h, df_1h, params)
        assert result in (SIGNAL_BUY, SIGNAL_SELL, SIGNAL_SKIP)


# ── optimize() 入力バリデーション ────────────────────────────
class TestOptimizeValidation:
    def test_invalid_metric_raises(self):
        with pytest.raises(ValueError, match="metric"):
            optimize("USD/JPY", metric="invalid_metric")

    def test_too_many_combinations_raises(self):
        with pytest.raises(ValueError, match="上限"):
            optimize(
                "USD/JPY",
                ma_short_values=list(range(1, 20)),
                ma_long_values=list(range(50, 200, 5)),
                rsi_buy_max_values=[60, 65, 70, 75, 80],
            )

    def test_invalid_symbol_raises(self):
        with pytest.raises(ValueError, match="未対応"):
            optimize("FAKE/PAIR")


# ── optimize() 正常系（実データ） ────────────────────────────
class TestOptimizeIntegration:
    """実際のCSVデータを使った結合テスト（軽量設定）。"""

    def test_returns_list_of_results(self):
        results = optimize(
            "USD/JPY",
            ma_short_values=[20],
            ma_long_values=[75],
            rsi_buy_max_values=[70],
            metric="win_rate",
            window=200,
            step=48,
        )
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], OptimizeResult)

    def test_results_sorted_by_score_descending(self):
        results = optimize(
            "USD/JPY",
            ma_short_values=[15, 20],
            ma_long_values=[75],
            rsi_buy_max_values=[70],
            metric="win_rate",
            window=200,
            step=48,
        )
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_short_must_be_less_than_long(self):
        # ma_short=50, ma_long=50 はフィルターされる → 有効コンボ数に影響しない
        results = optimize(
            "USD/JPY",
            ma_short_values=[50],
            ma_long_values=[50],
            rsi_buy_max_values=[70],
            metric="total_pips",
            window=200,
            step=48,
        )
        assert results == []

    def test_result_fields_are_populated(self):
        results = optimize(
            "USD/JPY",
            ma_short_values=[20],
            ma_long_values=[75],
            rsi_buy_max_values=[70],
            metric="avg_pips",
            window=200,
            step=48,
        )
        r = results[0]
        assert r.symbol == "USD/JPY"
        assert r.params.ma_short == 20
        assert r.params.ma_long == 75
        assert r.params.rsi_buy_max == 70
        assert r.wins >= 0
        assert r.losses >= 0

    def test_metric_total_pips(self):
        results = optimize(
            "USD/JPY",
            ma_short_values=[20],
            ma_long_values=[75],
            rsi_buy_max_values=[70],
            metric="total_pips",
            window=200,
            step=48,
        )
        assert len(results) == 1
        assert isinstance(results[0].total_pips, float)

    def test_multiple_combos_returns_all(self):
        results = optimize(
            "USD/JPY",
            ma_short_values=[15, 20, 25],
            ma_long_values=[50, 75],
            rsi_buy_max_values=[70],
            metric="win_rate",
            window=200,
            step=48,
        )
        # short < long の組み合わせのみ: 全6通り
        assert len(results) == 6
