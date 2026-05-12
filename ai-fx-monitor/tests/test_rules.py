"""売買判定ルールのテスト"""
import numpy as np
import pandas as pd
import pytest

from app.strategy.rules import (
    SIGNAL_BUY,
    SIGNAL_SELL,
    SIGNAL_SKIP,
    analyze_signal,
)


def make_trending_ohlc(n: int, trend: float, start: float = 150.0, freq: str = "1h") -> pd.DataFrame:
    """指定トレンドのOHLCデータを生成する。"""
    np.random.seed(42)
    closes = [start]
    for _ in range(n - 1):
        closes.append(max(closes[-1] + trend + np.random.normal(0, 0.02), 1.0))
    closes = np.array(closes)
    highs = closes + 0.05
    lows = closes - 0.05
    opens = np.roll(closes, 1)
    opens[0] = start
    idx = pd.date_range("2024-01-01", periods=n, freq=freq)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes},
        index=idx,
    )


class TestAnalyzeSignalDataInsufficient:
    def test_empty_daily_returns_skip(self):
        result = analyze_signal(
            df_daily=pd.DataFrame(),
            df_4h=pd.DataFrame(),
            df_1h=pd.DataFrame(),
        )
        assert result.signal == SIGNAL_SKIP
        assert not result.data_sufficient

    def test_insufficient_daily_returns_skip(self):
        df_small = make_trending_ohlc(50, 0.01, freq="1D")
        df_4h = make_trending_ohlc(100, 0.01, freq="4h")
        df_1h = make_trending_ohlc(200, 0.01, freq="1h")
        result = analyze_signal(df_small, df_4h, df_1h)
        assert result.signal == SIGNAL_SKIP
        assert not result.data_sufficient

    def test_insufficient_1h_returns_skip(self):
        df_daily = make_trending_ohlc(200, 0.01, freq="1D")
        df_4h = make_trending_ohlc(200, 0.01, freq="4h")
        df_1h_small = make_trending_ohlc(50, 0.01, freq="1h")
        result = analyze_signal(df_daily, df_4h, df_1h_small)
        assert result.signal == SIGNAL_SKIP


class TestAnalyzeSignalEconomicWarning:
    def test_economic_warning_returns_skip(self):
        """重要指標前後は必ずSKIP。"""
        df_daily = make_trending_ohlc(200, 0.01, freq="1D")
        df_4h = make_trending_ohlc(400, 0.01, freq="4h")
        df_1h = make_trending_ohlc(1000, 0.01, freq="1h")
        result = analyze_signal(df_daily, df_4h, df_1h, economic_warning=True)
        assert result.signal == SIGNAL_SKIP
        assert any("経済指標" in r for r in result.skip_reasons)


class TestAnalyzeSignalResult:
    def test_signal_has_valid_value(self):
        df_daily = make_trending_ohlc(200, 0.01, freq="1D")
        df_4h = make_trending_ohlc(400, 0.01, freq="4h")
        df_1h = make_trending_ohlc(1000, 0.01, freq="1h")
        result = analyze_signal(df_daily, df_4h, df_1h)
        assert result.signal in (SIGNAL_BUY, SIGNAL_SELL, SIGNAL_SKIP)

    def test_result_has_rsi(self):
        df_daily = make_trending_ohlc(200, 0.01, freq="1D")
        df_4h = make_trending_ohlc(400, 0.01, freq="4h")
        df_1h = make_trending_ohlc(1000, 0.01, freq="1h")
        result = analyze_signal(df_daily, df_4h, df_1h)
        assert result.rsi is None or (0 <= result.rsi <= 100)

    def test_result_has_trend_info(self):
        df_daily = make_trending_ohlc(200, 0.01, freq="1D")
        df_4h = make_trending_ohlc(400, 0.01, freq="4h")
        df_1h = make_trending_ohlc(1000, 0.01, freq="1h")
        result = analyze_signal(df_daily, df_4h, df_1h)
        assert result.daily_trend in ("上昇", "下降", "横ばい", "判定不能")
        assert result.h4_trend in ("上昇", "下降", "横ばい", "判定不能")

    def test_skip_has_reasons(self):
        """SKIPの場合はskip_reasonsが存在する（データ不足以外）。"""
        df_daily = make_trending_ohlc(200, 0.01, freq="1D")
        df_4h = make_trending_ohlc(400, 0.01, freq="4h")
        df_1h = make_trending_ohlc(1000, 0.01, freq="1h")
        result = analyze_signal(df_daily, df_4h, df_1h)
        if result.signal == SIGNAL_SKIP and result.data_sufficient:
            assert len(result.skip_reasons) > 0

    def test_downtrend_data_does_not_return_buy(self):
        """強い下降トレンドでは買いシグナルが出ない（BUY条件が揃わない）。"""
        df_daily = make_trending_ohlc(200, -0.05, freq="1D")
        df_4h = make_trending_ohlc(400, -0.05, freq="4h")
        df_1h = make_trending_ohlc(1000, -0.05, freq="1h")
        result = analyze_signal(df_daily, df_4h, df_1h)
        assert result.signal != SIGNAL_BUY
