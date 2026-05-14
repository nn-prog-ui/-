"""バックテストCLI

過去のCSVデータを使って判定ルールの精度を検証する。
実際の注文は一切発生しない。分析・集計のみ。

使い方:
    python -m app.scripts.backtest --symbol USD/JPY --window 500
    python -m app.scripts.backtest --symbol EUR/USD --window 200 --step 24
    python -m app.scripts.backtest  # デフォルト: 全ペア、直近500本、ステップ24本
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.config import DATA_DIR, SUPPORTED_SYMBOLS, SYMBOL_CSV_MAP
from app.data.loader import load_or_generate
from app.data.resampler import get_all_timeframes
from app.strategy.risk import TradeSetup, calculate_buy_setup, calculate_sell_setup
from app.strategy.rules import SIGNAL_BUY, SIGNAL_SELL, SIGNAL_SKIP, analyze_signal


@dataclass
class BacktestTrade:
    """バックテスト上の1取引。"""
    bar_index: int
    signal: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    outcome: str = ""      # "win" | "loss" | "open"
    exit_price: float = 0.0
    pnl_pips: float = 0.0


@dataclass
class BacktestResult:
    """バックテスト集計結果。"""
    symbol: str
    total_bars: int
    signals_generated: int
    buy_signals: int
    sell_signals: int
    skip_signals: int
    valid_setups: int       # SL/TPが設定できた取引数
    wins: int = 0
    losses: int = 0
    open_count: int = 0
    win_rate: float | None = None
    total_pips: float = 0.0
    avg_pips: float | None = None
    max_win_pips: float = 0.0
    max_loss_pips: float = 0.0
    trades: list[BacktestTrade] = field(default_factory=list)


def _pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def _simulate_outcome(
    trade: BacktestTrade,
    future_bars: pd.DataFrame,
    symbol: str,
) -> BacktestTrade:
    """未来バーのcloseでSL/TPに到達したか判定してtradeを更新する。"""
    pip = _pip_size(symbol)
    for _, row in future_bars.iterrows():
        price = float(row["close"])
        if trade.signal == SIGNAL_BUY:
            if price >= trade.take_profit:
                trade.outcome = "win"
                trade.exit_price = price
                trade.pnl_pips = round((price - trade.entry_price) / pip, 1)
                return trade
            if price <= trade.stop_loss:
                trade.outcome = "loss"
                trade.exit_price = price
                trade.pnl_pips = round((price - trade.entry_price) / pip, 1)
                return trade
        else:  # SELL
            if price <= trade.take_profit:
                trade.outcome = "win"
                trade.exit_price = price
                trade.pnl_pips = round((trade.entry_price - price) / pip, 1)
                return trade
            if price >= trade.stop_loss:
                trade.outcome = "loss"
                trade.exit_price = price
                trade.pnl_pips = round((trade.entry_price - price) / pip, 1)
                return trade
    trade.outcome = "open"
    return trade


def run_backtest(
    symbol: str,
    window: int = 500,
    step: int = 24,
    future_bars: int = 100,
) -> BacktestResult:
    """指定シンボルのバックテストを実行する。

    Args:
        symbol: 通貨ペア（例: "USD/JPY"）
        window: 判定に使う直近バー数（例: 500本 = 1時間足なら約20日）
        step: 判定をずらす本数（例: 24 = 1日ごとに判定）
        future_bars: SL/TP到達チェックに使う未来バー数
    """
    csv_filename = SYMBOL_CSV_MAP.get(symbol)
    if not csv_filename:
        raise ValueError(f"未対応のシンボル: {symbol}")

    csv_path = DATA_DIR / csv_filename
    df_1h_full = load_or_generate(csv_path, symbol)

    if df_1h_full.empty or len(df_1h_full) < window + future_bars:
        print(f"[{symbol}] データ不足: {len(df_1h_full)}本（必要: {window + future_bars}本以上）")
        return BacktestResult(
            symbol=symbol,
            total_bars=len(df_1h_full),
            signals_generated=0,
            buy_signals=0,
            sell_signals=0,
            skip_signals=0,
            valid_setups=0,
        )

    trades: list[BacktestTrade] = []
    buy_count = sell_count = skip_count = valid_count = 0

    # 最初の window 本から始めて step 本ずつ進む（最後の future_bars 本は未来用に残す）
    start = window
    end = len(df_1h_full) - future_bars

    for i in range(start, end, step):
        slice_1h = df_1h_full.iloc[i - window : i].copy()
        timeframes = get_all_timeframes(slice_1h)
        df_daily = timeframes.get("daily", pd.DataFrame())
        df_4h = timeframes.get("4h", pd.DataFrame())
        df_h1 = timeframes.get("1h", pd.DataFrame())

        result = analyze_signal(df_daily=df_daily, df_4h=df_4h, df_1h=df_h1)

        if result.signal == SIGNAL_BUY:
            buy_count += 1
            setup: TradeSetup | None = calculate_buy_setup(df_h1, df_daily)
        elif result.signal == SIGNAL_SELL:
            sell_count += 1
            setup = calculate_sell_setup(df_h1, df_daily)
        else:
            skip_count += 1
            continue

        if not setup or not setup.is_valid:
            continue
        if not setup.entry_price or not setup.stop_loss or not setup.take_profit:
            continue

        valid_count += 1
        trade = BacktestTrade(
            bar_index=i,
            signal=result.signal,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            risk_reward=setup.risk_reward or 0.0,
        )

        future = df_1h_full.iloc[i : i + future_bars]
        trade = _simulate_outcome(trade, future, symbol)
        trades.append(trade)

    wins = sum(1 for t in trades if t.outcome == "win")
    losses = sum(1 for t in trades if t.outcome == "loss")
    open_count = sum(1 for t in trades if t.outcome == "open")
    closed = wins + losses
    win_rate = (wins / closed * 100) if closed > 0 else None
    total_pips = sum(t.pnl_pips for t in trades if t.outcome != "open")
    avg_pips = (total_pips / closed) if closed > 0 else None
    max_win = max((t.pnl_pips for t in trades if t.outcome == "win"), default=0.0)
    max_loss = min((t.pnl_pips for t in trades if t.outcome == "loss"), default=0.0)

    return BacktestResult(
        symbol=symbol,
        total_bars=len(df_1h_full),
        signals_generated=buy_count + sell_count + skip_count,
        buy_signals=buy_count,
        sell_signals=sell_count,
        skip_signals=skip_count,
        valid_setups=valid_count,
        wins=wins,
        losses=losses,
        open_count=open_count,
        win_rate=win_rate,
        total_pips=total_pips,
        avg_pips=avg_pips,
        max_win_pips=max_win,
        max_loss_pips=max_loss,
        trades=trades,
    )


def print_result(r: BacktestResult) -> None:
    print(f"\n{'='*50}")
    print(f"  バックテスト結果: {r.symbol}")
    print(f"{'='*50}")
    print(f"  総データ本数      : {r.total_bars} 本")
    print(f"  判定回数          : {r.signals_generated} 回")
    print(f"    BUY             : {r.buy_signals}")
    print(f"    SELL            : {r.sell_signals}")
    print(f"    SKIP（見送り）   : {r.skip_signals}")
    print(f"  有効セットアップ  : {r.valid_setups} 件")
    print(f"  勝ち              : {r.wins}")
    print(f"  負け              : {r.losses}")
    print(f"  未決済            : {r.open_count}")
    if r.win_rate is not None:
        print(f"  勝率              : {r.win_rate:.1f}%")
    else:
        print(f"  勝率              : ---（決済なし）")
    print(f"  合計損益(pips)    : {r.total_pips:+.1f}")
    if r.avg_pips is not None:
        print(f"  平均損益(pips)    : {r.avg_pips:+.1f}")
    if r.max_win_pips:
        print(f"  最大勝ち(pips)    : +{r.max_win_pips:.1f}")
    if r.max_loss_pips:
        print(f"  最大負け(pips)    : {r.max_loss_pips:.1f}")
    print(f"\n  ※ バックテストは過去データのシミュレーションです。")
    print(f"  ※ 将来の成績を保証するものではありません。")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FX判定ルールのバックテスト（注文なし・分析専用）"
    )
    parser.add_argument(
        "--symbol", default=None,
        help=f"通貨ペア。省略時は全ペア。選択肢: {', '.join(SUPPORTED_SYMBOLS)}"
    )
    parser.add_argument(
        "--window", type=int, default=500,
        help="判定に使う直近の1時間足バー数（デフォルト: 500）"
    )
    parser.add_argument(
        "--step", type=int, default=24,
        help="判定をずらす本数（デフォルト: 24 = 1日ごと）"
    )
    parser.add_argument(
        "--future", type=int, default=100,
        help="SL/TP到達チェックの未来バー数（デフォルト: 100）"
    )
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else SUPPORTED_SYMBOLS

    print(f"バックテスト開始")
    print(f"  対象ペア: {', '.join(symbols)}")
    print(f"  window={args.window}本 / step={args.step}本 / future={args.future}本")
    print(f"  ※ 実際の注文は一切発生しません")

    results = []
    for sym in symbols:
        try:
            r = run_backtest(sym, window=args.window, step=args.step, future_bars=args.future)
            print_result(r)
            results.append(r)
        except Exception as exc:
            print(f"[{sym}] エラー: {exc}")

    if len(results) > 1:
        print(f"\n{'='*50}")
        print("  全ペア合計サマリー")
        print(f"{'='*50}")
        total_valid = sum(r.valid_setups for r in results)
        total_wins = sum(r.wins for r in results)
        total_losses = sum(r.losses for r in results)
        total_pips_all = sum(r.total_pips for r in results)
        closed_all = total_wins + total_losses
        wr = (total_wins / closed_all * 100) if closed_all > 0 else None
        print(f"  有効セットアップ  : {total_valid} 件")
        print(f"  勝ち / 負け       : {total_wins} / {total_losses}")
        print(f"  勝率              : {wr:.1f}%" if wr is not None else "  勝率              : ---")
        print(f"  合計損益(pips)    : {total_pips_all:+.1f}")


if __name__ == "__main__":
    main()
