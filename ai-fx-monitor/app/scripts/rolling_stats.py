"""Phase 55: ローリング成績分析（Rolling Performance Analysis）

直近 N トレードのウィンドウで勝率・期待値・プロフィットファクターを計算し、
成績トレンドを可視化する。注文は一切発生しない。集計・可視化のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db

VALID_WINDOWS = {10, 20, 30, 50}
DEFAULT_WINDOW = 20

TREND_IMPROVING = "improving"
TREND_STABLE = "stable"
TREND_DECLINING = "declining"
TREND_INSUFFICIENT = "insufficient"


@dataclass
class RollingPoint:
    trade_index: int        # 1-based index in chronological order
    created_at: str
    symbol: str
    pnl_pips: float
    outcome: str            # "win" or "loss"
    # rolling window values (None if window not yet full)
    win_rate: float | None = None
    expectancy: float | None = None
    profit_factor: float | None = None
    cumulative_pips: float = 0.0


@dataclass
class RollingReport:
    window: int
    symbol: str | None
    total_trades: int
    points: list[RollingPoint] = field(default_factory=list)
    # series for chart.js
    labels: list[str] = field(default_factory=list)
    win_rate_series: list[float | None] = field(default_factory=list)
    expectancy_series: list[float | None] = field(default_factory=list)
    profit_factor_series: list[float | None] = field(default_factory=list)
    cumulative_series: list[float] = field(default_factory=list)
    # trend analysis (last window vs first window)
    trend: str = TREND_INSUFFICIENT
    trend_label: str = ""
    last_win_rate: float | None = None
    last_expectancy: float | None = None
    last_profit_factor: float | None = None
    # overall stats for reference
    overall_win_rate: float | None = None
    overall_expectancy: float | None = None


def _calc_window_stats(pnl_window: list[float], outcome_window: list[str]) -> tuple[float, float, float | None]:
    """ウィンドウ内の勝率・期待値・プロフィットファクターを返す。"""
    n = len(pnl_window)
    if n == 0:
        return 0.0, 0.0, None

    wins = [p for p, o in zip(pnl_window, outcome_window) if o == "win"]
    losses = [p for p, o in zip(pnl_window, outcome_window) if o == "loss"]

    win_rate = len(wins) / n * 100

    expectancy = sum(pnl_window) / n

    gross_profit = sum(p for p in pnl_window if p > 0)
    gross_loss = abs(sum(p for p in pnl_window if p < 0))
    profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else None

    return round(win_rate, 1), round(expectancy, 2), profit_factor


def _determine_trend(points: list[RollingPoint], window: int) -> tuple[str, str]:
    """最初と最後のウィンドウの期待値を比較してトレンドを判定。"""
    filled = [p for p in points if p.expectancy is not None]
    if len(filled) < window * 2:
        return TREND_INSUFFICIENT, "データ不足（トレンド判定には 2 ウィンドウ分以上必要）"

    first_half = filled[:window]
    last_half = filled[-window:]

    first_exp = sum(p.expectancy for p in first_half) / len(first_half)  # type: ignore[arg-type]
    last_exp = sum(p.expectancy for p in last_half) / len(last_half)  # type: ignore[arg-type]

    delta = last_exp - first_exp
    if delta > 1.0:
        return TREND_IMPROVING, f"改善傾向（期待値 {first_exp:+.2f} → {last_exp:+.2f} pips）"
    elif delta < -1.0:
        return TREND_DECLINING, f"悪化傾向（期待値 {first_exp:+.2f} → {last_exp:+.2f} pips）"
    else:
        return TREND_STABLE, f"安定（期待値 {first_exp:+.2f} → {last_exp:+.2f} pips）"


def get_rolling_report(
    symbol: str | None = None,
    window: int = DEFAULT_WINDOW,
    db_path=None,
) -> RollingReport:
    """ローリングウィンドウ成績レポートを返す。"""
    if window not in VALID_WINDOWS:
        raise ValueError(f"無効なウィンドウサイズ: {window}。有効値: {sorted(VALID_WINDOWS)}")

    path = db_path or DB_PATH
    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy_approved', 'sell_approved')",
        "pnl_pips IS NOT NULL",
    ]
    params: list = []

    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    with get_db(path) as conn:
        rows = conn.execute(
            f"SELECT created_at, symbol, outcome, pnl_pips "
            f"FROM approval_history WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at ASC, id ASC",
            params,
        ).fetchall()

    report = RollingReport(window=window, symbol=symbol, total_trades=len(rows))

    if not rows:
        return report

    pnl_buf: list[float] = []
    out_buf: list[str] = []
    cumulative = 0.0

    for idx, row in enumerate(rows):
        pnl = float(row["pnl_pips"])
        outcome = row["outcome"]
        cumulative += pnl

        pnl_buf.append(pnl)
        out_buf.append(outcome)

        pt = RollingPoint(
            trade_index=idx + 1,
            created_at=str(row["created_at"])[:10],
            symbol=row["symbol"],
            pnl_pips=pnl,
            outcome=outcome,
            cumulative_pips=round(cumulative, 2),
        )

        if len(pnl_buf) >= window:
            wr, exp, pf = _calc_window_stats(pnl_buf[-window:], out_buf[-window:])
            pt.win_rate = wr
            pt.expectancy = exp
            pt.profit_factor = pf

        report.points.append(pt)

    # Build chart series
    for pt in report.points:
        label = f"#{pt.trade_index}"
        report.labels.append(label)
        report.win_rate_series.append(pt.win_rate)
        report.expectancy_series.append(pt.expectancy)
        report.profit_factor_series.append(pt.profit_factor)
        report.cumulative_series.append(pt.cumulative_pips)

    # Trend
    trend, trend_label = _determine_trend(report.points, window)
    report.trend = trend
    report.trend_label = trend_label

    # Last window stats
    if report.points:
        last = report.points[-1]
        report.last_win_rate = last.win_rate
        report.last_expectancy = last.expectancy
        report.last_profit_factor = last.profit_factor

    # Overall stats
    all_pnl = [float(r["pnl_pips"]) for r in rows]
    all_outcomes = [r["outcome"] for r in rows]
    n = len(rows)
    wins = sum(1 for o in all_outcomes if o == "win")
    report.overall_win_rate = round(wins / n * 100, 1) if n > 0 else None
    report.overall_expectancy = round(sum(all_pnl) / n, 2) if n > 0 else None

    return report
