"""Phase 48: 連勝/連敗ストリーク分析

過去の取引履歴から連勝・連敗の最大値・現在値・平均値を計算する。
注文は発生しない。集計・分析のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db


@dataclass
class StreakEvent:
    type: str      # "win" or "loss"
    length: int    # 連続回数
    start_at: str  # 開始日時
    end_at: str    # 終了日時


@dataclass
class StreakStats:
    symbol: str | None
    trades: int                      # 対象クローズ済みトレード数
    max_win_streak: int              # 最大連勝数
    max_loss_streak: int             # 最大連敗数
    current_streak_type: str         # "win" / "loss" / "none"
    current_streak_length: int       # 現在のストリーク長
    avg_win_streak: float            # 連勝ストリークの平均長
    avg_loss_streak: float           # 連敗ストリークの平均長
    total_win_streaks: int           # 連勝ストリーク発生回数（1以上のもの）
    total_loss_streaks: int          # 連敗ストリーク発生回数（1以上のもの）
    longest_win_streak_start: str    # 最大連勝の開始日
    longest_loss_streak_start: str   # 最大連敗の開始日
    streaks: list[StreakEvent] = field(default_factory=list)


def _compute_streaks(rows: list) -> tuple[list[StreakEvent], list[dict]]:
    """DB行リストからストリークイベントを生成する。

    Returns:
        (streak_events, raw_outcomes)
        raw_outcomes: [{"outcome": "win"/"loss", "created_at": str}]
    """
    if not rows:
        return [], []

    events: list[StreakEvent] = []
    current_type = rows[0]["outcome"]
    current_len = 1
    current_start = rows[0]["created_at"]

    for row in rows[1:]:
        outcome = row["outcome"]
        if outcome == current_type:
            current_len += 1
        else:
            events.append(StreakEvent(
                type=current_type,
                length=current_len,
                start_at=current_start,
                end_at=rows[rows.index(row) - 1]["created_at"] if False else current_start,
            ))
            current_type = outcome
            current_len = 1
            current_start = row["created_at"]

    events.append(StreakEvent(
        type=current_type,
        length=current_len,
        start_at=current_start,
        end_at=rows[-1]["created_at"],
    ))

    return events, [{"outcome": r["outcome"], "created_at": r["created_at"]} for r in rows]


def _compute_streaks_v2(rows: list) -> list[StreakEvent]:
    """DB行リストからストリークイベントを生成する（改良版）。"""
    if not rows:
        return []

    events: list[StreakEvent] = []
    current_type = rows[0]["outcome"]
    current_len = 1
    current_start = rows[0]["created_at"]
    prev_end = rows[0]["created_at"]

    for row in rows[1:]:
        outcome = row["outcome"]
        if outcome == current_type:
            current_len += 1
            prev_end = row["created_at"]
        else:
            events.append(StreakEvent(
                type=current_type,
                length=current_len,
                start_at=current_start,
                end_at=prev_end,
            ))
            current_type = outcome
            current_len = 1
            current_start = row["created_at"]
            prev_end = row["created_at"]

    events.append(StreakEvent(
        type=current_type,
        length=current_len,
        start_at=current_start,
        end_at=prev_end,
    ))

    return events


def get_streak_stats(
    symbol: str | None = None,
    db_path=None,
) -> StreakStats:
    """指定通貨ペア（None = 全ペア）の連勝/連敗統計を返す。"""
    path = db_path or DB_PATH
    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy', 'sell')",
    ]
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    where = " AND ".join(clauses)
    sql = f"""
        SELECT created_at, outcome
        FROM approval_history
        WHERE {where}
        ORDER BY created_at ASC
    """

    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()

    n = len(rows)
    if n == 0:
        return StreakStats(
            symbol=symbol, trades=0,
            max_win_streak=0, max_loss_streak=0,
            current_streak_type="none", current_streak_length=0,
            avg_win_streak=0.0, avg_loss_streak=0.0,
            total_win_streaks=0, total_loss_streaks=0,
            longest_win_streak_start="", longest_loss_streak_start="",
            streaks=[],
        )

    events = _compute_streaks_v2(rows)

    win_streaks = [e for e in events if e.type == "win"]
    loss_streaks = [e for e in events if e.type == "loss"]

    max_win = max((e.length for e in win_streaks), default=0)
    max_loss = max((e.length for e in loss_streaks), default=0)

    avg_win = round(sum(e.length for e in win_streaks) / len(win_streaks), 2) if win_streaks else 0.0
    avg_loss = round(sum(e.length for e in loss_streaks) / len(loss_streaks), 2) if loss_streaks else 0.0

    # 最大連勝/最大連敗の開始日
    longest_win_event = max(win_streaks, key=lambda e: e.length, default=None)
    longest_loss_event = max(loss_streaks, key=lambda e: e.length, default=None)

    # 現在のストリーク（最後の StreakEvent）
    last_event = events[-1]

    return StreakStats(
        symbol=symbol,
        trades=n,
        max_win_streak=max_win,
        max_loss_streak=max_loss,
        current_streak_type=last_event.type,
        current_streak_length=last_event.length,
        avg_win_streak=avg_win,
        avg_loss_streak=avg_loss,
        total_win_streaks=len(win_streaks),
        total_loss_streaks=len(loss_streaks),
        longest_win_streak_start=longest_win_event.start_at[:10] if longest_win_event else "",
        longest_loss_streak_start=longest_loss_event.start_at[:10] if longest_loss_event else "",
        streaks=events,
    )


def get_streak_stats_by_symbol(db_path=None) -> list[StreakStats]:
    """各通貨ペア別の連勝/連敗統計一覧を返す。"""
    path = db_path or DB_PATH
    with get_db(path) as conn:
        symbols = [
            row[0]
            for row in conn.execute(
                """SELECT DISTINCT symbol FROM approval_history
                   WHERE outcome IN ('win','loss') AND human_action IN ('buy','sell')
                   ORDER BY symbol"""
            ).fetchall()
        ]
    return [get_streak_stats(sym, db_path=path) for sym in symbols]
