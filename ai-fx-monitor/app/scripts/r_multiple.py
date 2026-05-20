"""Phase 50: R倍数・期待値分析

各トレードの損益を「リスク単位（R）」で正規化し、期待値・SQNを計算する。
1R の基準値には「過去の平均実損失 pips」を使用する。
注文は発生しない。集計・分析のみ。
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db


@dataclass
class RMultipleTrade:
    record_id: int
    symbol: str
    outcome: str      # "win" / "loss"
    pnl_pips: float
    r_value: float    # pnl_pips / avg_loss_pips（基準Rで正規化）
    created_at: str


@dataclass
class RMultipleReport:
    trades: int
    avg_loss_pips: float          # 1R 基準値（平均実損失 pips）
    mean_r: float | None          # 平均 R
    median_r: float | None        # 中央値 R
    std_r: float | None           # R 標準偏差
    min_r: float | None
    max_r: float | None
    expectancy: float | None      # 期待値 = mean_r（R 単位）
    sqn: float | None             # System Quality Number
    sqn_grade: str                # Poor / Average / Good / Excellent / Holy Grail
    positive_r_count: int
    negative_r_count: int
    series: list[RMultipleTrade] = field(default_factory=list)
    histogram_labels: list[str] = field(default_factory=list)
    histogram_counts: list[int] = field(default_factory=list)
    by_symbol: list[dict] = field(default_factory=list)


def _sqn_grade(sqn: float | None) -> str:
    if sqn is None:
        return "N/A"
    if sqn < 1.6:
        return "Poor"
    if sqn < 2.0:
        return "Average"
    if sqn < 3.0:
        return "Good"
    if sqn < 5.0:
        return "Excellent"
    return "Holy Grail"


def _build_histogram(
    r_values: list[float], bucket_size: float = 0.5
) -> tuple[list[str], list[int]]:
    if not r_values:
        return [], []

    lo = math.floor(min(r_values) / bucket_size) * bucket_size
    hi = math.ceil(max(r_values) / bucket_size) * bucket_size

    buckets: dict[float, int] = {}
    b = lo
    while b <= hi + 1e-9:
        buckets[round(b, 6)] = 0
        b = round(b + bucket_size, 6)

    for r in r_values:
        key = round(math.floor(r / bucket_size) * bucket_size, 6)
        buckets[key] = buckets.get(key, 0) + 1

    sorted_keys = sorted(buckets.keys())
    labels = [f"{k:+.1f}R" for k in sorted_keys]
    counts = [buckets[k] for k in sorted_keys]
    return labels, counts


def _symbol_summary(symbol: str, r_vals: list[float]) -> dict:
    n = len(r_vals)
    mean_r = round(statistics.mean(r_vals), 4)
    std_r = round(statistics.stdev(r_vals), 4) if n >= 2 else None
    sqn = round(math.sqrt(n) * mean_r / std_r, 2) if (std_r and std_r > 0) else None
    return {
        "symbol": symbol,
        "trades": n,
        "mean_r": mean_r,
        "sqn": sqn,
        "sqn_grade": _sqn_grade(sqn),
    }


def get_r_multiple_report(
    symbol: str | None = None,
    db_path=None,
) -> RMultipleReport:
    """R倍数・期待値・SQN レポートを返す。"""
    path = db_path or DB_PATH

    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy_approved', 'sell_approved')",
    ]
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    where = " AND ".join(clauses)
    with get_db(path) as conn:
        rows = conn.execute(
            f"""
            SELECT id, symbol, outcome, pnl_pips, created_at
            FROM approval_history
            WHERE {where}
            ORDER BY created_at ASC
            """,
            params,
        ).fetchall()

    n = len(rows)
    if n == 0:
        return RMultipleReport(
            trades=0, avg_loss_pips=0.0,
            mean_r=None, median_r=None, std_r=None,
            min_r=None, max_r=None,
            expectancy=None, sqn=None, sqn_grade="N/A",
            positive_r_count=0, negative_r_count=0,
        )

    loss_pips = [abs(float(r["pnl_pips"] or 0)) for r in rows if r["outcome"] == "loss"]
    avg_loss_pips = (sum(loss_pips) / len(loss_pips)) if loss_pips else 1.0
    if avg_loss_pips <= 0:
        avg_loss_pips = 1.0

    series: list[RMultipleTrade] = []
    for row in rows:
        pnl = float(row["pnl_pips"] or 0)
        series.append(RMultipleTrade(
            record_id=row["id"],
            symbol=row["symbol"],
            outcome=row["outcome"],
            pnl_pips=round(pnl, 2),
            r_value=round(pnl / avg_loss_pips, 4),
            created_at=row["created_at"],
        ))

    r_vals = [t.r_value for t in series]
    mean_r = round(statistics.mean(r_vals), 4)
    median_r = round(statistics.median(r_vals), 4)
    std_r = round(statistics.stdev(r_vals), 4) if n >= 2 else None
    sqn = round(math.sqrt(n) * mean_r / std_r, 2) if (std_r and std_r > 0) else None

    positive_r = sum(1 for r in r_vals if r > 0)
    negative_r = sum(1 for r in r_vals if r <= 0)

    labels, counts = _build_histogram(r_vals)

    groups: dict[str, list[float]] = {}
    for t in series:
        groups.setdefault(t.symbol, []).append(t.r_value)
    by_symbol = [_symbol_summary(sym, vs) for sym, vs in sorted(groups.items())]

    return RMultipleReport(
        trades=n,
        avg_loss_pips=round(avg_loss_pips, 2),
        mean_r=mean_r,
        median_r=median_r,
        std_r=std_r,
        min_r=round(min(r_vals), 4),
        max_r=round(max(r_vals), 4),
        expectancy=mean_r,
        sqn=sqn,
        sqn_grade=_sqn_grade(sqn),
        positive_r_count=positive_r,
        negative_r_count=negative_r,
        series=series,
        histogram_labels=labels,
        histogram_counts=counts,
        by_symbol=by_symbol,
    )
