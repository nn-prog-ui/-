"""戦略パラメータ最適化スクリプト（Phase 36）

バックテストを使って MA期間・RSI閾値の最適値をグリッドサーチで探索する。
実際の注文は一切発生しない。分析・集計のみ。

CLI 使い方:
    python -m app.scripts.optimizer --symbol USD/JPY
    python -m app.scripts.optimizer --symbol USD/JPY --ma-short 10,15,20 --ma-long 50,75,100 --metric total_pips
"""
from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.config import DATA_DIR, SUPPORTED_SYMBOLS, SYMBOL_CSV_MAP
from app.data.loader import load_or_generate
from app.data.resampler import get_all_timeframes
from app.indicators.atr import get_recent_high, get_recent_low, is_atr_abnormal
from app.indicators.moving_average import get_ma_trend
from app.indicators.rsi import get_rsi_value
from app.strategy.risk import TradeSetup, calculate_buy_setup, calculate_sell_setup
from app.strategy.rules import SIGNAL_BUY, SIGNAL_SELL, SIGNAL_SKIP

# 注意：本モジュールの analyze_with_params() は最適化専用。
# 本番の analyze_signal() (rules.py) は変更しない。

VALID_METRICS = ["win_rate", "total_pips", "avg_pips"]

# デフォルトのグリッド候補値
DEFAULT_MA_SHORT = [10, 15, 20, 25]
DEFAULT_MA_LONG  = [50, 75, 100]
DEFAULT_RSI_BUY_MAX = [65, 70, 75]

MAX_COMBINATIONS = 200  # 組み合わせ上限（過大なグリッドを防ぐ）


@dataclass
class OptimizeParams:
    """最適化で試す1組のパラメータ。"""
    ma_short: int = 20
    ma_long: int = 75
    rsi_buy_max: int = 70   # BUY 条件: RSI < rsi_buy_max かつ RSI >= rsi_buy_min
    rsi_buy_min: int = 40
    rsi_sell_min: int = 30  # SELL 条件: RSI > rsi_sell_min かつ RSI <= rsi_sell_max
    rsi_sell_max: int = 60


@dataclass
class OptimizeResult:
    """1パラメータ組み合わせのバックテスト集計。"""
    params: OptimizeParams
    symbol: str
    wins: int = 0
    losses: int = 0
    open_count: int = 0
    total_pips: float = 0.0
    win_rate: float | None = None
    avg_pips: float | None = None
    trade_count: int = 0
    score: float = 0.0  # 選択メトリックの値

    @property
    def closed(self) -> int:
        return self.wins + self.losses


def _analyze_with_params(
    df_daily: pd.DataFrame,
    df_4h: pd.DataFrame,
    df_1h: pd.DataFrame,
    params: OptimizeParams,
) -> str:
    """パラメータを注入した簡易シグナル判定。本番ルールは一切変更しない。"""
    if df_daily.empty or len(df_daily) < params.ma_long:
        return SIGNAL_SKIP
    if df_4h.empty or len(df_4h) < params.ma_long:
        return SIGNAL_SKIP
    if df_1h.empty or len(df_1h) < 75:
        return SIGNAL_SKIP

    daily_trend = get_ma_trend(df_daily, short=params.ma_short, long=params.ma_long)
    h4_trend    = get_ma_trend(df_4h,    short=params.ma_short, long=params.ma_long)
    rsi         = get_rsi_value(df_1h)
    atr_bad     = is_atr_abnormal(df_1h)
    recent_high = get_recent_high(df_1h, lookback=20)
    recent_low  = get_recent_low(df_1h,  lookback=20)

    if atr_bad or rsi is None:
        return SIGNAL_SKIP

    # 1時間足ブレイクアウト判定
    h1_close = float(df_1h["close"].iloc[-1])
    h1_high_ref = df_1h["high"].iloc[-20:-1].max() if len(df_1h) >= 20 else None
    h1_low_ref  = df_1h["low"].iloc[-20:-1].min()  if len(df_1h) >= 20 else None
    h1_high_breakout = h1_high_ref is not None and h1_close > h1_high_ref
    h1_low_breakout  = h1_low_ref  is not None and h1_close < h1_low_ref

    buy_ok = (
        daily_trend == "上昇"
        and h4_trend == "上昇"
        and h1_high_breakout
        and params.rsi_buy_min <= rsi < params.rsi_buy_max
    )
    sell_ok = (
        daily_trend == "下降"
        and h4_trend == "下降"
        and h1_low_breakout
        and params.rsi_sell_min < rsi <= params.rsi_sell_max
    )

    if buy_ok and not sell_ok:
        return SIGNAL_BUY
    if sell_ok and not buy_ok:
        return SIGNAL_SELL
    return SIGNAL_SKIP


