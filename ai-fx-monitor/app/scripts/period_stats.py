"""Phase 52: 月次・週次パフォーマンスサマリー

approval_history のクローズ済みトレードを月・週単位で集計し、
損益トレンドと成績推移を可視化するデータを返す。
注文は発生しない。集計・分析のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.config import DB_PATH
from app.database.db import get_db


@dataclass
class PeriodStat:
    label: str              # "2026-01" (月) / "2026-W03" (週)
    trades: int
    wins: int
    losses: int
    win_rate: float | None  # 0〜100
    total_pips: float
    avg_pips: float | None


@dataclass
class PeriodReport:
    symbol: str | None
    monthly: list[PeriodStat]
    weekly: list[PeriodStat]
    # サマリー
    total_trades: int
    total_pips: float
    best_month: PeriodStat | None       # 合計pips最大月
    worst_month: PeriodStat | None      # 合計pips最小月
    max_consecutive_positive: int       # 連続プラス月数
    max_consecutive_negative: int       # 連続マイナス月数


def _parse_dt(text: str) -> datetime | None:
    if not text:
        return None
    s = str(text).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _isoweek_label(dt: datetime) -> str:
    """'YYYY-WNN' 形式の週ラベルを返す。"""
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _build_period_stats(rows: list, period_fn) -> list[PeriodStat]:
    """rows を period_fn で分類してラベル別に集計する。"""
    buckets: dict[str, dict] = {}

    for row in rows:
        dt = _parse_dt(str(row["created_at"] or ""))
        if dt is None:
            continue
        outcome = row["outcome"]
        if outcome not in ("win", "loss"):
            continue
        pnl = float(row["pnl_pips"] or 0)
        label = period_fn(dt)
        b = buckets.setdefault(label, {"trades": 0, "wins": 0, "losses": 0, "total_pips": 0.0})
        b["trades"] += 1
        b["total_pips"] += pnl
        if outcome == "win":
            b["wins"] += 1
        else:
            b["losses"] += 1

    result: list[PeriodStat] = []
    for label in sorted(buckets.keys()):
        b = buckets[label]
        n = b["trades"]
        win_rate = round(b["wins"] / n * 100, 1) if n > 0 else None
        avg_pips = round(b["total_pips"] / n, 2) if n > 0 else None
        result.append(PeriodStat(
            label=label,
            trades=n,
            wins=b["wins"],
            losses=b["losses"],
            win_rate=win_rate,
            total_pips=round(b["total_pips"], 2),
            avg_pips=avg_pips,
        ))
    return result


def _max_consecutive(stats: list[PeriodStat], positive: bool) -> int:
    """連続プラス（または連続マイナス）月数の最大値を返す。"""
    max_run = 0
    cur = 0
    for s in stats:
        if (s.total_pips > 0) == positive:
            cur += 1
            max_run = max(max_run, cur)
        else:
            cur = 0
    return max_run


def get_period_report(
    symbol: str | None = None,
    db_path=None,
) -> PeriodReport:
    """月次・週次パフォーマンスレポートを返す。"""
    path = db_path or DB_PATH

    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy_approved', 'sell_approved')",
    ]
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    with get_db(path) as conn:
        rows = conn.execute(
            f"""
            SELECT created_at, outcome, pnl_pips
            FROM approval_history
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at ASC
            """,
            params,
        ).fetchall()

    if not rows:
        return PeriodReport(
            symbol=symbol,
            monthly=[], weekly=[],
            total_trades=0, total_pips=0.0,
            best_month=None, worst_month=None,
            max_consecutive_positive=0, max_consecutive_negative=0,
        )

    monthly = _build_period_stats(rows, lambda dt: dt.strftime("%Y-%m"))
    weekly = _build_period_stats(rows, _isoweek_label)

    total_trades = sum(s.trades for s in monthly)
    total_pips = round(sum(s.total_pips for s in monthly), 2)

    best_month = max(monthly, key=lambda s: s.total_pips) if monthly else None
    worst_month = min(monthly, key=lambda s: s.total_pips) if monthly else None

    return PeriodReport(
        symbol=symbol,
        monthly=monthly,
        weekly=weekly,
        total_trades=total_trades,
        total_pips=total_pips,
        best_month=best_month,
        worst_month=worst_month,
        max_consecutive_positive=_max_consecutive(monthly, positive=True),
        max_consecutive_negative=_max_consecutive(monthly, positive=False),
    )
