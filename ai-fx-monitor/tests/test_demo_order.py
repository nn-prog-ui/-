"""tests/test_demo_order.py — DemoOrderAdapter と is_demo_order_available() のテスト"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.demo_order import (
    DemoOrderAdapter,
    DemoOrderError,
    DemoOrderResult,
    _to_oanda_instrument,
    is_demo_order_available,
)


# --------------------------------------------------------------------------- #
# ヘルパー
# --------------------------------------------------------------------------- #

def _make_adapter() -> DemoOrderAdapter:
    return DemoOrderAdapter(
        api_key="test_key",
        account_id="test_account",
        environment="practice",
    )


def _make_fill_response(trade_id="12345", price="150.123") -> dict:
    return {
        "orderFillTransaction": {
            "price": price,
            "tradeOpened": {"tradeID": trade_id},
        },
        "relatedTransactionIDs": ["T001"],
    }


# --------------------------------------------------------------------------- #
# _to_oanda_instrument
# --------------------------------------------------------------------------- #

class TestToOandaInstrument:
    def test_usdjpy(self):
        assert _to_oanda_instrument("USD/JPY") == "USD_JPY"

    def test_eurusd(self):
        assert _to_oanda_instrument("EUR/USD") == "EUR_USD"

    def test_no_slash(self):
        assert _to_oanda_instrument("USDJPY") == "USDJPY"


# --------------------------------------------------------------------------- #
# DemoOrderAdapter.__init__ — 安全制約テスト
# --------------------------------------------------------------------------- #

class TestDemoOrderAdapterInit:
    def test_practice_env_ok(self):
        adapter = DemoOrderAdapter("key", "acct", "practice")
        assert adapter._base_url == "https://api-fxtrade.oanda.com"

    def test_live_env_rejected(self):
        with pytest.raises(DemoOrderError, match="practice"):
            DemoOrderAdapter("key", "acct", "live")

    def test_default_env_is_practice(self):
        adapter = DemoOrderAdapter("key", "acct")
        assert adapter._base_url == "https://api-fxtrade.oanda.com"

    def test_any_non_practice_rejected(self):
        for bad_env in ("production", "LIVE", "real", ""):
            with pytest.raises(DemoOrderError):
                DemoOrderAdapter("key", "acct", bad_env)


# --------------------------------------------------------------------------- #
# DemoOrderAdapter.from_env
# --------------------------------------------------------------------------- #

class TestFromEnv:
    def test_missing_api_key_raises(self):
        env = {"OANDA_API_KEY": "", "OANDA_ACCOUNT_ID": "acct", "OANDA_ENVIRONMENT": "practice"}
        with patch.dict("os.environ", env, clear=False):
            with pytest.raises(DemoOrderError, match="OANDA_API_KEY"):
                DemoOrderAdapter.from_env()

    def test_missing_account_id_raises(self):
        env = {"OANDA_API_KEY": "key", "OANDA_ACCOUNT_ID": "", "OANDA_ENVIRONMENT": "practice"}
        with patch.dict("os.environ", env, clear=False):
            with pytest.raises(DemoOrderError):
                DemoOrderAdapter.from_env()

    def test_live_environment_rejected(self):
        env = {"OANDA_API_KEY": "key", "OANDA_ACCOUNT_ID": "acct", "OANDA_ENVIRONMENT": "live"}
        with patch.dict("os.environ", env, clear=False):
            with pytest.raises(DemoOrderError, match="practice"):
                DemoOrderAdapter.from_env()

    def test_valid_env_returns_adapter(self):
        env = {"OANDA_API_KEY": "key", "OANDA_ACCOUNT_ID": "acct", "OANDA_ENVIRONMENT": "practice"}
        with patch.dict("os.environ", env, clear=False):
            adapter = DemoOrderAdapter.from_env()
            assert isinstance(adapter, DemoOrderAdapter)


# --------------------------------------------------------------------------- #
# place_market_order
# --------------------------------------------------------------------------- #

class TestPlaceMarketOrder:
    def _mock_response(self, data: dict, status_code: int = 200):
        mock_resp = MagicMock()
        mock_resp.json.return_value = data
        mock_resp.status_code = status_code
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_buy_order_success(self):
        adapter = _make_adapter()
        resp_data = _make_fill_response("99", "150.500")
        mock_resp = self._mock_response(resp_data)

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = adapter.place_market_order("USD/JPY", "BUY", 1000)

        assert isinstance(result, DemoOrderResult)
        assert result.success is True
        assert result.trade_id == "99"
        assert result.filled_price == pytest.approx(150.5)
        assert result.units == 1000  # BUY → positive

        call_body = mock_post.call_args[1]["json"]
        assert call_body["order"]["units"] == "1000"
        assert call_body["order"]["instrument"] == "USD_JPY"

    def test_sell_order_units_negative(self):
        adapter = _make_adapter()
        resp_data = _make_fill_response("88", "149.900")
        mock_resp = self._mock_response(resp_data)

        with patch("requests.post", return_value=mock_resp):
            result = adapter.place_market_order("USD/JPY", "SELL", 2000)

        assert result.units == -2000  # SELL → negative

    def test_stop_loss_attached(self):
        adapter = _make_adapter()
        resp_data = _make_fill_response()
        mock_resp = self._mock_response(resp_data)

        with patch("requests.post", return_value=mock_resp) as mock_post:
            adapter.place_market_order("USD/JPY", "BUY", 1000, stop_loss=149.500)

        call_body = mock_post.call_args[1]["json"]
        assert "stopLossOnFill" in call_body["order"]
        assert call_body["order"]["stopLossOnFill"]["price"] == "149.500"

    def test_take_profit_attached(self):
        adapter = _make_adapter()
        resp_data = _make_fill_response()
        mock_resp = self._mock_response(resp_data)

        with patch("requests.post", return_value=mock_resp) as mock_post:
            adapter.place_market_order("USD/JPY", "BUY", 1000, take_profit=152.000)

        call_body = mock_post.call_args[1]["json"]
        assert "takeProfitOnFill" in call_body["order"]
        assert call_body["order"]["takeProfitOnFill"]["price"] == "152.000"

    def test_no_stop_loss_not_attached(self):
        adapter = _make_adapter()
        resp_data = _make_fill_response()
        mock_resp = self._mock_response(resp_data)

        with patch("requests.post", return_value=mock_resp) as mock_post:
            adapter.place_market_order("USD/JPY", "BUY", 1000)

        call_body = mock_post.call_args[1]["json"]
        assert "stopLossOnFill" not in call_body["order"]
        assert "takeProfitOnFill" not in call_body["order"]

    def test_http_error_raises_demo_order_error(self):
        adapter = _make_adapter()
        import requests as req_module

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_module.HTTPError("401")

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(DemoOrderError, match="注文送信失敗"):
                adapter.place_market_order("USD/JPY", "BUY", 1000)

    def test_connection_error_raises_demo_order_error(self):
        adapter = _make_adapter()
        import requests as req_module

        with patch("requests.post", side_effect=req_module.ConnectionError("refused")):
            with pytest.raises(DemoOrderError, match="注文送信失敗"):
                adapter.place_market_order("USD/JPY", "BUY", 1000)

    def test_filled_price_none_when_missing(self):
        adapter = _make_adapter()
        resp_data = {"orderFillTransaction": {}, "relatedTransactionIDs": []}
        mock_resp = MagicMock()
        mock_resp.json.return_value = resp_data
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            result = adapter.place_market_order("USD/JPY", "BUY", 1000)

        assert result.filled_price is None
        assert result.trade_id is None

    def test_order_type_is_market(self):
        adapter = _make_adapter()
        resp_data = _make_fill_response()
        mock_resp = self._mock_response(resp_data)

        with patch("requests.post", return_value=mock_resp) as mock_post:
            adapter.place_market_order("EUR/USD", "BUY", 500)

        call_body = mock_post.call_args[1]["json"]
        assert call_body["order"]["type"] == "MARKET"
        assert call_body["order"]["timeInForce"] == "FOK"


# --------------------------------------------------------------------------- #
# get_open_trades
# --------------------------------------------------------------------------- #

class TestGetOpenTrades:
    def test_returns_trades_list(self):
        adapter = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"trades": [{"id": "1"}, {"id": "2"}]}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            trades = adapter.get_open_trades()

        assert len(trades) == 2

    def test_returns_empty_on_error(self):
        adapter = _make_adapter()
        import requests as req_module

        with patch("requests.get", side_effect=req_module.ConnectionError("refused")):
            trades = adapter.get_open_trades()

        assert trades == []

    def test_instrument_filter_passed(self):
        adapter = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"trades": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp) as mock_get:
            adapter.get_open_trades(instrument="USD/JPY")

        call_params = mock_get.call_args[1]["params"]
        assert call_params.get("instrument") == "USD_JPY"


# --------------------------------------------------------------------------- #
# is_demo_order_available
# --------------------------------------------------------------------------- #

class TestIsDemoOrderAvailable:
    def _patch_env(self, **kwargs):
        defaults = {
            "DATA_SOURCE": "oanda",
            "OANDA_ENVIRONMENT": "practice",
            "OANDA_API_KEY": "mykey",
            "OANDA_ACCOUNT_ID": "myaccount",
        }
        defaults.update(kwargs)
        return patch.dict("os.environ", defaults, clear=False)

    def test_all_set_returns_true(self):
        with self._patch_env():
            assert is_demo_order_available() is True

    def test_csv_source_returns_false(self):
        with self._patch_env(DATA_SOURCE="csv"):
            assert is_demo_order_available() is False

    def test_live_environment_returns_false(self):
        with self._patch_env(OANDA_ENVIRONMENT="live"):
            assert is_demo_order_available() is False

    def test_missing_api_key_returns_false(self):
        with self._patch_env(OANDA_API_KEY=""):
            assert is_demo_order_available() is False

    def test_missing_account_id_returns_false(self):
        with self._patch_env(OANDA_ACCOUNT_ID=""):
            assert is_demo_order_available() is False

    def test_all_missing_returns_false(self):
        env = {
            "DATA_SOURCE": "csv",
            "OANDA_ENVIRONMENT": "live",
            "OANDA_API_KEY": "",
            "OANDA_ACCOUNT_ID": "",
        }
        with patch.dict("os.environ", env, clear=False):
            assert is_demo_order_available() is False


# --------------------------------------------------------------------------- #
# Phase 13: close_trade / get_trade_detail
# --------------------------------------------------------------------------- #

class TestCloseTrade:
    def test_close_trade_success(self):
        adapter = _make_adapter()
        resp_data = {
            "orderFillTransaction": {"price": "149.850"},
            "relatedTransactionIDs": ["TX999"],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = resp_data
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.put", return_value=mock_resp) as mock_put:
            result = adapter.close_trade("12345")

        assert result.success is True
        assert result.trade_id == "12345"
        assert result.filled_price == pytest.approx(149.85)
        assert result.order_id == "TX999"

        url = mock_put.call_args[0][0]
        assert "/trades/12345/close" in url

    def test_close_trade_http_error_raises(self):
        adapter = _make_adapter()
        import requests as req_module

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_module.HTTPError("404")

        with patch("requests.put", return_value=mock_resp):
            with pytest.raises(DemoOrderError, match="クローズ失敗"):
                adapter.close_trade("99999")

    def test_close_trade_connection_error_raises(self):
        adapter = _make_adapter()
        import requests as req_module

        with patch("requests.put", side_effect=req_module.ConnectionError("refused")):
            with pytest.raises(DemoOrderError, match="クローズ失敗"):
                adapter.close_trade("99999")

    def test_close_trade_no_price_in_response(self):
        adapter = _make_adapter()
        resp_data = {"orderFillTransaction": {}, "relatedTransactionIDs": []}
        mock_resp = MagicMock()
        mock_resp.json.return_value = resp_data
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.put", return_value=mock_resp):
            result = adapter.close_trade("11111")

        assert result.filled_price is None


class TestGetTradeDetail:
    def test_returns_trade_dict(self):
        adapter = _make_adapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"trade": {"id": "42", "currentUnits": "1000"}}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            detail = adapter.get_trade_detail("42")

        assert detail is not None
        assert detail["id"] == "42"

    def test_returns_none_on_error(self):
        adapter = _make_adapter()
        import requests as req_module

        with patch("requests.get", side_effect=req_module.ConnectionError("refused")):
            detail = adapter.get_trade_detail("42")

        assert detail is None
