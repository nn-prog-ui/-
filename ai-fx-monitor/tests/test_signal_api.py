"""Phase 29: /api/latest-signal・/api/all-signals エンドポイントのテスト"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.web.routes as routes_module
from app.main import app


@pytest.fixture(autouse=True)
def clear_signal_cache():
    """各テスト前後にキャッシュをリセットする。"""
    routes_module._signal_cache.clear()
    yield
    routes_module._signal_cache.clear()


@pytest.fixture()
def client():
    return TestClient(app)


class TestLatestSignalEmpty:
    def test_returns_200_when_no_cache(self, client):
        resp = client.get("/api/latest-signal?symbol=USD/JPY")
        assert resp.status_code == 200

    def test_signal_none_when_no_cache(self, client):
        data = client.get("/api/latest-signal?symbol=USD/JPY").json()
        assert data["signal"] == "NONE"
        assert data["score"] is None
        assert data["current_price"] is None

    def test_unsupported_symbol_falls_back_to_default(self, client):
        data = client.get("/api/latest-signal?symbol=FAKE/XX").json()
        assert data["symbol"] == "USD/JPY"

    def test_symbol_in_response(self, client):
        data = client.get("/api/latest-signal?symbol=EUR/USD").json()
        assert data["symbol"] == "EUR/USD"


class TestLatestSignalWithCache:
    def test_returns_cached_signal(self, client):
        routes_module._signal_cache["USD/JPY"] = {
            "signal": "BUY",
            "score": 5,
            "current_price": 150.123,
            "analyzed_at": "2024-01-01T12:00:00",
        }
        data = client.get("/api/latest-signal?symbol=USD/JPY").json()
        assert data["signal"] == "BUY"
        assert data["score"] == 5
        assert data["current_price"] == pytest.approx(150.123)

    def test_returns_sell_signal(self, client):
        routes_module._signal_cache["EUR/USD"] = {
            "signal": "SELL",
            "score": -4,
            "current_price": 1.0850,
            "analyzed_at": "2024-01-01T10:00:00",
        }
        data = client.get("/api/latest-signal?symbol=EUR/USD").json()
        assert data["signal"] == "SELL"

    def test_returns_skip_signal(self, client):
        routes_module._signal_cache["USD/JPY"] = {
            "signal": "SKIP",
            "score": 0,
            "current_price": 149.5,
            "analyzed_at": "2024-01-01T08:00:00",
        }
        data = client.get("/api/latest-signal?symbol=USD/JPY").json()
        assert data["signal"] == "SKIP"


class TestAllSignals:
    def test_returns_200(self, client):
        resp = client.get("/api/all-signals")
        assert resp.status_code == 200

    def test_has_signals_key(self, client):
        data = client.get("/api/all-signals").json()
        assert "signals" in data

    def test_returns_all_supported_symbols(self, client):
        from app.config import SUPPORTED_SYMBOLS
        data = client.get("/api/all-signals").json()
        returned_symbols = {s["symbol"] for s in data["signals"]}
        assert set(SUPPORTED_SYMBOLS) == returned_symbols

    def test_none_signal_when_empty_cache(self, client):
        data = client.get("/api/all-signals").json()
        for item in data["signals"]:
            assert item["signal"] == "NONE"

    def test_cached_values_reflected(self, client):
        routes_module._signal_cache["USD/JPY"] = {
            "signal": "BUY",
            "score": 6,
            "current_price": 152.0,
            "analyzed_at": "2024-01-02T09:00:00",
        }
        data = client.get("/api/all-signals").json()
        usdjpy = next(s for s in data["signals"] if s["symbol"] == "USD/JPY")
        assert usdjpy["signal"] == "BUY"
        assert usdjpy["score"] == 6

    def test_count_matches_supported_symbols(self, client):
        from app.config import SUPPORTED_SYMBOLS
        data = client.get("/api/all-signals").json()
        assert len(data["signals"]) == len(SUPPORTED_SYMBOLS)
