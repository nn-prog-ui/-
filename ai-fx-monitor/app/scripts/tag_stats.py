"""Phase 59: ジャーナルタグ別成績分析（Tag Performance Analysis）

trade_journal の tags カラム（カンマ区切り）と approval_history の P&L を結合し、
タグごとの勝率・期待値・件数を集計する。注文は一切発生しない。集計・可視化のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db

TAG_MIN_TRADES = 2  # minimum trades to show a tag in chart


@dataclass
class TagBucket:
    tag: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pips: float = 0.0
    win_rate: float | None = None
    expectancy: float | None = None
    profit_factor: float | None = None


@dataclass
class TagReport:
    symbol: str | None
    total_trades: int
    total_tags: int
    buckets: list[TagBucket] = field(default_factory=list)
    # chart series (sorted by expectancy desc, min TAG_MIN_TRADES trades)
    tag_labels: list[str] = field(default_factory=list)
    win_rate_series: list[float | None] = field(default_factory=list)
    expectancy_series: list[float | None] = field(default_factory=list)
    trade_count_series: list[int] = field(default_factory=list)
    profit_factor_series: list[float | None] = field(default_factory=list)
    best_tag: str | None = None
    worst_tag: str | None = None


def _parse_tags(tags_text: str | None) -> list[str]:
    """カンマ区切りのタグ文字列をリストに変換する。空・None は空リストを返す。"""
    if not tags_text:
        return []
    return [t.strip() for t in tags_text.split(",") if t.strip()]


def get_tag_report(
    symbol: str | None = None,
    db_path=None,
) -> TagReport:
    """タグ別成績レポートを返す。注文は発生しない。"""
    path = db_path or DB_PATH

    sym_clause = ""
    params: list = []
    if symbol:
        sym_clause = "AND ah.symbol = ?"
        params.append(symbol)

    with get_db(path) as conn:
        rows = conn.execute(
            f"""
            SELECT tj.tags, ah.outcome, ah.pnl_pips
            FROM trade_journal tj
            JOIN approval_history ah ON tj.approval_id = ah.id
            WHERE ah.outcome IN ('win', 'loss')
              AND ah.human_action IN ('buy_approved', 'sell_approved')
              AND ah.pnl_pips IS NOT NULL
              AND tj.tags IS NOT NULL
              AND tj.tags != ''
              {sym_clause}
            """,
            params,
        ).fetchall()

    buckets: dict[str, TagBucket] = {}

    for row in rows:
        tags = _parse_tags(row["tags"])
        for tag in tags:
            if tag not in buckets:
                buckets[tag] = TagBucket(tag=tag)
            b = buckets[tag]
            b.trades += 1
            b.total_pips += float(row["pnl_pips"])
            if row["outcome"] == "win":
                b.wins += 1
            else:
                b.losses += 1

    # Compute stats per tag
    for b in buckets.values():
        if b.trades > 0:
            b.win_rate = round(b.wins / b.trades * 100, 1)
            b.expectancy = round(b.total_pips / b.trades, 2)
            gross_profit = sum(
                b.total_pips  # placeholder — computed below per-trade
                for _ in []   # empty loop; real calc follows
            )
            # Recompute gross/loss directly from already-aggregated data
            # Since we don't store per-trade values per tag, approximate using wins/losses average
            # We need to re-scan rows for accurate profit_factor
            pass

    # Recompute profit_factor with full row scan per tag
    tag_profits: dict[str, float] = {t: 0.0 for t in buckets}
    tag_losses_abs: dict[str, float] = {t: 0.0 for t in buckets}
    for row in rows:
        tags = _parse_tags(row["tags"])
        pnl = float(row["pnl_pips"])
        for tag in tags:
            if tag in buckets:
                if pnl > 0:
                    tag_profits[tag] += pnl
                elif pnl < 0:
                    tag_losses_abs[tag] += abs(pnl)

    for tag, b in buckets.items():
        gp = tag_profits[tag]
        gl = tag_losses_abs[tag]
        b.profit_factor = round(gp / gl, 3) if gl > 0 else None

    # Sort by expectancy desc for display
    all_buckets = sorted(
        buckets.values(),
        key=lambda b: (b.expectancy or float("-inf")),
        reverse=True,
    )

    report = TagReport(
        symbol=symbol,
        total_trades=len(rows),
        total_tags=len(buckets),
        buckets=all_buckets,
    )

    # Chart series: only tags with >= TAG_MIN_TRADES trades
    chart_buckets = [b for b in all_buckets if b.trades >= TAG_MIN_TRADES]
    report.tag_labels = [b.tag for b in chart_buckets]
    report.win_rate_series = [b.win_rate for b in chart_buckets]
    report.expectancy_series = [b.expectancy for b in chart_buckets]
    report.trade_count_series = [b.trades for b in chart_buckets]
    report.profit_factor_series = [b.profit_factor for b in chart_buckets]

    # Best / worst by expectancy (min TAG_MIN_TRADES trades)
    active = [b for b in chart_buckets if b.expectancy is not None]
    if active:
        report.best_tag = max(active, key=lambda b: b.expectancy or 0.0).tag
        report.worst_tag = min(active, key=lambda b: b.expectancy or 0.0).tag

    return report