def _pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def _run_one(
    symbol: str,
    df_1h_full: pd.DataFrame,
    params: OptimizeParams,
    window: int = 300,
    step: int = 24,
    future_bars: int = 80,
) -> OptimizeResult:
    """1パラメータ組み合わせでミニバックテストを実行する。"""
    wins = losses = open_count = 0
    total_pips = 0.0
    pip = _pip_size(symbol)

    start = window
    end   = len(df_1h_full) - future_bars

    for i in range(start, end, step):
        slice_1h = df_1h_full.iloc[i - window : i].copy()
        tfs = get_all_timeframes(slice_1h)
        signal = _analyze_with_params(
            tfs.get("daily", pd.DataFrame()),
            tfs.get("4h",    pd.DataFrame()),
            tfs.get("1h",    pd.DataFrame()),
            params,
        )
        if signal == SIGNAL_BUY:
            setup: TradeSetup | None = calculate_buy_setup(
                tfs.get("1h", pd.DataFrame()), tfs.get("daily", pd.DataFrame())
            )
        elif signal == SIGNAL_SELL:
            setup = calculate_sell_setup(
                tfs.get("1h", pd.DataFrame()), tfs.get("daily", pd.DataFrame())
            )
        else:
            continue

        if not setup or not setup.is_valid:
            continue
        if not setup.entry_price or not setup.stop_loss or not setup.take_profit:
            continue

        future = df_1h_full.iloc[i : i + future_bars]
        outcome = "open"
        pnl = 0.0
        for _, row in future.iterrows():
            price = float(row["close"])
            if signal == SIGNAL_BUY:
                if price >= setup.take_profit:
                    outcome, pnl = "win", round((price - setup.entry_price) / pip, 1)
                    break
                if price <= setup.stop_loss:
                    outcome, pnl = "loss", round((price - setup.entry_price) / pip, 1)
                    break
            else:
                if price <= setup.take_profit:
                    outcome, pnl = "win", round((setup.entry_price - price) / pip, 1)
                    break
                if price >= setup.stop_loss:
                    outcome, pnl = "loss", round((setup.entry_price - price) / pip, 1)
                    break

        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1
        else:
            open_count += 1
        if outcome != "open":
            total_pips += pnl

    closed = wins + losses
    win_rate = (wins / closed * 100) if closed > 0 else None
    avg_pips = (total_pips / closed) if closed > 0 else None

    return OptimizeResult(
        params=params,
        symbol=symbol,
        wins=wins,
        losses=losses,
        open_count=open_count,
        total_pips=round(total_pips, 1),
        win_rate=win_rate,
        avg_pips=avg_pips,
        trade_count=closed + open_count,
    )


def _compute_score(result: OptimizeResult, metric: str) -> float:
    """選択メトリックのスコアを返す（比較用）。"""
    if metric == "win_rate":
        return result.win_rate if result.win_rate is not None else -1.0
    if metric == "total_pips":
        return result.total_pips
    if metric == "avg_pips":
        return result.avg_pips if result.avg_pips is not None else -9999.0
    return 0.0


