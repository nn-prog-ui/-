"""承認履歴のCRUD操作"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database.db import get_db
from app.services.market_analyzer import AnalysisResult

HUMAN_ACTION_BUY = "buy_approved"
HUMAN_ACTION_SELL = "sell_approved"
HUMAN_ACTION_SKIP = "skipped"

VALID_ACTIONS = {HUMAN_ACTION_BUY, HUMAN_ACTION_SELL, HUMAN_ACTION_SKIP}


def save_approval(
    result: AnalysisResult,
    human_action: str,
    notes: str = "",
    db_path: Path | None = None,
) -> int:
    """分析結果と人間の承認アクションをSQLiteに保存する。

    承認ボタンを押しても注文は発生しない。履歴保存のみ。

    Returns:
        保存されたレコードのID
    """
    if human_action not in VALID_ACTIONS:
        raise ValueError(f"無効なアクション: {human_action}。有効値: {VALID_ACTIONS}")

    skip_reasons_json = json.dumps(result.skip_reasons, ensure_ascii=False)

    with get_db(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO approval_history (
                created_at, symbol, current_price, signal, score,
                daily_trend, h4_trend, h1_status, rsi, atr_value, atr_status,
                recent_high, recent_low, entry_price, stop_loss, take_profit,
                risk_reward, economic_event_warning, economic_event_name,
                ai_comment, human_action, notes, is_dummy_data, skip_reasons
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            (
                result.analyzed_at.strftime("%Y-%m-%d %H:%M:%S"),
                result.symbol,
                result.current_price,
                result.signal,
                result.score,
                result.daily_trend,
                result.h4_trend,
                result.h1_status,
                result.rsi,
                result.atr_value,
                result.atr_status,
                result.recent_high,
                result.recent_low,
                result.entry_price,
                result.stop_loss,
                result.take_profit,
                result.risk_reward,
                1 if result.economic_warning else 0,
                result.economic_event_name,
                result.ai_comment,
                human_action,
                notes,
                1 if result.is_dummy_data else 0,
                skip_reasons_json,
            ),
        )
        return cursor.lastrowid


def get_history(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """承認履歴を新しい順で取得する。"""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM approval_history
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [dict(row) for row in rows]


def get_history_count() -> int:
    """承認履歴の総件数を返す。"""
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM approval_history").fetchone()
    return row["cnt"]


def get_by_id(record_id: int) -> dict[str, Any] | None:
    """IDで履歴レコードを取得する。"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM approval_history WHERE id = ?", (record_id,)
        ).fetchone()
    return dict(row) if row else None


def get_open_trades(db_path: Path | None = None) -> list[dict]:
    """BUY/SELL承認済みでoutcomeがNULLの取引を返す。"""
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM approval_history
            WHERE human_action IN ('buy_approved', 'sell_approved')
              AND outcome IS NULL
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def close_trade(
    record_id: int,
    outcome: str,
    exit_price: float,
    pnl_pips: float,
    db_path: Path | None = None,
) -> None:
    """取引結果を記録する。outcome は 'win' or 'loss'"""
    if outcome not in ("win", "loss"):
        raise ValueError(f"無効なoutcome: {outcome}。有効値: 'win', 'loss'")
    closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db(db_path) as conn:
        conn.execute(
            """
            UPDATE approval_history
            SET outcome = ?, exit_price = ?, closed_at = ?, pnl_pips = ?
            WHERE id = ?
            """,
            (outcome, exit_price, closed_at, pnl_pips, record_id),
        )


