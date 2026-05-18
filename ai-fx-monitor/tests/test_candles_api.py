"""Phase 28/30: /api/candles エンドポイントのテスト（MA20・MA50・BB追加対応）"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app


def _make_df(n: int = 80, start: float = 150.0) -> pd.DataFrame:
    """テスト用1時間足OHLCデータを生成する。"""
    np.random.seed(0)
    closes = [start]
    for _ in range(n - 1):
        closes.append(max(closes[-1] + np.random.normal(0, 0.05), 1.0))
    closes = np.array(closes)
    highs = closes + 0.1
    lows = closes - 0.1
    opens = np.roll(closes, 1)
    opens[0] = start
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=idx)


@pytest.fixture()
def client():
    return TestClient(app)


class TestCandlesApiBasic:
    def test_returns_200(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(), False)):
            resp = client.get("/api/candles?symbol=USD/JPY&limit=50")
        assert resp.status_code == 200

    def test_returns_json_keys(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=50").json()
        assert "candles" in data
        assert "symbol" in data
        assert "count" in data

    def test_limit_respected(self, client):
        df = _make_df(n=80)
        with patch("app.web.routes.load_or_generate", return_value=(df, False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=30").json()
        assert data["count"] == 30
        assert len(data["candles"]) == 30

    def test_candle_has_ohlc_fields(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=5").json()
        for c in data["candles"]:
            assert "t" in c
            assert "o" in c
            assert "h" in c
            assert "l" in c
            assert "c" in c

    def test_candle_values_are_floats(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=10").json()
        for c in data["candles"]:
            assert isinstance(c["o"], float)
            assert isinstance(c["h"], float)
            assert isinstance(c["l"], float)
            assert isinstance(c["c"], float)

    def test_high_gte_low(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=60), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=60").json()
        for c in data["candles"]:
            assert c["h"] >= c["l"]

    def test_symbol_reflected_in_response(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(), False)):
            data = client.get("/api/candles?symbol=EUR/USD&limit=10").json()
        assert data["symbol"] == "EUR/USD"

    def test_unsupported_symbol_falls_back_to_default(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(), False)):
            data = client.get("/api/candles?symbol=FAKE/XX&limit=10").json()
        assert data["symbol"] == "USD/JPY"

    def test_empty_df_returns_empty_candles(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(pd.DataFrame(), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=10").json()
        assert data["candles"] == []
        assert data["count"] == 0


class TestCandlesApiTimeframes:
    """Phase 31: 複数時間足（tf パラメータ）のテスト"""

    def test_default_tf_is_1h(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=80), False)):
            data = client.get("/api/candles?symbol=USD/JPY").json()
        assert data["tf"] == "1h"

    def test_4h_tf_returns_fewer_candles(self, client):
        """4時間足は1時間足をリサンプルするため本数が少なくなる。"""
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=200), False)):
            d1h = client.get("/api/candles?symbol=USD/JPY&tf=1h&limit=200").json()
            d4h = client.get("/api/candles?symbol=USD/JPY&tf=4h&limit=200").json()
        assert d4h["count"] < d1h["count"]

    def test_1d_tf_returns_fewer_candles_than_4h(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=500), False)):
            d4h = client.get("/api/candles?symbol=USD/JPY&tf=4h&limit=500").json()
            d1d = client.get("/api/candles?symbol=USD/JPY&tf=1d&limit=500").json()
        assert d1d["count"] < d4h["count"]

    def test_invalid_tf_falls_back_to_1h(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=80), False)):
            data = client.get("/api/candles?symbol=USD/JPY&tf=bogus").json()
        assert data["tf"] == "1h"

    def test_tf_reflected_in_response(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=200), False)):
            data = client.get("/api/candles?symbol=USD/JPY&tf=4h&limit=30").json()
        assert data["tf"] == "4h"

    def test_1d_candle_has_ohlc_fields(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=500), False)):
            data = client.get("/api/candles?symbol=USD/JPY&tf=1d&limit=30").json()
        if data["candles"]:
            c = data["candles"][0]
            assert all(k in c for k in ("t", "o", "h", "l", "c"))


class TestCandlesApiIndicators:
    """Phase 30: MA20・MA50・BB フィールドのテスト"""

    def test_candle_has_indicator_fields(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=80), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=50").json()
        for c in data["candles"]:
            assert "ma20" in c
            assert "ma50" in c
            assert "bb_upper" in c
            assert "bb_lower" in c

    def test_ma20_present_when_enough_data(self, client):
        """80本データの後半50本では MA20 が null でない。"""
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=80), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=50").json()
        # 後半ならMA20が計算できている
        non_null = [c["ma20"] for c in data["candles"] if c["ma20"] is not None]
        assert len(non_null) > 0

    def test_ma50_present_when_enough_data(self, client):
        """110本データの後半50本では MA50 が null でない。"""
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=110), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=50").json()
        non_null = [c["ma50"] for c in data["candles"] if c["ma50"] is not None]
        assert len(non_null) > 0

    def test_bb_upper_gte_lower(self, client):
        """BB 上限 >= 下限 は常に成立する。"""
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=80), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=50").json()
        for c in data["candles"]:
            if c["bb_upper"] is not None and c["bb_lower"] is not None:
                assert c["bb_upper"] >= c["bb_lower"]

    def test_ma20_is_float_or_none(self, client):
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=80), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=50").json()
        for c in data["candles"]:
            assert c["ma20"] is None or isinstance(c["ma20"], float)

    def test_insufficient_data_returns_null_ma(self, client):
        """データ本数 < 20 なら MA20 はすべて null。"""
        with patch("app.web.routes.load_or_generate", return_value=(_make_df(n=15), False)):
            data = client.get("/api/candles?symbol=USD/JPY&limit=15").json()
        assert all(c["ma20"] is None for c in data["candles"])
