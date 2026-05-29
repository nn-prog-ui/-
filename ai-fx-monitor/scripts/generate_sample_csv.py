#!/usr/bin/env python3
"""テスト用サンプルCSV生成スクリプト

開発・テスト用途のみ。実際の取引には使用しないこと。

使い方:
    python scripts/generate_sample_csv.py              # 全ペア生成
    python scripts/generate_sample_csv.py --symbol AUD/JPY  # 指定ペアのみ

Phase 83: AUD/JPY・AUD/USD・EUR/GBP・GBP/JPY を追加
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

# 通貨ペアごとの設定（シンボル: (CSVファイル名, ベース価格, ボラティリティ係数)）
PAIR_CONFIG: dict[str, tuple[str, float, float]] = {
    "USD/JPY": ("USDJPY_1h.csv", 150.0,  0.0015),
    "EUR/USD": ("EURUSD_1h.csv",   1.085, 0.0008),
    "GBP/USD": ("GBPUSD_1h.csv",   1.265, 0.0010),
    "EUR/JPY": ("EURJPY_1h.csv", 162.0,  0.0015),
    "AUD/JPY": ("AUDJPY_1h.csv",  97.0,  0.0015),
    "AUD/USD": ("AUDUSD_1h.csv",   0.644, 0.0008),
    "EUR/GBP": ("EURGBP_1h.csv",   0.850, 0.0006),
    "GBP/JPY": ("GBPJPY_1h.csv", 192.0,  0.0018),
}


def generate_sample_csv(
    output_path: Path,
    n_bars: int = 3000,
    base_price: float = 150.0,
    volatility: float = 0.0015,
    seed: int = 42,
) -> None:
    np.random.seed(seed)

    periods = pd.date_range(
        end=pd.Timestamp("2024-12-31 23:00:00"),
        periods=n_bars,
        freq="1h",
    )
    # 3000本 = 約125日 ≥ 日足75MA計算に必要な75日

    # 緩やかな上昇トレンド + ランダムウォーク
    returns = np.random.normal(0.00005, volatility, n_bars)
    closes = base_price * np.cumprod(1 + returns)

    opens = np.roll(closes, 1)
    opens[0] = base_price

    noise_scale = base_price * 0.0004
    noise_high = np.abs(np.random.normal(0, noise_scale, n_bars))
    noise_low  = np.abs(np.random.normal(0, noise_scale, n_bars))
    highs = np.maximum(opens, closes) + noise_high
    lows  = np.minimum(opens, closes) - noise_low

    volumes = np.random.randint(500, 8000, n_bars)

    # 小数点桁数: JPYペアは3桁、非JPYは5桁
    decimals = 3 if base_price > 10 else 5

    df = pd.DataFrame(
        {
            "datetime": periods,
            "open":   np.round(opens, decimals),
            "high":   np.round(highs, decimals),
            "low":    np.round(lows,  decimals),
            "close":  np.round(closes, decimals),
            "volume": volumes,
        }
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"  ✅ {output_path.name} ({n_bars}行, 価格範囲: {closes.min():.{decimals}f}〜{closes.max():.{decimals}f})")


def main() -> None:
    parser = argparse.ArgumentParser(description="FX サンプルCSV生成（テスト用）")
    parser.add_argument("--symbol", default="", help="生成するシンボル（省略時は全ペア）")
    parser.add_argument("--bars",   type=int, default=3000, help="生成本数（デフォルト: 3000）")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data" / "raw"

    pairs = PAIR_CONFIG
    if args.symbol:
        sym = args.symbol.upper().replace("-", "/")
        if sym not in pairs:
            print(f"❌ 未対応シンボル: {sym}")
            print(f"   対応ペア: {', '.join(pairs.keys())}")
            sys.exit(1)
        pairs = {sym: pairs[sym]}

    print(f"\nサンプルCSV生成開始（{len(pairs)}ペア, {args.bars}本/ペア）")
    print("注意: このデータはテスト用ダミーデータです。実際の取引には使用しないでください。\n")

    for symbol, (csv_name, base_price, volatility) in pairs.items():
        output = data_dir / csv_name
        print(f"  {symbol} → {csv_name}")
        generate_sample_csv(output, n_bars=args.bars, base_price=base_price, volatility=volatility)

    print(f"\n生成先: {data_dir}")
    print("完了")


if __name__ == "__main__":
    main()