def get_performance_stats(db_path: Path | None = None) -> dict:
    """勝率・損益統計を返す。

    Returns:
        {
            total_trades: int,      # BUY/SELL承認の合計（open含む）
            closed_trades: int,     # 勝ち+負け
            win_count: int,
            loss_count: int,
            open_count: int,        # outcome IS NULL のBUY/SELL承認
            win_rate: float | None, # win / closed * 100
            total_pips: float,      # pnl_pipsの合計
            avg_pips: float | None, # closed取引の平均pips
        }
    """
    with get_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_trades,
                SUM(CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END) AS closed_trades,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS win_count,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS loss_count,
                SUM(CASE WHEN outcome IS NULL THEN 1 ELSE 0 END) AS open_count,
                SUM(CASE WHEN pnl_pips IS NOT NULL THEN pnl_pips ELSE 0 END) AS total_pips,
                AVG(CASE WHEN outcome IS NOT NULL THEN pnl_pips ELSE NULL END) AS avg_pips
            FROM approval_history
            WHERE human_action IN ('buy_approved', 'sell_approved')
            """
        ).fetchone()

    if row is None:
        return {
            "total_trades": 0,
            "closed_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "open_count": 0,
            "win_rate": None,
            "total_pips": 0.0,
            "avg_pips": None,
        }

    total_trades = row["total_trades"] or 0
    closed_trades = row["closed_trades"] or 0
    win_count = row["win_count"] or 0
    loss_count = row["loss_count"] or 0
    open_count = row["open_count"] or 0
    total_pips = row["total_pips"] or 0.0
    avg_pips = row["avg_pips"]

    win_rate = (win_count / closed_trades * 100) if closed_trades > 0 else None

    return {
        "total_trades": total_trades,
        "closed_trades": closed_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "open_count": open_count,
        "win_rate": win_rate,
        "total_pips": total_pips,
        "avg_pips": avg_pips,
    }


def check_and_close_open_trades(
    current_price: float,
    symbol: str,
    db_path: Path | None = None,
) -> list[dict]:
    """オープン中の取引をcurrent_priceとSL/TPで照合し、ヒットしたものを自動クローズ。

    クローズした取引のリストを返す（通知用）。

    pips計算: 'JPY'がsymbolに含まれる場合 pip_size=0.01、それ以外は0.0001
    BUY: price >= take_profit → win; price <= stop_loss → loss
    SELL: price <= take_profit → win; price >= stop_loss → loss
    """
    pip_size = 0.01 if "JPY" in symbol.upper() else 0.0001
    open_trades = get_open_trades(db_path)
    closed = []

    for trade in open_trades:
        entry_price = trade.get("entry_price")
        stop_loss = trade.get("stop_loss")
        take_profit = trade.get("take_profit")
        human_action = trade.get("human_action", "")

        if entry_price is None or stop_loss is None or take_profit is None:
            continue

        outcome = None
        if human_action == HUMAN_ACTION_BUY:
            if current_price >= take_profit:
                outcome = "win"
            elif current_price <= stop_loss:
                outcome = "loss"
        elif human_action == HUMAN_ACTION_SELL:
            if current_price <= take_profit:
                outcome = "win"
            elif current_price >= stop_loss:
                outcome = "loss"

        if outcome is not None:
            pnl_pips = (current_price - entry_price) / pip_size
            if human_action == HUMAN_ACTION_SELL:
                pnl_pips = -pnl_pips
            close_trade(trade["id"], outcome, current_price, pnl_pips, db_path)
            trade["outcome"] = outcome
            trade["exit_price"] = current_price
            trade["pnl_pips"] = pnl_pips
            closed.append(trade)

    return closed


# ============================================================
# Phase 12: デモ注文 CRUD
# ============================================================

def save_demo_order(
    approval_id: int,
    symbol: str,
    direction: str,
    units: int,
    entry_price: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    oanda_trade_id: str | None,
    oanda_order_id: str | None,
    filled_price: float | None,
    notes: str = "",
    db_path: Path | None = None,
) -> int:
    """デモ注文結果をSQLiteに記録して IDを返す。"""
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO demo_orders (
                created_at, approval_id, symbol, direction, units,
                entry_price, stop_loss, take_profit,
                oanda_trade_id, oanda_order_id, filled_price, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                datetime.utcnow().isoformat(),
                approval_id,
                symbol,
                direction,
                units,
                entry_price,
                stop_loss,
                take_profit,
                oanda_trade_id,
                oanda_order_id,
                filled_price,
                notes,
            ),
        )
        return cursor.lastrowid


def get_demo_orders(limit: int = 50, db_path: Path | None = None) -> list[dict[str, Any]]:
    """デモ注文履歴を新しい順に返す。"""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM demo_orders ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_approval_by_id(record_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    """承認履歴の1件をIDで取得する。"""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM approval_history WHERE id = ?", (record_id,)
        ).fetchone()
    return dict(row) if row else None


def get_demo_order_by_id(demo_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    """デモ注文の1件をIDで取得する。"""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM demo_orders WHERE id = ?", (demo_id,)
        ).fetchone()
    return dict(row) if row else None


def get_open_demo_orders(db_path: Path | None = None) -> list[dict[str, Any]]:
    """statusが'open'のデモ注文一覧を返す。"""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM demo_orders WHERE status = 'open' ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def close_demo_order(
    demo_id: int,
    exit_price: float,
    pnl_pips: float,
    db_path: Path | None = None,
) -> None:
    """デモ注文をクローズして損益を記録する。"""
    closed_at = datetime.utcnow().isoformat()
    with get_db(db_path) as conn:
        conn.execute(
            """
            UPDATE demo_orders
            SET status = 'closed', exit_price = ?, pnl_pips = ?, closed_at = ?
            WHERE id = ?
            """,
            (exit_price, pnl_pips, closed_at, demo_id),
        )
