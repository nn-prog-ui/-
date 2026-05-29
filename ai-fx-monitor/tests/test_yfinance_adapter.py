"""Phase 84: yfinance アダプター テスト"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def _adapter_src() -> str:
    return (Path(__file__).parent.parent / "app" / "data" / "yfinance_adapter.py").read_text(encoding="utf-8")


def _price_source_src() -> str:
    return (Path(__file__).parent.parent / "app" / "data" / "price_source.py").read_text(encoding="utf-8")


def _env_example_src() -> str:
    return (Path(__file__).parent.parent / ".env.example").read_text(encoding="utf-8")


def _requirements_src() -> str:
    return (Path(__file__).parent.parent / "requirements.txt").read_text(encoding="utf-8")


# ── シンボルマッピングテスト ────────────────────────────────────────────────

class TestYfSymbolMap:
    def test_usdjpy_symbol(self):
        """USD/JPY → JPY=X"""
        from app.data.yfinance_adapter import get_yf_symbol
        assert get_yf_symbol("USD/JPY") == "JPY=X"

    def test_eurusd_symbol(self):
        """EUR/USD → EURUSD=X"""
        from app.data.yfinance_adapter import get_yf_symbol
        assert get_yf_symbol("EUR/USD") == "EURUSD=X"

    def test_gbpusd_symbol(self):
        """GBP/USD → GBPUSD=X"""
        from app.data.yfinance_adapter import get_yf_symbol
        assert get_yf_symbol("GBP/USD") == "GBPUSD=X"

    def test_eurjpy_symbol(self):
        """EUR/JPY → EURJPY=X"""
        from app.data.yfinance_adapter import get_yf_symbol
        assert get_yf_symbol("EUR/JPY") == "EURJPY=X"

    def test_audjpy_symbol(self):
        """AUD/JPY → AUDJPY=X"""
        from app.data.yfinance_adapter import get_yf_symbol
        assert get_yf_symbol("AUD/JPY") == "AUDJPY=X"

    def test_audusd_symbol(self):
        """AUD/USD → AUDUSD=X"""
        from app.data.yfinance_adapter import get_yf_symbol
        assert get_yf_symbol("AUD/USD") == "AUDUSD=X"

    def test_eurgbp_symbol(self):
        """EUR/GBP → EURGBP=X"""
        from app.data.yfinance_adapter import get_yf_symbol
        assert get_yf_symbol("EUR/GBP") == "EURGBP=X"

    def test_gbpjpy_symbol(self):
        """GBP/JPY → GBPJPY=X"""
        from app.data.yfinance_adapter import get_yf_symbol
        assert get_yf_symbol("GBP/JPY") == "GBPJPY=X"

    def test_all_8_pairs_mapped(self):
        """全8通貨ペアがマッピングされている"""
        from app.data.yfinance_adapter import _YF_SYMBOL_MAP
        expected = {"USD/JPY", "EUR/USD", "GBP/USD", "EUR/JPY",
                    "AUD/JPY", "AUD/USD", "EUR/GBP", "GBP/JPY"}
        assert expected == set(_YF_SYMBOL_MAP.keys())

    def test_unknown_symbol_fallback(self):
        """未知シンボルはスラッシュを除いて =X を付加する"""
        from app.data.yfinance_adapter import get_yf_symbol
        assert get_yf_symbol("XAU/USD") == "XAUUSD=X"


# ── データ正規化テスト ──────────────────────────────────────────────────────

class TestNormalizeDf:
    def _make_raw_df(self) -> pd.DataFrame:
        """yfinance が返す形式の DataFrame を作成"""
        idx = pd.date_range("2024-01-01", periods=5, freq="1h", tz="UTC")
        return pd.DataFrame({
            "Open":   [150.0, 150.5, 151.0, 150.8, 151.2],
            "High":   [150.8, 151.2, 151.5, 151.0, 151.8],
            "Low":    [149.8, 150.2, 150.5, 150.3, 150.9],
            "Close":  [150.5, 151.0, 150.8, 151.2, 151.5],
            "Volume": [1000,  1200,  900,   1100,  800  ],
        }, index=idx)

    def test_columns_lowercased(self):
        """カラム名が小文字に変換される"""
        from app.data.yfinance_adapter import _normalize_df
        df = _normalize_df(self._make_raw_df())
        assert set(["open", "high", "low", "close", "volume"]).issubset(set(df.columns))

    def test_no_uppercase_columns(self):
        """大文字カラムが残っていない"""
        from app.data.yfinance_adapter import _normalize_df
        df = _normalize_df(self._make_raw_df())
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            assert col not in df.columns

    def test_timezone_removed(self):
        """タイムゾーン情報が除去される（tz-naive）"""
        from app.data.yfinance_adapter import _normalize_df
        df = _normalize_df(self._make_raw_df())
        assert df.index.tz is None

    def test_index_name_is_datetime(self):
        """インデックス名が datetime"""
        from app.data.yfinance_adapter import _normalize_df
        df = _normalize_df(self._make_raw_df())
        assert df.index.name == "datetime"

    def test_sorted_ascending(self):
        """昇順ソートされている"""
        from app.data.yfinance_adapter import _normalize_df
        df = _normalize_df(self._make_raw_df())
        assert df.index.is_monotonic_increasing

    def test_row_count_preserved(self):
        """NaN がない場合は行数が変わらない"""
        from app.data.yfinance_adapter import _normalize_df
        raw = self._make_raw_df()
        df = _normalize_df(raw)
        assert len(df) == len(raw)


# ── fetch_ohlcv テスト（yfinance をモック） ─────────────────────────────────

class TestFetchOhlcv:
    def _make_mock_df(self) -> pd.DataFrame:
        idx = pd.date_range("2024-01-01", periods=100, freq="1h", tz="UTC")
        return pd.DataFrame({
            "Open":   [150.0] * 100,
            "High":   [151.0] * 100,
            "Low":    [149.0] * 100,
            "Close":  [150.5] * 100,
            "Volume": [1000]  * 100,
        }, index=idx)

    def test_returns_dataframe(self):
        """DataFrame を返す"""
        from app.data.yfinance_adapter import fetch_ohlcv, clear_cache
        clear_cache()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_df()
        with patch("yfinance.Ticker", return_value=mock_ticker):
            df = fetch_ohlcv("USD/JPY", use_cache=False)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_has_required_columns(self):
        """必須カラムが揃っている"""
        from app.data.yfinance_adapter import fetch_ohlcv, clear_cache
        clear_cache()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_df()
        with patch("yfinance.Ticker", return_value=mock_ticker):
            df = fetch_ohlcv("USD/JPY", use_cache=False)
        for col in ["open", "high", "low", "close"]:
            assert col in df.columns

    def test_empty_response_returns_empty_df(self):
        """yfinance が空を返したら空 DataFrame"""
        from app.data.yfinance_adapter import fetch_ohlcv, clear_cache
        clear_cache()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        with patch("yfinance.Ticker", return_value=mock_ticker):
            df = fetch_ohlcv("USD/JPY", use_cache=False)
        assert df.empty

    def test_exception_returns_empty_df(self):
        """例外が発生したら空 DataFrame（フォールバック可能）"""
        from app.data.yfinance_adapter import fetch_ohlcv, clear_cache
        clear_cache()
        with patch("yfinance.Ticker", side_effect=Exception("network error")):
            df = fetch_ohlcv("USD/JPY", use_cache=False)
        assert df.empty

    def test_cache_is_used(self):
        """2回目はキャッシュを使う（yfinance を呼ばない）"""
        from app.data.yfinance_adapter import fetch_ohlcv, clear_cache
        clear_cache()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_df()
        with patch("yfinance.Ticker", return_value=mock_ticker) as mock_yf:
            fetch_ohlcv("USD/JPY", use_cache=True)
            fetch_ohlcv("USD/JPY", use_cache=True)
        # Ticker の呼び出しは1回だけ
        assert mock_yf.call_count == 1


# ── fetch_latest_price テスト ───────────────────────────────────────────────

class TestFetchLatestPrice:
    def _make_mock_df(self) -> pd.DataFrame:
        idx = pd.date_range("2024-01-01", periods=10, freq="1h", tz="UTC")
        closes = [150.0, 150.2, 150.5, 150.3, 150.8,
                  151.0, 150.9, 151.2, 151.5, 151.3]
        return pd.DataFrame({
            "Open":   closes,
            "High":   [c + 0.3 for c in closes],
            "Low":    [c - 0.3 for c in closes],
            "Close":  closes,
            "Volume": [1000] * 10,
        }, index=idx)

    def test_returns_dict(self):
        """辞書を返す"""
        from app.data.yfinance_adapter import fetch_latest_price, clear_cache
        clear_cache()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_df()
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = fetch_latest_price("USD/JPY", use_cache=False)
        assert isinstance(result, dict)

    def test_has_price_keys(self):
        """price・prev_price・change・change_pct キーがある"""
        from app.data.yfinance_adapter import fetch_latest_price, clear_cache
        clear_cache()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_df()
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = fetch_latest_price("USD/JPY", use_cache=False)
        assert result is not None
        for key in ["price", "prev_price", "change", "change_pct"]:
            assert key in result

    def test_change_is_correct(self):
        """change = price - prev_price"""
        from app.data.yfinance_adapter import fetch_latest_price, clear_cache
        clear_cache()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = self._make_mock_df()
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = fetch_latest_price("USD/JPY", use_cache=False)
        assert result is not None
        expected_change = round(result["price"] - result["prev_price"], 5)
        assert abs(result["change"] - expected_change) < 1e-4

    def test_returns_none_on_empty(self):
        """データが空なら None"""
        from app.data.yfinance_adapter import fetch_latest_price, clear_cache
        clear_cache()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = fetch_latest_price("USD/JPY", use_cache=False)
        assert result is None


# ── price_source.py 統合テスト ──────────────────────────────────────────────

class TestPriceSourceYfinance:
    def test_yfinance_in_get_price_data(self):
        """price_source.py が yfinance ソースを処理している"""
        assert "yfinance" in _price_source_src()

    def test_get_from_yfinance_function(self):
        """_get_from_yfinance 関数が定義されている"""
        assert "_get_from_yfinance" in _price_source_src()

    def test_fallback_on_failure(self):
        """yfinance 失敗時は CSV にフォールバック"""
        src = _price_source_src()
        fn = src[src.find("_get_from_yfinance"):]
        assert "フォールバック" in fn or "fallback" in fn.lower()

    def test_phase84_comment(self):
        """Phase 84 コメントがある"""
        assert "Phase 84" in _price_source_src()


# ── 設定ファイルテスト ──────────────────────────────────────────────────────

class TestConfiguration:
    def test_yfinance_in_requirements(self):
        """requirements.txt に yfinance がある"""
        assert "yfinance" in _requirements_src()

    def test_yfinance_version_specified(self):
        """yfinance のバージョンが指定されている"""
        src = _requirements_src()
        line = [l for l in src.splitlines() if "yfinance" in l]
        assert len(line) > 0 and ">=" in line[0]

    def test_yfinance_in_env_example(self):
        """env.example に DATA_SOURCE=yfinance の説明がある"""
        assert "yfinance" in _env_example_src()

    def test_env_example_explains_yfinance(self):
        """env.example に yfinance の説明文がある"""
        src = _env_example_src()
        assert "口座不要" in src or "無料" in src

    def test_adapter_has_cache(self):
        """アダプターにキャッシュ機能がある（API過負荷防止）"""
        src = _adapter_src()
        assert "_cache" in src and "TTL" in src

    def test_adapter_has_clear_cache(self):
        """キャッシュクリア関数がある（テスト・デバッグ用）"""
        assert "clear_cache" in _adapter_src()

    def test_adapter_phase84_comment(self):
        """Phase 84 コメントがある"""
        assert "Phase 84" in _adapter_src()

    def test_pip_install_hint_in_adapter(self):
        """pip install yfinance のヒントがある"""
        assert "pip install yfinance" in _adapter_src()
