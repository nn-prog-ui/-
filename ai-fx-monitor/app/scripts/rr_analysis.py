"""Phase 57: R:R実績分析（Planned vs Actual Risk-Reward Analysis）

計画した損切り・利確（entry/stop_loss/take_profit）と実際の結果を比較し、
TP命中率・SL命中率・計画 R:R vs 実際 R:R を分析する。
注文は一切発生しない。集計・可視化のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db

EXIT_HIT_TP = "hit_tp"
EXIT_HIT_SL = "hit_sl"
EXIT_EARLY  = "early_exit"
EXIT_UNKNOWN = "unknown"

# 実際の exit_price がTP/SLの何 pip 以内なら「命中」とみなすか
HIT_TOLERANCE_PIPS = 5.0


@dataclass
class RRTrade:
    approval_id: int
    created_at: str
    symbol: str
    signal: str                   # "BUY" / "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    pnl_pips: float
    outcome: str                  # "win" / "loss"
    planned_rr: float             # (TP - entry) / (entry - SL)
    planned_risk_pips: float      # |entry - SL| in pips
    planned_reward_pips: float    # |TP - entry| in pips
    actual_r: float               # pnl_pips / planned_risk_pips (R倍数)
    exit_type: str                # "hit_tp" / "hit_sl" / "early_exit" / "unknown"


@dataclass
class RRReport:
    symbol: str | None
    total_trades: int             # trades with full R:R data
    # exit type counts
    tp_count: int = 0
    sl_count: int = 0
    early_count: int = 0
    unknown_count: int = 0
    # planned R:R stats
    avg_planned_rr: float | None = None
    avg_actual_r: float | None = None
    # assessment
    assessment: str = ""
    # chart series — distribution of actual R multiples
    hist_labels: list[str] = field(default_factory=list)   # e.g. "-3", "-2", …, "3"
    hist_counts: list[int] = field(default_factory=list)
    # per-outcome breakdown
    avg_planned_rr_wins: float | None = None
    avg_planned_rr_losses: float | None = None
    # trades list (for display)
    trades: list[RRTrade] = field(default_factory=list)


def _pip_size(symbol: str) -> float:
    """通貨ペアの pip サイズ（JPY ペアは 0.01、それ以外は 0.0001）。"""
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def _infer_exit_type(trade: RRTrade) -> str:
    """exit_price から TP/SL 命中を推定する。"""
    pip = _pip_size(trade.symbol)
    tol = HIT_TOLERANCE_PIPS * pip

    if trade.signal == "BUY":
        tp_dist = abs(trade.exit_price - trade.take_profit)
        sl_dist = abs(trade.exit_price - trade.stop_loss)
    else:  # SELL
        tp_dist = abs(trade.exit_price - trade.take_profit)
        sl_dist = abs(trade.exit_price - trade.stop_loss)

    if tp_dist <= tol:
        return EXIT_HIT_TP
    if sl_dist <= tol:
        return EXIT_HIT_SL
    return EXIT_EARLY


def _build_histogram(trades: list[RRTrade]) -> tuple[list[str], list[int]]:
    """実際の R 倍数のヒストグラム（-4R 〜 +5R、0.5 刻み）を返す。"""
    # bins: [-4, -3.5, -3, ..., 4.5, 5]
    bin_edges = [i / 2 for i in range(-8, 11)]   # -4.0 to 5.0 step 0.5
    counts = [0] * (len(bin_edges) - 1)
    labels: list[str] = []
    for i in range(len(bin_edges) - 1):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        labels.append(f"{lo:+.1f}")
        for t in trades:
            if lo <= t.actual_r < hi:
                counts[i] += 1
    return labels, counts


def _assess(report: RRReport) -> str:
    if report.total_trades == 0:
        return "データがありません。"

    parts: list[str] = []
    n = report.total_trades
    tp_pct = report.tp_count / n * 100
    sl_pct = report.sl_count / n * 100

    parts.append(f"TP命中率 {tp_pct:.1f}% / SL命中率 {sl_pct:.1f}%")

    if report.avg_planned_rr is not None:
        parts.append(f"平均計画R:R {report.avg_planned_rr:.2f}")

    if report.avg_actual_r is not None:
        ar = report.avg_actual_r
        if ar >= 1.0:
            parts.append(f"平均実績R {ar:+.2f}（良好）")
        elif ar >= 0:
            parts.append(f"平均実績R {ar:+.2f}（プラス圏）")
        else:
            parts.append(f"平均実績R {ar:+.2f}（マイナス圏）")

    return " / ".join(parts)


def get_rr_report(
    symbol: str | None = None,
    db_path=None,
) -> RRReport:
    """R:R実績分析レポートを返す。注文は発生しない。"""
    path = db_path or DB_PATH
    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy_approved', 'sell_approved')",
        "pnl_pips IS NOT NULL",
        "entry_price IS NOT NULL",
        "stop_loss IS NOT NULL",
        "take_profit IS NOT NULL",
        "exit_price IS NOT NULL",
    ]
    params: list = []

    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    with get_db(path) as conn:
        rows = conn.execute(
            f"SELECT id, created_at, symbol, signal, entry_price, stop_loss, "
            f"take_profit, exit_price, pnl_pips, outcome "
            f"FROM approval_history WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at DESC",
            params,
        ).fetchall()

    report = RRReport(symbol=symbol, total_trades=0, assessment=_assess(RRReport(symbol=symbol, total_trades=0)))
    trades: list[RRTrade] = []

    for row in rows:
        entry  = float(row["entry_price"])
        sl     = float(row["stop_loss"])
        tp     = float(row["take_profit"])
        ex     = float(row["exit_price"])
        pnl    = float(row["pnl_pips"])
        sig    = str(row["signal"]).upper()
        sym    = str(row["symbol"])
        pip    = _pip_size(sym)

        risk_pips   = abs(entry - sl) / pip
        reward_pips = abs(tp - entry) / pip

        if risk_pips < 0.01:
            continue   # invalid SL

        planned_rr   = round(reward_pips / risk_pips, 3)
        actual_r     = round(pnl / risk_pips, 3)

        t = RRTrade(
            approval_id=row["id"],
            created_at=str(row["created_at"])[:10],
            symbol=sym,
            signal=sig,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            exit_price=ex,
            pnl_pips=pnl,
            outcome=row["outcome"],
            planned_rr=planned_rr,
            planned_risk_pips=round(risk_pips, 1),
            planned_reward_pips=round(reward_pips, 1),
            actual_r=actual_r,
            exit_type=EXIT_UNKNOWN,
        )
        t.exit_type = _infer_exit_type(t)
        trades.append(t)

    report.total_trades = len(trades)
    if not trades:
        return report

    # Exit type counts
    report.tp_count      = sum(1 for t in trades if t.exit_type == EXIT_HIT_TP)
    report.sl_count      = sum(1 for t in trades if t.exit_type == EXIT_HIT_SL)
    report.early_count   = sum(1 for t in trades if t.exit_type == EXIT_EARLY)
    report.unknown_count = sum(1 for t in trades if t.exit_type == EXIT_UNKNOWN)

    # Averages
    report.avg_planned_rr = round(
        sum(t.planned_rr for t in trades) / len(trades), 3)
    report.avg_actual_r = round(
        sum(t.actual_r for t in trades) / len(trades), 3)

    wins   = [t for t in trades if t.outcome == "win"]
    losses = [t for t in trades if t.outcome == "loss"]
    if wins:
        report.avg_planned_rr_wins = round(
            sum(t.planned_rr for t in wins) / len(wins), 3)
    if losses:
        report.avg_planned_rr_losses = round(
            sum(t.planned_rr for t in losses) / len(losses), 3)

    # Histogram
    report.hist_labels, report.hist_counts = _build_histogram(trades)

    # Assessment
    report.assessment = _assess(report)

    # Trade list (最新50件)
    report.trades = trades[:50]

    return report
