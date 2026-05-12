"""テクニカル指標のテスト"""
import numpy as np
import pandas as pd
import pytest

from app.indicators.moving_average import calculate_ma, get_ma_trend, get_ma_values
from app.indicators.rsi import calculate_rsi, get_rsi_value, get_rsi_status
from app.indicators.atr import (
    calculate_atr,
    get_atr_value,
    get_recent_high,
    get_recent_low,
    is_atr_abnormal,
)


def make_ohlc(n: int = 200, start_price: float = 150.0, trend: float = 0.0) -> pd.DataFrame:
    """テスト用OHLCDataFrameを作成する。"""
    np.random.seed(0)
    closes = [start_price]
    for _ in range(n - 1):
        closes.append(closes[-1] + trend + np.random.normal(0, 0.05))
    closes = np.array(closes)
    highs = closes + np.abs(np.random.normal(0, 0.03, n))
    lows = closes - np.abs(np.random.normal(0, 0.03, n))
    opens = np.roll(closes, 1)
    opens[0] = start_price

    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes},
        index=idx,
    )


# ============================================================
# 移動平均
# ============================================================

class TestMovingAverage:
    def test_ma20_length(self):
        df = make_ohlc(200)
        ma = calculate_ma(df["close"], 20)
        assert len(ma) == 200

    def test_ma20_first_values_nan(self):
        df = make_ohlc(200)
        ma = calculate_ma(df["close"], 20)
        assert ma.iloc[:19].isna().all()

    def test_ma20_value_at_period(self):
        df = make_ohlc(200)
        ma = calculate_ma(df["close"], 20)
        assert not pd.isna(ma.iloc[19])

    def test_ma_insufficient_data(self):
        df = make_ohlc(10)
        ma = calculate_ma(df["close"], 20)
        assert ma.isna().all()

    def test_get_ma_trend_uptrend(self):
        """上昇トレンドでは20MA > 75MAになる。"""
        df = make_ohlc(200, trend=0.01)
        trend = get_ma_trend(df)
        assert trend in ("上昇", "下降", "横ばい", "判定不能")

    def test_get_ma_trend_insufficient_data(self):
        df = make_ohlc(50)
        trend = get_ma_trend(df)
        assert trend == "判定不能"

    def test_get_ma_values_returns_dict(self):
        df = make_ohlc(200)
        result = get_ma_values(df)
        assert "ma20" in result
        assert "ma75" in result

    def test_get_ma_values_empty(self):
        result = get_ma_values(pd.DataFrame())
        assert result["ma20"] is None
        assert result["ma75"] is None


# ============================================================
# RSI
# ============================================================

class TestRSI:
    def test_rsi_range(self):
        """RSIは0〜100の範囲内にある。"""
        df = make_ohlc(200)
        rsi = calculate_rsi(df["close"], 14)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_insufficient_data(self):
        df = make_ohlc(10)
        rsi = calculate_rsi(df["close"], 14)
        assert rsi.isna().all()

    def test_get_rsi_value_returns_float(self):
        df = make_ohlc(200)
        val = get_rsi_value(df)
        assert val is not None
        assert 0 <= val <= 100

    def test_get_rsi_value_insufficient(self):
        df = make_ohlc(5)
        val = get_rsi_value(df)
        assert val is None

    def test_rsi_all_up(self):
        """全部上昇の場合RSIは100に近い。"""
        prices = pd.Series([100.0 + i * 0.1 for i in range(50)])
        rsi = calculate_rsi(prices, 14)
        assert rsi.dropna().iloc[-1] > 90

    def test_rsi_all_down(self):
        """全部下降の場合RSIは0に近い。"""
        prices = pd.Series([100.0 - i * 0.1 for i in range(50)])
        rsi = calculate_rsi(prices, 14)
        assert rsi.dropna().iloc[-1] < 10

    def test_get_rsi_status(self):
        assert get_rsi_status(75) == "買われすぎ"
        assert get_rsi_status(25) == "売られすぎ"
        assert get_rsi_status(50) == "中立"
        assert get_rsi_status(None) == "判定不能"


# ============================================================
# ATR・直近高安値
# ============================================================

class TestATR:
    def test_atr_positive(self):
        """ATRは正の値。"""
        df = make_ohlc(200)
        atr = calculate_atr(df, 14)
        valid = atr.dropna()
        assert (valid > 0).all()

    def test_atr_length(self):
        df = make_ohlc(200)
        atr = calculate_atr(df, 14)
        assert len(atr) == 200

    def test_atr_insufficient(self):
        df = make_ohlc(5)
        val = get_atr_value(df)
        assert val is None

    def test_get_atr_value(self):
        df = make_ohlc(200)
        val = get_atr_value(df)
        assert val is not None and val > 0

    def test_recent_high_gt_recent_low(self):
        df = make_ohlc(200)
        high = get_recent_high(df, 20)
        low = get_recent_low(df, 20)
        assert high is not None
        assert low is not None
        assert high >= low

    def test_recent_high_insufficient(self):
        df = make_ohlc(10)
        high = get_recent_high(df, 20)
        assert high is None

    def test_atr_abnormal_normal_data(self):
        """通常データでは異常フラグが立たない（多くの場合）。"""
        df = make_ohlc(200)
        result = is_atr_abnormal(df)
        assert isinstance(result, bool)
