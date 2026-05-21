"""Phase 54: 月次・週次目標管理（Goal Tracker）

月または週単位で pip 目標を設定し、実績との対比・進捗率を返す。
注文は発生しない。集計・管理のみ。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date

from app.config import DB_PATH
from app.database.db import get_db

PERIOD_MONTHLY = "monthly"
PERIOD_WEEKLY = "weekly"
VALID_PERIOD_TYPES = {PERIOD_MONTHLY, PERIOD_WEEKLY}


@dataclass
class TradeGoal:
    id: int
    created_at: str
    period_type: str        # "monthly" / "weekly"
    period_label: str       # "2026-01" / "2026-W03"
    target_pips: float
    symbol: str | None      # None = 全通貨ペア
    note: str
    # 実績（DB から計算）
    actual_pips: float = 0.0
    actual_trades: int = 0
    progress_pct: float = 0.0   # actual / target * 100
    achieved: bool = False      # actual >= target


def current_month_label() -> str:
    return datetime.now().strftime("%Y-%m")


def current_week_label() -> str:
    iso = datetime.now().isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _actual_pips(
    period_type: str,
    period_label: str,
    symbol: str | None,
    conn,
) -> tuple[float, int]:
    """approval_history から期間内の実績 pips と件数を返す。"""
    if period_type == PERIOD_MONTHLY:
        # period_label = "2026-01" → LIKE '2026-01-%'
        date_filter = f"{period_label}-%"
        operator = "LIKE"
    else:
        # period_label = "2026-W03" → ISO week 判定は strftime('%Y-W%W') ではなく
        # 実際の日付範囲で絞る方が確実。ここでは DB 側の strftime を利用する。
        # SQLite の strftime('%Y-W%W', date) は月曜起点でない場合がある。
        # 代わりに Python で範囲を計算して BETWEEN で絞る。
        year, wnum = period_label.split("-W")
        mon = _week_monday(int(year), int(wnum))
        sun = _week_sunday(int(year), int(wnum))
        date_filter = None  # BETWEEN を使う

    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy_approved', 'sell_approved')",
        "pnl_pips IS NOT NULL",
    ]
    params: list = []

    if period_type == PERIOD_MONTHLY:
        clauses.append("created_at LIKE ?")
        params.append(date_filter)
    else:
        clauses.append("created_at BETWEEN ? AND ?")
        params.extend([mon.isoformat(), sun.isoformat() + " 23:59:59"])

    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    rows = conn.execute(
        f"SELECT pnl_pips FROM approval_history WHERE {' AND '.join(clauses)}",
        params,
    ).fetchall()

    total = sum(float(r["pnl_pips"]) for r in rows)
    return round(total, 2), len(rows)


def _week_monday(year: int, week: int) -> date:
    """ISO週の月曜日を返す。"""
    jan4 = date(year, 1, 4)
    week1_mon = jan4 - __import__('datetime').timedelta(days=jan4.isoweekday() - 1)
    return week1_mon + __import__('datetime').timedelta(weeks=week - 1)


def _week_sunday(year: int, week: int) -> date:
    return _week_monday(year, week) + __import__('datetime').timedelta(days=6)


# ── CRUD ────────────────────────────────────────────────────────────

def create_goal(
    period_type: str,
    period_label: str,
    target_pips: float,
    symbol: str | None = None,
    note: str = "",
    db_path=None,
) -> int:
    """目標を作成して id を返す。同一キーが存在する場合は上書き (UPSERT)。"""
    if period_type not in VALID_PERIOD_TYPES:
        raise ValueError(f"無効な period_type: {period_type}")
    if target_pips <= 0:
        raise ValueError("target_pips は正の値を指定してください")

    sym_key = symbol or ""  # NULL の代わりに空文字列で UNIQUE 制約を機能させる
    path = db_path or DB_PATH
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db(path) as conn:
        cur = conn.execute(
            """INSERT INTO trade_goals
               (created_at, period_type, period_label, target_pips, symbol, note)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(period_type, period_label, symbol)
               DO UPDATE SET target_pips=excluded.target_pips, note=excluded.note""",
            (now, period_type, period_label, target_pips, sym_key, note),
        )
        return cur.lastrowid


def delete_goal(goal_id: int, db_path=None) -> bool:
    path = db_path or DB_PATH
    with get_db(path) as conn:
        cur = conn.execute("DELETE FROM trade_goals WHERE id = ?", (goal_id,))
        return cur.rowcount > 0


def get_goals(
    period_type: str | None = None,
    symbol: str | None = None,
    db_path=None,
) -> list[TradeGoal]:
    """目標一覧と実績を返す（降順）。"""
    path = db_path or DB_PATH
    clauses: list[str] = []
    params: list = []
    if period_type:
        clauses.append("period_type = ?")
        params.append(period_type)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_db(path) as conn:
        rows = conn.execute(
            f"SELECT * FROM trade_goals {where} ORDER BY period_label DESC, id DESC",
            params,
        ).fetchall()

        goals: list[TradeGoal] = []
        for row in rows:
            sym = row["symbol"] or None  # '' → None に正規化
            actual, trades = _actual_pips(
                row["period_type"], row["period_label"], sym, conn
            )
            target = float(row["target_pips"])
            progress = round(actual / target * 100, 1) if target > 0 else 0.0
            goals.append(TradeGoal(
                id=row["id"],
                created_at=row["created_at"],
                period_type=row["period_type"],
                period_label=row["period_label"],
                target_pips=target,
                symbol=sym,
                note=row["note"] or "",
                actual_pips=actual,
                actual_trades=trades,
                progress_pct=progress,
                achieved=actual >= target,
            ))
    return goals


def get_goal_by_id(goal_id: int, db_path=None) -> TradeGoal | None:
    path = db_path or DB_PATH
    with get_db(path) as conn:
        row = conn.execute(
            "SELECT * FROM trade_goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if row is None:
            return None
        sym = row["symbol"] or None  # '' → None に正規化
        actual, trades = _actual_pips(
            row["period_type"], row["period_label"], sym, conn
        )
        target = float(row["target_pips"])
        progress = round(actual / target * 100, 1) if target > 0 else 0.0
        return TradeGoal(
            id=row["id"],
            created_at=row["created_at"],
            period_type=row["period_type"],
            period_label=row["period_label"],
            target_pips=target,
            symbol=sym,
            note=row["note"] or "",
            actual_pips=actual,
            actual_trades=trades,
            progress_pct=progress,
            achieved=actual >= target,
        )
