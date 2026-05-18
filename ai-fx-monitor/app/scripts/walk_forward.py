"""Phase 42: ウォークフォワード分析エンジン

全データを n_windows 個のウィンドウに分割し、各ウィンドウの
インサンプル(IS)期間でシグナル品質を計測し、アウトオブサンプル(OOS)期間で
検証する。IS/OOS の差異（過学習スコア）を算出する。

注文は一切発生しない。分析・集計のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.config import DATA_DIR, SUPPORTED_SYMBOLS, SYMBOL_CSV_MAP
from app.data.loader import load_or_generate
from app.data.resampler import get_all_timeframes
from app.strategy.risk import calculate_buy_setup, calculate_sell_setup
from app.strategy.rules import SIGNAL_BUY, SIGNAL_SELL, analyze_signal
from app.scripts.backtest import BacktestTrade, _simulate_outcome


# デフォルトパラメータ
DEFAULT_N_WINDOWS = 5
DEFAULT_IS_RATIO = 0.7      # IS期間を全ウィンドウの70%に設定
DEFAULT_WINDOW_BARS = 500   # 各ウィンドウのバー数（1時間足で約20日）
DEFAULT_STEP = 24           # 判定ステップ（1日ごと）
DEFAULT_FUTURE_BARS = 100   # SL/TP判定に使う未来バー数


@dataclass
class WFWindow:
    """1ウィンドウのIS/OOS結果。"""
    window_num: int
    is_start_bar: int
    is_end_bar: int
    oos_start_bar: int
    oos_end_bar: int

    # IS 統計
    is_trades: int = 0
    is_wins: int = 0
    is_losses: int = 0
    is_win_rate: float | None = None
    is_total_pips: float = 0.0
    is_avg_pips: float | None = None

    # OOS 統計
    oos_trades: int = 0
    oos_wins: int = 0
    oos_losses: int = 0
    oos_win_rate: float | None = None
    oos_total_pips: float = 0.0
    oos_avg_pips: float | None = None

    # 過学習指標
    overfitting_score: float | None = None  # IS勝率 - OOS勝率 (pct points)
    robustness_ratio: float | None = None   # OOS total_pips / IS total_pips


@dataclass
class WalkForwardResult:
    """ウォークフォワード分析の全体結果。"""
    symbol: str
    n_windows: int
    is_ratio: float
    window_bars: int
    step: int
    total_data_bars: int

    windows: list[WFWindow] = field(default_factory=list)

    # 集計
    avg_is_win_rate: float | None = None
    avg_oos_win_rate: float | None = None
    avg_is_pips: float | None = None
    avg_oos_pips: float | None = None
    avg_overfitting_score: float | None = None
    avg_robustness_ratio: float | None = None
    total_oos_trades: int = 0
    total_oos_wins: int = 0
    total_oos_losses: int = 0
    combined_oos_win_rate: float | None = None
    combined_oos_pips: float = 0.0
    assessment: str = ""


def _run_slice(
    df_full: pd.DataFrame,
    symbol: str,
    slice_start: int,
    slice_end: int,
    window: int,
    step: int,
    future_bars: int,
) -> tuple[int, int, int, float]:
    """[slice_start, slice_end] のデータでバックテストを実行して集計を返す。

    Returns:
        (trades, wins, losses, total_pips)
    """
    trades_list: list[BacktestTrade] = []

    start = slice_start + window
    end = slice_end - future_bars

    if start >= end:
        return 0, 0, 0, 0.0

    for i in range(start, end, step):
        hist = df_full.iloc[i - window: i].copy()
        tfs = get_all_timeframes(hist)
        result = analyze_signal(
            df_daily=tfs.get("daily", pd.DataFrame()),
            df_4h=tfs.get("4h", pd.DataFrame()),
            df_1h=tfs.get("1h", pd.DataFrame()),
        )

        if result.signal == SIGNAL_BUY:
            setup = calculate_buy_setup(tfs.get("1h", pd.DataFrame()), tfs.get("daily", pd.DataFrame()))
        elif result.signal == SIGNAL_SELL:
            setup = calculate_sell_setup(tfs.get("1h", pd.DataFrame()), tfs.get("daily", pd.DataFrame()))
        else:
            continue

        if not setup or not setup.is_valid:
            continue
        if not setup.entry_price or not setup.stop_loss or not setup.take_profit:
            continue

        trade = BacktestTrade(
            bar_index=i,
            signal=result.signal,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            risk_reward=setup.risk_reward or 0.0,
        )
        future = df_full.iloc[i: i + future_bars]
        trade = _simulate_outcome(trade, future, symbol)
        trades_list.append(trade)

    closed = [t for t in trades_list if t.outcome in ("win", "loss")]
    wins = sum(1 for t in closed if t.outcome == "win")
    losses = len(closed) - wins
    total_pips = sum(t.pnl_pips for t in closed)
    return len(closed), wins, losses, round(total_pips, 1)


def _fill_window_stats(w: WFWindow) -> None:
    """WFWindow の統計フィールドを埋める。"""
    # IS
    is_closed = w.is_wins + w.is_losses
    w.is_win_rate = round(w.is_wins / is_closed * 100, 1) if is_closed > 0 else None
    w.is_avg_pips = round(w.is_total_pips / is_closed, 1) if is_closed > 0 else None

    # OOS
    oos_closed = w.oos_wins + w.oos_losses
    w.oos_win_rate = round(w.oos_wins / oos_closed * 100, 1) if oos_closed > 0 else None
    w.oos_avg_pips = round(w.oos_total_pips / oos_closed, 1) if oos_closed > 0 else None

    # 過学習スコア
    if w.is_win_rate is not None and w.oos_win_rate is not None:
        w.overfitting_score = round(w.is_win_rate - w.oos_win_rate, 1)

    # ロバストネス比率（OOS/IS pips）
    if w.is_total_pips != 0:
        w.robustness_ratio = round(w.oos_total_pips / w.is_total_pips, 2)


def run_walk_forward(
    symbol: str,
    n_windows: int = DEFAULT_N_WINDOWS,
    is_ratio: float = DEFAULT_IS_RATIO,
    window_bars: int = DEFAULT_WINDOW_BARS,
    step: int = DEFAULT_STEP,
    future_bars: int = DEFAULT_FUTURE_BARS,
) -> WalkForwardResult:
    """ウォークフォワード分析を実行する。

    Args:
        symbol:      通貨ペア
        n_windows:   ウィンドウ数（分割数）
        is_ratio:    各ウィンドウ内のIS比率（0.5〜0.9）
        window_bars: 各ウィンドウの総バー数
        step:        判定ステップ（バー数）
        future_bars: SL/TP判定用の未来バー数
    """
    csv_filename = SYMBOL_CSV_MAP.get(symbol)
    if not csv_filename:
        raise ValueError(f"未対応シンボル: {symbol}")

    csv_path = DATA_DIR / csv_filename
    df_full, _ = load_or_generate(csv_path, symbol=symbol)

    result = WalkForwardResult(
        symbol=symbol,
        n_windows=n_windows,
        is_ratio=is_ratio,
        window_bars=window_bars,
        step=step,
        total_data_bars=len(df_full),
    )

    total_needed = n_windows * window_bars + future_bars + window_bars
    if len(df_full) < total_needed:
        result.assessment = f"データ不足（{len(df_full)}本、必要: {total_needed}本以上）"
        return result

    # ウィンドウを設定（データ末尾から逆算して n_windows 個取る）
    data_end = len(df_full) - future_bars
    is_bars = int(window_bars * is_ratio)
    oos_bars = window_bars - is_bars

    windows: list[WFWindow] = []
    for k in range(n_windows):
        w_end = data_end - k * window_bars
        w_start = w_end - window_bars
        if w_start < window_bars:
            break  # 判定用の lookback が足りない場合はスキップ
        is_end = w_start + is_bars
        oos_end = w_end

        w = WFWindow(
            window_num=n_windows - k,  # 古いウィンドウを小さい番号にする
            is_start_bar=w_start,
            is_end_bar=is_end,
            oos_start_bar=is_end,
            oos_end_bar=oos_end,
        )

        # IS バックテスト
        is_closed, is_wins, is_losses, is_pips = _run_slice(
            df_full, symbol, w_start, is_end, window_bars, step, future_bars
        )
        w.is_trades = is_closed
        w.is_wins = is_wins
        w.is_losses = is_losses
        w.is_total_pips = is_pips

        # OOS バックテスト
        oos_closed, oos_wins, oos_losses, oos_pips = _run_slice(
            df_full, symbol, is_end, oos_end, window_bars, step, future_bars
        )
        w.oos_trades = oos_closed
        w.oos_wins = oos_wins
        w.oos_losses = oos_losses
        w.oos_total_pips = oos_pips

        _fill_window_stats(w)
        windows.append(w)

    # 時系列順に並べ直す
    windows.sort(key=lambda x: x.window_num)
    result.windows = windows

    if not windows:
        result.assessment = "有効なウィンドウが得られませんでした"
        return result

    # 全体集計
    is_rates = [w.is_win_rate for w in windows if w.is_win_rate is not None]
    oos_rates = [w.oos_win_rate for w in windows if w.oos_win_rate is not None]
    oos_scores = [w.overfitting_score for w in windows if w.overfitting_score is not None]
    rob_ratios = [w.robustness_ratio for w in windows if w.robustness_ratio is not None]

    result.avg_is_win_rate = round(sum(is_rates) / len(is_rates), 1) if is_rates else None
    result.avg_oos_win_rate = round(sum(oos_rates) / len(oos_rates), 1) if oos_rates else None
    result.avg_is_pips = round(sum(w.is_total_pips for w in windows) / len(windows), 1)
    result.avg_oos_pips = round(sum(w.oos_total_pips for w in windows) / len(windows), 1)
    result.avg_overfitting_score = round(sum(oos_scores) / len(oos_scores), 1) if oos_scores else None
    result.avg_robustness_ratio = round(sum(rob_ratios) / len(rob_ratios), 2) if rob_ratios else None

    result.total_oos_trades = sum(w.oos_trades for w in windows)
    result.total_oos_wins = sum(w.oos_wins for w in windows)
    result.total_oos_losses = sum(w.oos_losses for w in windows)
    result.combined_oos_pips = round(sum(w.oos_total_pips for w in windows), 1)
    total_oos_closed = result.total_oos_wins + result.total_oos_losses
    result.combined_oos_win_rate = (
        round(result.total_oos_wins / total_oos_closed * 100, 1) if total_oos_closed > 0 else None
    )

    result.assessment = _assess(result)
    return result


def _assess(r: WalkForwardResult) -> str:
    """ウォークフォワード結果を日本語で評価する。"""
    score = r.avg_overfitting_score
    rob = r.avg_robustness_ratio
    oos_wr = r.avg_oos_win_rate

    if score is None and oos_wr is None:
        return "データ不足のため評価できません"

    parts = []
    if score is not None:
        if score < 5:
            parts.append("過学習リスク: 低（IS/OOS乖離 < 5%）")
        elif score < 15:
            parts.append("過学習リスク: 中（IS/OOS乖離 5〜15%）")
        else:
            parts.append("過学習リスク: 高（IS/OOS乖離 ≥ 15%）")

    if rob is not None:
        if rob >= 0.8:
            parts.append("ロバストネス: 高（OOS/IS比 ≥ 0.8）")
        elif rob >= 0.5:
            parts.append("ロバストネス: 中")
        else:
            parts.append("ロバストネス: 低（OOS/IS比 < 0.5）")

    if oos_wr is not None:
        if oos_wr >= 55:
            parts.append("OOS勝率: 良好（≥ 55%）")
        elif oos_wr >= 50:
            parts.append("OOS勝率: やや良好")
        else:
            parts.append("OOS勝率: 低調（< 50%）")

    return " / ".join(parts) if parts else "評価データ不足"
