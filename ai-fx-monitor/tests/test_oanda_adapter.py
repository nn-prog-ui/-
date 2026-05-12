"""OANDAアダプターのテスト（外部APIへの実通信なし・モック使用）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.data.oanda_adapter import OandaAdapter, OandaAdapterError


class TestOandaAdapterInit:
    def test_practice_environment_ok(self):
        adapter = OandaAdapter("test_key", "test_account", "practice")
        assert adapter._account_id == "test_account"

    def test_live_environment_raises(self):
        with pytest.raises(OandaAdapterError, match="practice"):
            OandaAdapter("test_key", "test_account", "live")

    def test_from_env_missing_key_raises(self, monkeypatch):
        monkeypatch.setenv("OANDA_API_KEY", "")
        monkeypatch.setenv("OANDA_ACCOUNT_ID", "")
        with pytest.raises(OandaAdapterError, match="OANDA_API_KEY"):
            OandaAdapter.from_env()

    def test_from_env_with_values(self, monkeypatch):
        monkeypatch.setenv("OANDA_API_KEY", "dummy_key")
        monkeypatch.setenv("OANDA_ACCOUNT_ID", "dummy_account")
        monkeypatch.setenv("OANDA_ENVIRONMENT", "practice")
        adapter = OandaAdapter.from_env()
        assert adapter._account_id == "dummy_account"


class TestOandaAdapterParseCandles:
    def _make_adapter(self) -> OandaAdapter:
        return OandaAdapter("key", "account", "practice")

    def _make_candle(self, time: str, o: str, h: str, l: str, c: str, vol: int = 100) -> dict:
        return {
            "time": time,
            "complete": True,
            "volume": vol,
            "mid": {"o": o, "h": h, "l": l, "c": c},
        }

    def test_parse_candles_returns_dataframe(self):
        adapter = self._make_adapter()
        candles = [
            self._make_candle("2024-01-01T00:00:00.000000000Z", "150.0", "150.5", "149.8", "150.3"),
            self._make_candle("2024-01-01T01:00:00.000000000Z", "150.3", "150.8", "150.0", "150.6"),
        ]
        df = adapter._parse_candles(candles)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    def test_parse_candles_values(self):
        adapter = self._make_adapter()
        candles = [
            self._make_candle("2024-01-01T00:00:00.000000000Z", "150.0", "150.5", "149.8", "150.3")
        ]
        df = adapter._parse_candles(candles)
        assert df["open"].iloc[0] == 150.0
        assert df["high"].iloc[0] == 150.5
        assert df["low"].iloc[0] == 149.8
        assert df["close"].iloc[0] == 150.3

    def test_parse_candles_incomplete_skipped(self):
        """complete=Falseのキャンドルはスキップされる（未確定足）。"""
        adapter = self._make_adapter()
        candles = [
            {
                "time": "2024-01-01T00:00:00.000000000Z",
                "complete": False,
                "volume": 50,
                "mid": {"o": "150.0", "h": "150.5", "l": "149.8", "c": "150.3"},
            }
        ]
        df = adapter._parse_candles(candles)
        assert df.empty

    def test_parse_candles_empty_list(self):
        adapter = self._make_adapter()
        df = adapter._parse_candles([])
        assert df.empty

    def test_parse_candles_sorted_by_time(self):
        adapter = self._make_adapter()
        candles = [
            self._make_candle("2024-01-01T02:00:00.000000000Z", "152.0", "152.5", "151.8", "152.3"),
            self._make_candle("2024-01-01T00:00:00.000000000Z", "150.0", "150.5", "149.8", "150.3"),
            self._make_candle("2024-01-01T01:00:00.000000000Z", "150.3", "150.8", "150.0", "150.6"),
        ]
        df = adapter._parse_candles(candles)
        assert df.index[0] < df.index[1] < df.index[2]

    def test_parse_candles_high_gte_low(self):
        adapter = self._make_adapter()
        candles = [
            self._make_candle("2024-01-01T00:00:00.000000000Z", "150.0", "150.5", "149.8", "150.3")
        ]
        df = adapter._parse_candles(candles)
        assert (df["high"] >= df["low"]).all()


class TestOandaAdapterGetOhlcv:
    def _make_adapter(self) -> OandaAdapter:
        return OandaAdapter("key", "account", "practice")

    def _make_mock_response(self, candles: list) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"candles": candles, "instrument": "USD_JPY"}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_get_ohlcv_success(self):
        adapter = self._make_adapter()
        candles = [
            {
                "time": f"2024-01-{i+1:02d}T00:00:00.000000000Z",
                "complete": True,
                "volume": 1000,
                "mid": {"o": "150.0", "h": "150.5", "l": "149.8", "c": "150.3"},
            }
            for i in range(5)
        ]
        mock_resp = self._make_mock_response(candles)

        with patch("requests.get", return_value=mock_resp):
            df = adapter.get_ohlcv("USD_JPY", "1h", count=5)

        assert len(df) == 5
        assert "close" in df.columns

    def test_get_ohlcv_api_error_raises(self):
        adapter = self._make_adapter()
        with patch("requests.get", side_effect=Exception("Connection refused")):
            with pytest.raises(OandaAdapterError):
                adapter.get_ohlcv("USD_JPY", "1h", count=5)

    def test_get_ohlcv_empty_candles(self):
        adapter = self._make_adapter()
        mock_resp = self._make_mock_response([])
        with patch("requests.get", return_value=mock_resp):
            df = adapter.get_ohlcv("USD_JPY", "1h", count=5)
        assert df.empty

    def test_get_current_price_success(self):
        adapter = self._make_adapter()
        candles = [
            {
                "time": "2024-01-01T00:00:00.000000000Z",
                "complete": True,
                "volume": 1000,
                "mid": {"o": "150.0", "h": "150.5", "l": "149.8", "c": "150.350"},
            }
        ]
        mock_resp = self._make_mock_response(candles)
        with patch("requests.get", return_value=mock_resp):
            price = adapter.get_current_price("USD_JPY")
        assert price == 150.35


class TestPriceSource:
    def test_csv_source_returns_timeframes(self):
        from app.data.price_source import _get_from_csv
        timeframes, is_dummy = _get_from_csv(None)
        assert "1h" in timeframes
        assert "4h" in timeframes
        assert "daily" in timeframes

    def test_oanda_source_fallback_to_csv_on_error(self, monkeypatch):
        """OANDA接続失敗時はCSVにフォールバックする。"""
        monkeypatch.setenv("OANDA_API_KEY", "dummy")
        monkeypatch.setenv("OANDA_ACCOUNT_ID", "dummy")

        from app.data.price_source import _get_from_oanda

        with patch("app.data.oanda_adapter.OandaAdapter.get_ohlcv", side_effect=Exception("API Error")):
            timeframes, is_dummy = _get_from_oanda("USD/JPY")

        assert "1h" in timeframes

    def test_get_price_data_csv_mode(self, monkeypatch):
        """DATA_SOURCE=csv のときCSVソースが使われる。"""
        monkeypatch.setenv("DATA_SOURCE", "csv")
        from app.data.price_source import get_price_data

        timeframes, is_dummy = get_price_data("USD/JPY")
        assert "1h" in timeframes

    def test_get_price_data_oanda_mode_no_key_fallback(self, monkeypatch):
        """OANDA_API_KEYがない場合はCSVにフォールバック。"""
        monkeypatch.setenv("DATA_SOURCE", "oanda")
        monkeypatch.setenv("OANDA_API_KEY", "")
        monkeypatch.setenv("OANDA_ACCOUNT_ID", "")
        from app.data.price_source import get_price_data

        timeframes, is_dummy = get_price_data("USD/JPY")
        assert "1h" in timeframes
