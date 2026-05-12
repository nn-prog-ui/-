"""承認履歴のCRUD操作"""
from __future__ import annotations

import json
from datetime import datetime
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
) -> int:
    """分析結果と人間の承認アクションをSQLiteに保存する。

    承認ボタンを押しても注文は発生しない。履歴保存のみ。

    Returns:
        保存されたレコードのID
    """
    if human_action not in VALID_ACTIONS:
        raise ValueError(f"無効なアクション: {human_action}。有効値: {VALID_ACTIONS}")

    skip_reasons_json = json.dumps(result.skip_reasons, ensure_ascii=False)

    with get_db() as conn:
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
