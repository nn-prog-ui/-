"""Phase 45: ヒートマップカレンダー

approval_history テーブルの取引履歴から、
曜日（0=月〜6=日）× 時間帯（0〜23時）の勝率・損益マトリクスを生成する。

注文は一切発生しない。集計・可視化のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.config import DB_PATH
from app.database.db import get_db


WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]

METRIC_WIN_RATE = "win_rate"
METRIC_TOTAL_PIPS = "total_pips"
VALID_METRICS = {METRIC_WIN_RATE, METRIC_TOTAL_PIPS}


@dataclass
class HeatmapCell:
    weekday: int       # 0=月〜6=日
    hour: int          # 0〜23
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float | None = None      # 勝率 (0〜100)
    total_pips: float = 0.0
    avg_pips: float | None = None


@dataclass
class HeatmapResult:
    symbol: str | None              # None = 全通貨ペア
    metric: str                     # "win_rate" or "total_pips"
    cells: list[list[HeatmapCell]]  # [weekday 0..6][hour 0..23]
    total_trades: int = 0
    overall_win_rate: float | None = None
    assessment: str = ""


def _parse_created_at(text: str) -> datetime | None:
    """'YYYY-MM-DD HH:MM:SS' → datetime。パース失敗は None。"""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def get_heatmap_rows(
    symbol: str | None = None,
    is_simulation: bool | None = None,
    db_path=None,
) -> list[dict]:
    """approval_history から closed 取引行を返す。"""
    path = db_path or DB_PATH
    clauses: list[str] = ["outcome IS NOT NULL", "outcome != ''"]
    params: list = []

    if symbol is not None:
        clauses.append("symbol = ?")
        params.append(symbol)
    if is_simulation is True:
        clauses.append("is_dummy_data = 1")
    elif is_simulation is False:
        clauses.append("is_dummy_data = 0")

    where = " AND ".join(clauses)
    sql = f"SELECT created_at, outcome, pnl_pips FROM approval_history WHERE {where}"

    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(r) for r in rows]


def build_heatmap(
    rows: list[dict],
    metric: str = METRIC_WIN_RATE,
    symbol: str | None = None,
) -> HeatmapResult:
    """行リストから 7×24 のヒートマップを構築する。"""
    if metric not in VALID_METRICS:
        raise ValueError(f"未対応のmetric: {metric}。有効値: {sorted(VALID_METRICS)}")

    # 7×24 セルを初期化
    cells: list[list[HeatmapCell]] = [
        [HeatmapCell(weekday=wd, hour=h) for h in range(24)]
        for wd in range(7)
    ]

    total_trades = 0
    total_wins = 0

    for row in rows:
        created_at = row.get("created_at", "")
        if not created_at:
            continue
        dt = _parse_created_at(str(created_at))
        if dt is None:
            continue

        wd = dt.weekday()   # 0=月〜6=日
        hr = dt.hour

        outcome = row.get("outcome", "")
        pnl = row.get("pnl_pips")
        pnl_val = float(pnl) if pnl is not None else 0.0

        cell = cells[wd][hr]
        cell.trades += 1
        total_trades += 1

        if outcome == "win":
            cell.wins += 1
            total_wins += 1
        elif outcome == "loss":
            cell.losses += 1

        cell.total_pips += pnl_val

    # 勝率・平均損益を計算
    for wd in range(7):
        for hr in range(24):
            c = cells[wd][hr]
            if c.trades > 0:
                c.win_rate = c.wins / c.trades * 100
                c.avg_pips = c.total_pips / c.trades

    overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else None
    assessment = _assess(cells, metric, total_trades)

    return HeatmapResult(
        symbol=symbol,
        metric=metric,
        cells=cells,
        total_trades=total_trades,
        overall_win_rate=overall_win_rate,
        assessment=assessment,
    )


def _assess(
    cells: list[list[HeatmapCell]],
    metric: str,
    total_trades: int,
) -> str:
    """簡易評価テキストを生成する。"""
    if total_trades == 0:
        return "データがありません。バックテストや取引履歴を記録してください。"

    # 最良の(曜日, 時間帯)を検索
    best_cell: HeatmapCell | None = None
    worst_cell: HeatmapCell | None = None

    active_cells = [
        cells[wd][hr]
        for wd in range(7)
        for hr in range(24)
        if cells[wd][hr].trades > 0
    ]

    if not active_cells:
        return "有効なデータがありません。"

    if metric == METRIC_WIN_RATE:
        key = lambda c: (c.win_rate or 0.0)
    else:
        key = lambda c: c.total_pips

    best_cell = max(active_cells, key=key)
    worst_cell = min(active_cells, key=key)

    parts: list[str] = []
    parts.append(f"総取引数: {total_trades}件")

    wd_label = WEEKDAY_LABELS[best_cell.weekday]
    if metric == METRIC_WIN_RATE:
        parts.append(
            f"最高勝率: {wd_label}曜{best_cell.hour}時台 "
            f"({best_cell.win_rate:.1f}% / {best_cell.trades}件)"
        )
        wd_label_w = WEEKDAY_LABELS[worst_cell.weekday]
        parts.append(
            f"最低勝率: {wd_label_w}曜{worst_cell.hour}時台 "
            f"({worst_cell.win_rate:.1f}% / {worst_cell.trades}件)"
        )
    else:
        parts.append(
            f"最高損益: {wd_label}曜{best_cell.hour}時台 "
            f"({best_cell.total_pips:+.1f}pips / {best_cell.trades}件)"
        )
        wd_label_w = WEEKDAY_LABELS[worst_cell.weekday]
        parts.append(
            f"最低損益: {wd_label_w}曜{worst_cell.hour}時台 "
            f"({worst_cell.total_pips:+.1f}pips / {worst_cell.trades}件)"
        )

    return " / ".join(parts)
