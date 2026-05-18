"""通貨相関マトリクス計算サービス（Phase 37）

各通貨ペアの日次リターンを使ってピアソン相関係数を算出する。
注文・売買判断には使用しない。分析参考情報のみ。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.config import DATA_DIR, SUPPORTED_SYMBOLS, SYMBOL_CSV_MAP
from app.data.loader import load_or_generate
from app.data.resampler import get_all_timeframes

# 期間プリセット（直近N本の日足データ）
LOOKBACK_OPTIONS: dict[str, int] = {
    "1ヶ月": 21,
    "3ヶ月": 63,
    "6ヶ月": 126,
    "1年": 252,
}
DEFAULT_LOOKBACK = 63


@dataclass
class CorrelationMatrix:
    """相関マトリクスの計算結果。"""
    symbols: list[str]
    matrix: list[list[float | None]]
    lookback_days: int
    data_points: dict[str, int]  # symbol -> 使用したデータ点数

    def get(self, sym_a: str, sym_b: str) -> float | None:
        if sym_a not in self.symbols or sym_b not in self.symbols:
            return None
        i = self.symbols.index(sym_a)
        j = self.symbols.index(sym_b)
        return self.matrix[i][j]

    def to_css_class(self, value: float | None) -> str:
        """相関値からヒートマップ用CSSクラスを返す。"""
        if value is None:
            return "corr-na"
        if value >= 0.7:
            return "corr-pos-strong"
        if value >= 0.3:
            return "corr-pos-medium"
        if value >= -0.3:
            return "corr-neutral"
        if value >= -0.7:
            return "corr-neg-medium"
        return "corr-neg-strong"


def _load_daily_returns(symbol: str, lookback_days: int) -> pd.Series | None:
    """シンボルの日足終値リターン系列を返す。データ不足時は None。"""
    csv_filename = SYMBOL_CSV_MAP.get(symbol)
    if not csv_filename:
        return None

    csv_path = DATA_DIR / csv_filename
    df_1h, _ = load_or_generate(csv_path)
    if df_1h.empty:
        return None

    tfs = get_all_timeframes(df_1h)
    df_daily = tfs.get("daily", pd.DataFrame())
    if df_daily.empty or len(df_daily) < 5:
        return None

    df_use = df_daily.tail(lookback_days + 1)
    returns = df_use["close"].pct_change().dropna()
    if len(returns) < 5:
        return None

    returns.name = symbol
    return returns


def calculate_correlation_matrix(
    symbols: list[str] | None = None,
    lookback_days: int = DEFAULT_LOOKBACK,
) -> CorrelationMatrix:
    """全対象シンボル間のピアソン相関係数マトリクスを計算する。

    Args:
        symbols: 対象シンボルリスト。None の場合は SUPPORTED_SYMBOLS 全件。
        lookback_days: 使用する日足データの本数。

    Returns:
        CorrelationMatrix オブジェクト。
    """
    if symbols is None:
        symbols = SUPPORTED_SYMBOLS

    # 各シンボルのリターン系列を取得
    series_map: dict[str, pd.Series] = {}
    for sym in symbols:
        s = _load_daily_returns(sym, lookback_days)
        if s is not None:
            series_map[sym] = s

    n = len(symbols)
    matrix: list[list[float | None]] = [[None] * n for _ in range(n)]
    data_points: dict[str, int] = {}

    for sym, s in series_map.items():
        data_points[sym] = len(s)

    for i, sym_a in enumerate(symbols):
        for j, sym_b in enumerate(symbols):
            if sym_a not in series_map or sym_b not in series_map:
                matrix[i][j] = None
                continue
            if sym_a == sym_b:
                matrix[i][j] = 1.0
                continue
            s_a = series_map[sym_a]
            s_b = series_map[sym_b]
            # 共通インデックスで相関計算
            common = s_a.index.intersection(s_b.index)
            if len(common) < 5:
                matrix[i][j] = None
                continue
            corr = float(np.corrcoef(s_a.loc[common], s_b.loc[common])[0, 1])
            # NaN ガード
            if np.isnan(corr):
                matrix[i][j] = None
            else:
                matrix[i][j] = round(corr, 3)

    return CorrelationMatrix(
        symbols=symbols,
        matrix=matrix,
        lookback_days=lookback_days,
        data_points=data_points,
    )


def correlation_label(value: float | None) -> str:
    """相関値を日本語ラベルに変換する。"""
    if value is None:
        return "---"
    if value >= 0.7:
        return "強い正相関"
    if value >= 0.3:
        return "中程度正相関"
    if value >= -0.3:
        return "相関なし"
    if value >= -0.7:
        return "中程度負相関"
    return "強い負相関"
