"""tests/test_correlation.py — Phase 37: 通貨相関マトリクステスト"""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch

from app.services.correlation import (
    CorrelationMatrix,
    LOOKBACK_OPTIONS,
    DEFAULT_LOOKBACK,
    calculate_correlation_matrix,
    correlation_label,
    _load_daily_returns,
)
from app.config import SUPPORTED_SYMBOLS


# ── CorrelationMatrix ────────────────────────────────────────
class TestCorrelationMatrix:
    def _make(self, symbols=None, matrix=None):
        symbols = symbols or ["A", "B", "C"]
        n = len(symbols)
        if matrix is None:
            matrix = [[1.0, 0.8, -0.5], [0.8, 1.0, -0.3], [-0.5, -0.3, 1.0]]
        return CorrelationMatrix(
            symbols=symbols,
            matrix=matrix,
            lookback_days=63,
            data_points={"A": 63, "B": 63, "C": 63},
        )

    def test_get_same_symbol_is_one(self):
        cm = self._make()
        assert cm.get("A", "A") == 1.0

    def test_get_existing_pair(self):
        cm = self._make()
        assert cm.get("A", "B") == 0.8

    def test_get_unknown_symbol_returns_none(self):
        cm = self._make()
        assert cm.get("A", "Z") is None

    def test_to_css_class_pos_strong(self):
        cm = self._make()
        assert cm.to_css_class(0.8) == "corr-pos-strong"

    def test_to_css_class_pos_medium(self):
        cm = self._make()
        assert cm.to_css_class(0.5) == "corr-pos-medium"

    def test_to_css_class_neutral(self):
        cm = self._make()
        assert cm.to_css_class(0.0) == "corr-neutral"
        assert cm.to_css_class(-0.1) == "corr-neutral"

    def test_to_css_class_neg_medium(self):
        cm = self._make()
        assert cm.to_css_class(-0.5) == "corr-neg-medium"

    def test_to_css_class_neg_strong(self):
        cm = self._make()
        assert cm.to_css_class(-0.9) == "corr-neg-strong"

    def test_to_css_class_none(self):
        cm = self._make()
        assert cm.to_css_class(None) == "corr-na"

    def test_to_css_class_boundary_pos_strong(self):
        cm = self._make()
        assert cm.to_css_class(0.7) == "corr-pos-strong"

    def test_to_css_class_boundary_neg_strong(self):
        cm = self._make()
        # -0.7 は >= -0.7 なので corr-neg-medium、-0.71以下が corr-neg-strong
        assert cm.to_css_class(-0.7) == "corr-neg-medium"
        assert cm.to_css_class(-0.71) == "corr-neg-strong"


# ── correlation_label ────────────────────────────────────────
class TestCorrelationLabel:
    def test_none_returns_dashes(self):
        assert correlation_label(None) == "---"

    def test_strong_positive(self):
        assert correlation_label(0.8) == "強い正相関"

    def test_medium_positive(self):
        assert correlation_label(0.5) == "中程度正相関"

    def test_neutral(self):
        assert correlation_label(0.0) == "相関なし"
        assert correlation_label(-0.2) == "相関なし"

    def test_medium_negative(self):
        assert correlation_label(-0.5) == "中程度負相関"

    def test_strong_negative(self):
        assert correlation_label(-0.9) == "強い負相関"


# ── 定数 ────────────────────────────────────────────────────
class TestConstants:
    def test_lookback_options_not_empty(self):
        assert len(LOOKBACK_OPTIONS) > 0

    def test_lookback_options_have_positive_values(self):
        for label, days in LOOKBACK_OPTIONS.items():
            assert days > 0, f"{label}の日数が0以下"

    def test_default_lookback_is_in_options(self):
        assert DEFAULT_LOOKBACK in LOOKBACK_OPTIONS.values()


# ── _load_daily_returns ──────────────────────────────────────
class TestLoadDailyReturns:
    def test_unknown_symbol_returns_none(self):
        result = _load_daily_returns("FAKE/XXX", 63)
        assert result is None

    def test_valid_symbol_returns_series_or_none(self):
        result = _load_daily_returns("USD/JPY", 63)
        # ダミーデータでも Series か None のどちらか
        assert result is None or isinstance(result, pd.Series)

    def test_returns_series_has_symbol_name(self):
        result = _load_daily_returns("USD/JPY", 63)
        if result is not None:
            assert result.name == "USD/JPY"

    def test_returns_values_are_finite(self):
        result = _load_daily_returns("USD/JPY", 63)
        if result is not None:
            assert np.all(np.isfinite(result.values))


# ── calculate_correlation_matrix ────────────────────────────
class TestCalculateCorrelationMatrix:
    def test_returns_correlation_matrix_type(self):
        result = calculate_correlation_matrix(lookback_days=21)
        assert isinstance(result, CorrelationMatrix)

    def test_symbols_match_supported(self):
        result = calculate_correlation_matrix(lookback_days=21)
        assert result.symbols == SUPPORTED_SYMBOLS

    def test_matrix_dimension(self):
        result = calculate_correlation_matrix(lookback_days=21)
        n = len(SUPPORTED_SYMBOLS)
        assert len(result.matrix) == n
        for row in result.matrix:
            assert len(row) == n

    def test_diagonal_is_one(self):
        result = calculate_correlation_matrix(lookback_days=21)
        for i in range(len(result.symbols)):
            val = result.matrix[i][i]
            assert val is None or abs(val - 1.0) < 1e-9

    def test_matrix_is_symmetric(self):
        result = calculate_correlation_matrix(lookback_days=21)
        n = len(result.symbols)
        for i in range(n):
            for j in range(n):
                val_ij = result.matrix[i][j]
                val_ji = result.matrix[j][i]
                if val_ij is None or val_ji is None:
                    assert val_ij == val_ji
                else:
                    assert abs(val_ij - val_ji) < 1e-9

    def test_values_in_range(self):
        result = calculate_correlation_matrix(lookback_days=21)
        for row in result.matrix:
            for val in row:
                if val is not None:
                    assert -1.0 <= val <= 1.0, f"相関値範囲外: {val}"

    def test_custom_symbols(self):
        symbols = ["USD/JPY", "EUR/USD"]
        result = calculate_correlation_matrix(symbols=symbols, lookback_days=21)
        assert result.symbols == symbols
        assert len(result.matrix) == 2
        assert len(result.matrix[0]) == 2

    def test_lookback_days_stored(self):
        result = calculate_correlation_matrix(lookback_days=42)
        assert result.lookback_days == 42

    def test_invalid_metric_does_not_raise(self):
        # 対応シンボルのみ処理するので、不正シンボルはスキップされる
        result = calculate_correlation_matrix(symbols=["USD/JPY", "FAKE/XXX"], lookback_days=21)
        assert isinstance(result, CorrelationMatrix)

    def test_data_points_populated(self):
        result = calculate_correlation_matrix(lookback_days=21)
        # データが取得できたシンボルのみ data_points に入る
        assert isinstance(result.data_points, dict)
        for sym, pts in result.data_points.items():
            assert pts >= 0
