#!/usr/bin/env python3
"""テスト用サンプルCSV生成スクリプト

開発・テスト用途のみ。実際の取引には使用しないこと。

使い方:
    python scripts/generate_sample_csv.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd


def generate_sample_csv(
    output_path: Path,
    n_bars: int = 3000,
    base_price: float = 150.0,
) -> None:
    np.random.seed(42)

    periods = pd.date_range(
        end=pd.Timestamp("2024-12-31 23:00:00"),
        periods=n_bars,
        freq="1h",
    )
    # 3000本 = 約125日 ≥ 日足75MA計算に必要な75日

    # 緩やかな上昇トレンド + ランダムウォーク
    returns = np.random.normal(0.00005, 0.0015, n_bars)
    closes = base_price * np.cumprod(1 + returns)

    opens = np.roll(closes, 1)
    opens[0] = base_price

    noise_high = np.abs(np.random.normal(0, 0.06, n_bars))
    noise_low = np.abs(np.random.normal(0, 0.06, n_bars))
    highs = np.maximum(opens, closes) + noise_high
    lows = np.minimum(opens, closes) - noise_low

    volumes = np.random.randint(500, 8000, n_bars)

    df = pd.DataFrame(
        {
            "datetime": periods,
            "open": np.round(opens, 3),
            "high": np.round(highs, 3),
            "low": np.round(lows, 3),
            "close": np.round(closes, 3),
            "volume": volumes,
        }
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"サンプルCSV生成完了: {output_path} ({n_bars}行)")
    print(f"  期間: {periods[0]} 〜 {periods[-1]}")
    print(f"  価格範囲: {closes.min():.3f} 〜 {closes.max():.3f}")
    print("\n注意: このデータはテスト用ダミーデータです。実際の取引には使用しないでください。")


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    output = project_root / "data" / "raw" / "USDJPY_1h.csv"
    generate_sample_csv(output)
