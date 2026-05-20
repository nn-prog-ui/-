"""Phase 49: マルチシンボル比較分析

複数通貨ペアのパフォーマンスを横断的に比較する。
注文は発生しない。集計・分析のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db


@dataclass
class SymbolStats:
    symbol: str
    trades: int              # クローズ済みトレード数
    win_count: int
    loss_count: int
    open_count: int          # オープン中
    win_rate: float | None   # 勝率 (0〜100)
    total_pips: float        # 合計損益
    avg_pips: float | None   # 平均損益
    avg_score: float | None  # 平均シグナルスコア
    avg_rsi: float | None    # 平均RSI
    profit_factor: float | None  # Σ勝ち / Σ|負け|
    max_win_pips: float | None   # 最大勝ちpips
    max_loss_pips: float | None  # 最大負けpips
    buy_count: int           # BUY承認数
    sell_count: int          # SELL承認数
    rank: int = 0            # ソート後の順位


@dataclass
class MultiSymbolReport:
    symbols: list[SymbolStats] = field(default_factory=list)
    sort_by: str = "total_pips"
    # 全通貨ペア合算サマリー
    total_trades: int = 0
    total_pips: float = 0.0
    overall_win_rate: float | None = None


_VALID_SORT_KEYS = {
    "total_pips", "win_rate", "avg_pips", "trades",
    "profit_factor", "avg_score",
}


def _compute_symbol_stats(rows: list, symbol: str) -> SymbolStats:
    """DB行リストから1通貨ペアの統計を計算する。"""
    closed = [r for r in rows if r["outcome"] in ("win", "loss")]
    wins = [r for r in closed if r["outcome"] == "win"]
    losses = [r for r in closed if r["outcome"] == "loss"]
    opens = [r for r in rows if r["outcome"] is None]

    win_pips = sum(float(r["pnl_pips"] or 0) for r in wins)
    loss_pips = sum(abs(float(r["pnl_pips"] or 0)) for r in losses)
    total_pips = sum(float(r["pnl_pips"] or 0) for r in closed)

    win_rate = (len(wins) / len(closed) * 100) if closed else None
    avg_pips = (total_pips / len(closed)) if closed else None
    profit_factor = (win_pips / loss_pips) if loss_pips > 0 else None

    scores = [r["score"] for r in rows if r["score"] is not None]
    avg_score = (sum(scores) / len(scores)) if scores else None

    rsis = [r["rsi"] for r in rows if r["rsi"] is not None]
    avg_rsi = (sum(rsis) / len(rsis)) if rsis else None

    max_win = max((float(r["pnl_pips"] or 0) for r in wins), default=None)
    max_loss = min((float(r["pnl_pips"] or 0) for r in losses), default=None)

    buy_count = sum(1 for r in rows if r["human_action"] == "buy_approved")
    sell_count = sum(1 for r in rows if r["human_action"] == "sell_approved")

    return SymbolStats(
        symbol=symbol,
        trades=len(closed),
        win_count=len(wins),
        loss_count=len(losses),
        open_count=len(opens),
        win_rate=round(win_rate, 1) if win_rate is not None else None,
        total_pips=round(total_pips, 2),
        avg_pips=round(avg_pips, 2) if avg_pips is not None else None,
        avg_score=round(avg_score, 2) if avg_score is not None else None,
        avg_rsi=round(avg_rsi, 1) if avg_rsi is not None else None,
        profit_factor=round(profit_factor, 2) if profit_factor is not None else None,
        max_win_pips=round(max_win, 2) if max_win is not None else None,
        max_loss_pips=round(max_loss, 2) if max_loss is not None else None,
        buy_count=buy_count,
        sell_count=sell_count,
    )


def get_multi_symbol_report(
    sort_by: str = "total_pips",
    db_path=None,
) -> MultiSymbolReport:
    """全通貨ペアのパフォーマンス比較レポートを返す。"""
    if sort_by not in _VALID_SORT_KEYS:
        sort_by = "total_pips"

    path = db_path or DB_PATH
    with get_db(path) as conn:
        rows = conn.execute(
            """
            SELECT symbol, human_action, outcome, pnl_pips, score, rsi
            FROM approval_history
            WHERE human_action IN ('buy_approved', 'sell_approved')
            ORDER BY created_at ASC
            """
        ).fetchall()

    # シンボル別にグループ化
    groups: dict[str, list] = {}
    for row in rows:
        sym = row["symbol"]
        groups.setdefault(sym, []).append(row)

    stats_list: list[SymbolStats] = []
    for sym, sym_rows in sorted(groups.items()):
        stats_list.append(_compute_symbol_stats(sym_rows, sym))

    # ソート
    def _sort_key(s: SymbolStats) -> float:
        if sort_by == "win_rate":
            return s.win_rate if s.win_rate is not None else -1.0
        if sort_by == "avg_pips":
            return s.avg_pips if s.avg_pips is not None else -9999.0
        if sort_by == "trades":
            return float(s.trades)
        if sort_by == "profit_factor":
            return s.profit_factor if s.profit_factor is not None else 0.0
        if sort_by == "avg_score":
            return s.avg_score if s.avg_score is not None else 0.0
        return s.total_pips  # default: total_pips

    stats_list.sort(key=_sort_key, reverse=True)
    for i, s in enumerate(stats_list, start=1):
        s.rank = i

    # 全体サマリー
    all_closed = [r for r in rows if r["outcome"] in ("win", "loss")]
    all_wins = [r for r in all_closed if r["outcome"] == "win"]
    total_pips = sum(float(r["pnl_pips"] or 0) for r in all_closed)
    overall_win_rate = (
        round(len(all_wins) / len(all_closed) * 100, 1) if all_closed else None
    )

    return MultiSymbolReport(
        symbols=stats_list,
        sort_by=sort_by,
        total_trades=len(all_closed),
        total_pips=round(total_pips, 2),
        overall_win_rate=overall_win_rate,
    )
