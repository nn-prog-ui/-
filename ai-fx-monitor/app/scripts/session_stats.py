"""Phase 58: FXセッション別分析（Session Performance Analysis）

取引履歴を JST 時間帯で東京・ロンドン・NY 重複・NY 各セッションに分類し、
勝率・期待値・件数を集計する。注文は一切発生しない。集計・可視化のみ。

JST 基準のセッション定義:
  東京       09:00 〜 16:59
  ロンドン   17:00 〜 20:59
  重複       21:00 〜 23:59 / 00:00 〜 00:59  (London + NY overlap)
  NY/深夜    01:00 〜 08:59
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.config import DB_PATH
from app.database.db import get_db

SESSION_TOKYO    = "東京"
SESSION_LONDON   = "ロンドン"
SESSION_OVERLAP  = "重複(LN+NY)"
SESSION_NY       = "NY/深夜"

# 表示順
SESSION_ORDER = [SESSION_TOKYO, SESSION_LONDON, SESSION_OVERLAP, SESSION_NY]

# (hour_start_inclusive, hour_end_inclusive) in JST
_SESSION_HOURS: dict[str, tuple[int, ...]] = {
    SESSION_TOKYO:   tuple(range(9,  17)),    # 9〜16
    SESSION_LONDON:  tuple(range(17, 21)),    # 17〜20
    SESSION_OVERLAP: (*range(21, 24), 0),     # 21〜23, 0
    SESSION_NY:      tuple(range(1,  9)),     # 1〜8
}


def _classify_hour(hour: int) -> str:
    """JST の時（0〜23）をセッション名に変換する。"""
    for session, hours in _SESSION_HOURS.items():
        if hour in hours:
            return session
    return SESSION_NY   # fallback


@dataclass
class SessionBucket:
    session: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pips: float = 0.0
    win_rate: float | None = None
    expectancy: float | None = None
    profit_factor: float | None = None
    best_hour: int | None = None         # most active hour in this session


@dataclass
class SessionReport:
    symbol: str | None
    total_trades: int
    buckets: list[SessionBucket] = field(default_factory=list)
    # chart series (in SESSION_ORDER)
    session_labels: list[str] = field(default_factory=list)
    win_rate_series: list[float | None] = field(default_factory=list)
    expectancy_series: list[float | None] = field(default_factory=list)
    trade_count_series: list[int] = field(default_factory=list)
    # best session by expectancy
    best_session: str | None = None
    worst_session: str | None = None
    # hourly breakdown for heatmap-like mini-chart (0..23 → trade count)
    hourly_counts: list[int] = field(default_factory=list)
    hourly_win_rates: list[float | None] = field(default_factory=list)


def _parse_dt(text: str) -> datetime | None:
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:n], fmt)
        except ValueError:
            continue
    return None


def get_session_report(
    symbol: str | None = None,
    db_path=None,
) -> SessionReport:
    """セッション別成績レポートを返す。注文は発生しない。"""
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

    report = SessionReport(symbol=symbol, total_trades=len(rows))

    if not rows:
        report.session_labels = SESSION_ORDER[:]
        report.win_rate_series = [None] * len(SESSION_ORDER)
        report.expectancy_series = [None] * len(SESSION_ORDER)
        report.trade_count_series = [0] * len(SESSION_ORDER)
        report.hourly_counts = [0] * 24
        report.hourly_win_rates = [None] * 24
        report.buckets = [SessionBucket(session=s) for s in SESSION_ORDER]
        return report

    # Initialize buckets
    buckets: dict[str, SessionBucket] = {s: SessionBucket(session=s) for s in SESSION_ORDER}

    # Hourly accumulators
    hourly_trades: list[int] = [0] * 24
    hourly_wins: list[int] = [0] * 24
    hourly_pnl: list[float] = [0.0] * 24

    for row in rows:
        dt = _parse_dt(str(row["created_at"]))
        if dt is None:
            continue

        hour = dt.hour
        session = _classify_hour(hour)
        pnl = float(row["pnl_pips"])
        outcome = row["outcome"]

        b = buckets[session]
        b.trades += 1
        b.total_pips += pnl
        if outcome == "win":
            b.wins += 1
        else:
            b.losses += 1

        hourly_trades[hour] += 1
        hourly_pnl[hour] += pnl
        if outcome == "win":
            hourly_wins[hour] += 1

    # Compute per-session stats
    for b in buckets.values():
        if b.trades > 0:
            b.win_rate = round(b.wins / b.trades * 100, 1)
            b.expectancy = round(b.total_pips / b.trades, 2)
            gross_profit = sum(
                float(row["pnl_pips"])
                for row in rows
                if float(row["pnl_pips"]) > 0
                and _classify_hour(
                    (_parse_dt(str(row["created_at"])) or datetime(2000, 1, 1)).hour
                ) == b.session
            )
            gross_loss = abs(sum(
                float(row["pnl_pips"])
                for row in rows
                if float(row["pnl_pips"]) < 0
                and _classify_hour(
                    (_parse_dt(str(row["created_at"])) or datetime(2000, 1, 1)).hour
                ) == b.session
            ))
            b.profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else None

    # Build chart series in SESSION_ORDER
    report.buckets = [buckets[s] for s in SESSION_ORDER]
    report.session_labels = SESSION_ORDER[:]
    report.win_rate_series = [buckets[s].win_rate for s in SESSION_ORDER]
    report.expectancy_series = [buckets[s].expectancy for s in SESSION_ORDER]
    report.trade_count_series = [buckets[s].trades for s in SESSION_ORDER]

    # Hourly breakdown
    report.hourly_counts = hourly_trades
    report.hourly_win_rates = [
        round(hourly_wins[h] / hourly_trades[h] * 100, 1) if hourly_trades[h] > 0 else None
        for h in range(24)
    ]

    # Best / worst by expectancy (min 3 trades)
    active = [b for b in report.buckets if b.trades >= 3 and b.expectancy is not None]
    if active:
        report.best_session = max(active, key=lambda b: b.expectancy or 0.0).session
        report.worst_session = min(active, key=lambda b: b.expectancy or 0.0).session

    return report
