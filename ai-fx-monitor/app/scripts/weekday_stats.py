"""Phase 60: 曜日別成績分析（Day-of-Week Performance Analysis）

取引履歴を曜日（月〜日）に分類し、勝率・期待値・件数を集計する。
注文は一切発生しない。集計・可視化のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.config import DB_PATH
from app.database.db import get_db

# 0=Monday … 6=Sunday (Python weekday())
WEEKDAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]
WEEKDAY_FULL  = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]

WEEKDAY_MIN_TRADES = 3   # minimum trades to qualify for best/worst


@dataclass
class WeekdayBucket:
    weekday: int           # 0=Mon … 6=Sun
    name: str              # "月"…"日"
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pips: float = 0.0
    win_rate: float | None = None
    expectancy: float | None = None
    profit_factor: float | None = None


@dataclass
class WeekdayReport:
    symbol: str | None
    total_trades: int
    buckets: list[WeekdayBucket] = field(default_factory=list)   # Mon..Sun order
    weekday_labels: list[str] = field(default_factory=list)
    win_rate_series: list[float | None] = field(default_factory=list)
    expectancy_series: list[float | None] = field(default_factory=list)
    trade_count_series: list[int] = field(default_factory=list)
    profit_factor_series: list[float | None] = field(default_factory=list)
    best_weekday: str | None = None
    worst_weekday: str | None = None


def _parse_dt(text: str) -> datetime | None:
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:n], fmt)
        except ValueError:
            continue
    return None


def get_weekday_report(
    symbol: str | None = None,
    db_path=None,
) -> WeekdayReport:
    """曜日別成績レポートを返す。注文は発生しない。"""
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
            f"SELECT created_at, outcome, pnl_pips "
            f"FROM approval_history WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at ASC",
            params,
        ).fetchall()

    # Initialize buckets Mon-Sun
    buckets: list[WeekdayBucket] = [
        WeekdayBucket(weekday=i, name=WEEKDAY_NAMES[i]) for i in range(7)
    ]

    report = WeekdayReport(symbol=symbol, total_trades=len(rows))

    if not rows:
        report.buckets = buckets
        report.weekday_labels = WEEKDAY_NAMES[:]
        report.win_rate_series = [None] * 7
        report.expectancy_series = [None] * 7
        report.trade_count_series = [0] * 7
        report.profit_factor_series = [None] * 7
        return report

    # Accumulate per weekday
    for row in rows:
        dt = _parse_dt(str(row["created_at"]))
        if dt is None:
            continue
        wd = dt.weekday()   # 0=Mon … 6=Sun
        pnl = float(row["pnl_pips"])
        b = buckets[wd]
        b.trades += 1
        b.total_pips += pnl
        if row["outcome"] == "win":
            b.wins += 1
        else:
            b.losses += 1

    # Profit/loss accumulators per weekday for PF
    wd_profits: list[float] = [0.0] * 7
    wd_losses_abs: list[float] = [0.0] * 7
    for row in rows:
        dt = _parse_dt(str(row["created_at"]))
        if dt is None:
            continue
        wd = dt.weekday()
        pnl = float(row["pnl_pips"])
        if pnl > 0:
            wd_profits[wd] += pnl
        elif pnl < 0:
            wd_losses_abs[wd] += abs(pnl)

    # Compute stats
    for b in buckets:
        if b.trades > 0:
            b.win_rate = round(b.wins / b.trades * 100, 1)
            b.expectancy = round(b.total_pips / b.trades, 2)
            gl = wd_losses_abs[b.weekday]
            gp = wd_profits[b.weekday]
            b.profit_factor = round(gp / gl, 3) if gl > 0 else None

    report.buckets = buckets
    report.weekday_labels = WEEKDAY_NAMES[:]
    report.win_rate_series = [b.win_rate for b in buckets]
    report.expectancy_series = [b.expectancy for b in buckets]
    report.trade_count_series = [b.trades for b in buckets]
    report.profit_factor_series = [b.profit_factor for b in buckets]

    # Best / worst by expectancy (min WEEKDAY_MIN_TRADES trades)
    active = [b for b in buckets if b.trades >= WEEKDAY_MIN_TRADES and b.expectancy is not None]
    if active:
        report.best_weekday = max(active, key=lambda b: b.expectancy or 0.0).name
        report.worst_weekday = min(active, key=lambda b: b.expectancy or 0.0).name

    return report