def optimize(
    symbol: str,
    ma_short_values: list[int] | None = None,
    ma_long_values: list[int]  | None = None,
    rsi_buy_max_values: list[int] | None = None,
    metric: str = "win_rate",
    window: int = 300,
    step: int = 24,
    future_bars: int = 80,
) -> list[OptimizeResult]:
    """グリッドサーチで最適パラメータを探索し、スコア降順で返す。

    Args:
        symbol: 通貨ペア
        ma_short_values: 短期MA候補リスト（例: [10,20,30]）
        ma_long_values: 長期MA候補リスト（例: [50,75,100]）
        rsi_buy_max_values: RSI BUY上限候補リスト（例: [65,70,75]）
        metric: "win_rate" | "total_pips" | "avg_pips"
        window: バックテスト用ウィンドウ幅
        step: 判定ステップ幅
        future_bars: 未来バー数

    Returns:
        OptimizeResult のリスト（スコア降順）
    """
    if metric not in VALID_METRICS:
        raise ValueError(f"metric は {VALID_METRICS} のいずれかにしてください。")

    ma_short_values    = ma_short_values    or DEFAULT_MA_SHORT
    ma_long_values     = ma_long_values     or DEFAULT_MA_LONG
    rsi_buy_max_values = rsi_buy_max_values or DEFAULT_RSI_BUY_MAX

    # 不正な組み合わせを除外（short < long）
    combos = [
        (s, l, r)
        for s, l, r in itertools.product(ma_short_values, ma_long_values, rsi_buy_max_values)
        if s < l
    ]

    if len(combos) > MAX_COMBINATIONS:
        raise ValueError(
            f"パラメータ組み合わせ数 {len(combos)} が上限 {MAX_COMBINATIONS} を超えています。"
            "範囲を絞ってください。"
        )

    csv_filename = SYMBOL_CSV_MAP.get(symbol)
    if not csv_filename:
        raise ValueError(f"未対応のシンボル: {symbol}")

    csv_path = DATA_DIR / csv_filename
    df_1h_full, _ = load_or_generate(csv_path)

    if df_1h_full.empty or len(df_1h_full) < window + future_bars:
        raise ValueError(
            f"データ不足: {len(df_1h_full)}本（必要: {window + future_bars}本以上）"
        )

    results: list[OptimizeResult] = []
    for ma_s, ma_l, rsi_max in combos:
        params = OptimizeParams(
            ma_short=ma_s, ma_long=ma_l,
            rsi_buy_max=rsi_max, rsi_buy_min=40,
            rsi_sell_min=30, rsi_sell_max=100 - rsi_max,
        )
        r = _run_one(symbol, df_1h_full, params, window=window, step=step, future_bars=future_bars)
        r.score = _compute_score(r, metric)
        results.append(r)

    results.sort(key=lambda x: x.score, reverse=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FX戦略パラメータ最適化（注文なし・分析専用）"
    )
    parser.add_argument("--symbol", default="USD/JPY",
                        help=f"通貨ペア（デフォルト: USD/JPY）")
    parser.add_argument("--ma-short", default="10,15,20,25",
                        help="短期MA候補（カンマ区切り、デフォルト: 10,15,20,25）")
    parser.add_argument("--ma-long", default="50,75,100",
                        help="長期MA候補（カンマ区切り、デフォルト: 50,75,100）")
    parser.add_argument("--rsi-max", default="65,70,75",
                        help="RSI BUY上限候補（カンマ区切り、デフォルト: 65,70,75）")
    parser.add_argument("--metric", default="win_rate",
                        choices=VALID_METRICS,
                        help=f"最適化メトリック（デフォルト: win_rate）")
    parser.add_argument("--window", type=int, default=300)
    parser.add_argument("--step", type=int, default=24)
    args = parser.parse_args()

    ma_s  = [int(x) for x in args.ma_short.split(",")]
    ma_l  = [int(x) for x in args.ma_long.split(",")]
    rsi_m = [int(x) for x in args.rsi_max.split(",")]

    print(f"最適化開始: {args.symbol} / metric={args.metric}")
    print(f"  MA短期候補: {ma_s}")
    print(f"  MA長期候補: {ma_l}")
    print(f"  RSI上限候補: {rsi_m}")
    print(f"  ※ 実際の注文は一切発生しません")

    results = optimize(
        symbol=args.symbol,
        ma_short_values=ma_s,
        ma_long_values=ma_l,
        rsi_buy_max_values=rsi_m,
        metric=args.metric,
        window=args.window,
        step=args.step,
    )

    print(f"\n上位10件（{args.metric} 降順）:")
    print(f"{'rank':>4} {'MA短':>5} {'MA長':>5} {'RSI上':>6} "
          f"{'取引':>5} {'勝ち':>5} {'負け':>5} "
          f"{'勝率%':>7} {'合計pips':>9} {'平均pips':>9}")
    print("-" * 75)
    for i, r in enumerate(results[:10], 1):
        wr  = f"{r.win_rate:.1f}" if r.win_rate is not None else "---"
        avg = f"{r.avg_pips:+.1f}" if r.avg_pips is not None else "---"
        print(
            f"{i:>4} {r.params.ma_short:>5} {r.params.ma_long:>5} {r.params.rsi_buy_max:>6} "
            f"{r.trade_count:>5} {r.wins:>5} {r.losses:>5} "
            f"{wr:>7} {r.total_pips:>+9.1f} {avg:>9}"
        )

    if results:
        best = results[0]
        print(f"\n★ 推奨パラメータ（{args.metric} 最優秀）:")
        print(f"  MA短期: {best.params.ma_short}  MA長期: {best.params.ma_long}  RSI上限(BUY): {best.params.rsi_buy_max}")
        if best.win_rate is not None:
            print(f"  勝率: {best.win_rate:.1f}%  合計pips: {best.total_pips:+.1f}")
        print(f"\n  ※ バックテストは過去データのシミュレーションです。")
        print(f"  ※ 将来の成績を保証するものではありません。")


if __name__ == "__main__":
    main()
