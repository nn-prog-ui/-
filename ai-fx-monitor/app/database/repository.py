"""承認履歴のCRUD操作"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
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


def get_signal_pattern_stats(
    signal: str | None = None,
    daily_trend: str | None = None,
    h4_trend: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """過去のトレードから勝率パターンを返す（Phase 20：過去トレードからの学習）。

    Returns:
        {
            overall_win_rate: float | None,  # 全体勝率（signal種別）
            overall_closed: int,
            pattern_win_rate: float | None,  # 同じdaily+h4トレンドパターンの勝率
            pattern_closed: int,
            recent_outcomes: list[str],      # 同パターンの最新5件のoutcome
        }
    """
    action = (
        HUMAN_ACTION_BUY if signal == "BUY"
        else HUMAN_ACTION_SELL if signal == "SELL"
        else None
    )

    with get_db(db_path) as conn:
        if action:
            overall_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS closed,
                    SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins
                FROM approval_history
                WHERE human_action = ? AND outcome IS NOT NULL
                """,
                (action,),
            ).fetchone()
        else:
            overall_row = None

        if action and daily_trend and h4_trend:
            pattern_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS closed,
                    SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins
                FROM approval_history
                WHERE human_action = ? AND daily_trend = ? AND h4_trend = ?
                  AND outcome IS NOT NULL
                """,
                (action, daily_trend, h4_trend),
            ).fetchone()
            recent_rows = conn.execute(
                """
                SELECT outcome FROM approval_history
                WHERE human_action = ? AND daily_trend = ? AND h4_trend = ?
                  AND outcome IS NOT NULL
                ORDER BY created_at DESC LIMIT 5
                """,
                (action, daily_trend, h4_trend),
            ).fetchall()
        else:
            pattern_row = None
            recent_rows = []

    overall_closed = (overall_row["closed"] or 0) if overall_row else 0
    overall_wins = (overall_row["wins"] or 0) if overall_row else 0
    overall_win_rate = (overall_wins / overall_closed * 100) if overall_closed > 0 else None

    pattern_closed = (pattern_row["closed"] or 0) if pattern_row else 0
    pattern_wins = (pattern_row["wins"] or 0) if pattern_row else 0
    pattern_win_rate = (pattern_wins / pattern_closed * 100) if pattern_closed > 0 else None

    return {
        "overall_win_rate": overall_win_rate,
        "overall_closed": overall_closed,
        "pattern_win_rate": pattern_win_rate,
        "pattern_closed": pattern_closed,
        "recent_outcomes": [row["outcome"] for row in recent_rows],
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


def get_demo_performance_stats(db_path: Path | None = None) -> dict:
    """デモ注文の成績統計を返す。

    Returns:
        {
            total_orders: int,       # 全デモ注文数
            open_count: int,         # オープン中
            closed_count: int,       # 決済済み
            win_count: int,          # pnl_pips > 0
            loss_count: int,         # pnl_pips <= 0
            win_rate: float | None,  # 勝率(%)
            total_pips: float,       # 合計損益(pips)
            avg_pips: float | None,  # 平均損益(pips/取引)
        }
    """
    with get_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_orders,
                SUM(CASE WHEN status = 'open'   THEN 1 ELSE 0 END) AS open_count,
                SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed_count,
                SUM(CASE WHEN status = 'closed' AND pnl_pips >  0 THEN 1 ELSE 0 END) AS win_count,
                SUM(CASE WHEN status = 'closed' AND pnl_pips <= 0 THEN 1 ELSE 0 END) AS loss_count,
                SUM(CASE WHEN pnl_pips IS NOT NULL THEN pnl_pips ELSE 0 END) AS total_pips,
                AVG(CASE WHEN status = 'closed' THEN pnl_pips ELSE NULL END) AS avg_pips
            FROM demo_orders
            """
        ).fetchone()

    if row is None:
        return {
            "total_orders": 0,
            "open_count": 0,
            "closed_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": None,
            "total_pips": 0.0,
            "avg_pips": None,
        }

    total_orders = row["total_orders"] or 0
    open_count   = row["open_count"]   or 0
    closed_count = row["closed_count"] or 0
    win_count    = row["win_count"]    or 0
    loss_count   = row["loss_count"]   or 0
    total_pips   = row["total_pips"]   or 0.0
    avg_pips     = row["avg_pips"]

    win_rate = (win_count / closed_count * 100) if closed_count > 0 else None

    return {
        "total_orders": total_orders,
        "open_count":   open_count,
        "closed_count": closed_count,
        "win_count":    win_count,
        "loss_count":   loss_count,
        "win_rate":     win_rate,
        "total_pips":   total_pips,
        "avg_pips":     avg_pips,
    }


# ============================================================
# Phase 22: アプリ設定 CRUD
# ============================================================

# デフォルト設定値（.envが未設定のときのフォールバック）
_SETTINGS_DEFAULTS: dict[str, str] = {
    "scan_enabled": "true",
    "scan_interval_minutes": "60",
    "notify_on_buy": "true",
    "notify_on_sell": "true",
    "notify_on_skip": "false",
    "notify_min_score": "0",
}


def get_setting(key: str, db_path: Path | None = None) -> str | None:
    """設定値を返す。DBになければデフォルト値を返す。"""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
    if row:
        return row["value"]
    return _SETTINGS_DEFAULTS.get(key)


def set_setting(key: str, value: str, db_path: Path | None = None) -> None:
    """設定値を保存する（upsert）。"""
    updated_at = datetime.utcnow().isoformat()
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, updated_at),
        )


def get_all_settings(db_path: Path | None = None) -> dict[str, str]:
    """全設定をデフォルト込みで返す。DBの値がデフォルトを上書きする。"""
    result = dict(_SETTINGS_DEFAULTS)
    with get_db(db_path) as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    for row in rows:
        result[row["key"]] = row["value"]
    return result


def save_settings(settings: dict[str, str], db_path: Path | None = None) -> None:
    """複数設定を一括保存する。"""
    for key, value in settings.items():
        if key in _SETTINGS_DEFAULTS:
            set_setting(key, value, db_path)


# ============================================================
# Phase 24: 判定精度レポート用クエリ
# ============================================================

def get_performance_report(db_path: Path | None = None) -> dict:
    """判定精度レポートデータを返す。

    Returns:
        {
            by_signal: list[dict],          # BUY/SELL別統計
            by_trend: list[dict],           # 日足×4H別統計
            by_score: list[dict],           # スコア別統計
            by_rsi_range: list[dict],       # RSIレンジ別統計
            monthly: list[dict],            # 月次統計
            total_closed: int,
        }
    """
    with get_db(db_path) as conn:
        # BUY/SELL別
        by_signal_rows = conn.execute("""
            SELECT
                signal,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'win'  THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
                AVG(CASE WHEN outcome IS NOT NULL THEN pnl_pips ELSE NULL END) AS avg_pips,
                SUM(CASE WHEN outcome IS NOT NULL THEN pnl_pips ELSE 0 END) AS total_pips
            FROM approval_history
            WHERE human_action IN ('buy_approved', 'sell_approved')
              AND outcome IS NOT NULL
            GROUP BY signal
        """).fetchall()

        # 日足×4H トレンド別
        by_trend_rows = conn.execute("""
            SELECT
                daily_trend, h4_trend,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'win'  THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
                AVG(CASE WHEN outcome IS NOT NULL THEN pnl_pips ELSE NULL END) AS avg_pips
            FROM approval_history
            WHERE human_action IN ('buy_approved', 'sell_approved')
              AND outcome IS NOT NULL
            GROUP BY daily_trend, h4_trend
            ORDER BY total DESC
        """).fetchall()

        # スコア別（0〜7の範囲でバケット）
        by_score_rows = conn.execute("""
            SELECT
                ABS(score) AS abs_score,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'win'  THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses
            FROM approval_history
            WHERE human_action IN ('buy_approved', 'sell_approved')
              AND outcome IS NOT NULL AND score IS NOT NULL
            GROUP BY abs_score
            ORDER BY abs_score
        """).fetchall()

        # RSIレンジ別（10刻み）
        by_rsi_rows = conn.execute("""
            SELECT
                CAST(rsi / 10 AS INTEGER) * 10 AS rsi_bucket,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'win'  THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses
            FROM approval_history
            WHERE human_action IN ('buy_approved', 'sell_approved')
              AND outcome IS NOT NULL AND rsi IS NOT NULL
            GROUP BY rsi_bucket
            ORDER BY rsi_bucket
        """).fetchall()

        # 月次統計
        monthly_rows = conn.execute("""
            SELECT
                SUBSTR(created_at, 1, 7) AS month,
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'win'  THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN outcome IS NOT NULL THEN pnl_pips ELSE 0 END) AS total_pips
            FROM approval_history
            WHERE human_action IN ('buy_approved', 'sell_approved')
              AND outcome IS NOT NULL
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        """).fetchall()

        total_row = conn.execute("""
            SELECT COUNT(*) AS cnt FROM approval_history
            WHERE human_action IN ('buy_approved', 'sell_approved')
              AND outcome IS NOT NULL
        """).fetchone()

    def _win_rate(wins: int, total: int) -> float | None:
        return (wins / total * 100) if total > 0 else None

    by_signal = [
        {
            "signal": r["signal"],
            "label": "買い" if r["signal"] == "BUY" else "売り",
            "total": r["total"],
            "wins": r["wins"] or 0,
            "losses": r["losses"] or 0,
            "win_rate": _win_rate(r["wins"] or 0, r["total"]),
            "avg_pips": r["avg_pips"],
            "total_pips": r["total_pips"] or 0.0,
        }
        for r in by_signal_rows
    ]

    by_trend = [
        {
            "daily_trend": r["daily_trend"] or "---",
            "h4_trend": r["h4_trend"] or "---",
            "total": r["total"],
            "wins": r["wins"] or 0,
            "losses": r["losses"] or 0,
            "win_rate": _win_rate(r["wins"] or 0, r["total"]),
            "avg_pips": r["avg_pips"],
        }
        for r in by_trend_rows
    ]

    by_score = [
        {
            "score": r["abs_score"],
            "total": r["total"],
            "wins": r["wins"] or 0,
            "losses": r["losses"] or 0,
            "win_rate": _win_rate(r["wins"] or 0, r["total"]),
        }
        for r in by_score_rows
    ]

    by_rsi_range = [
        {
            "rsi_range": f"{r['rsi_bucket']}〜{r['rsi_bucket'] + 9}",
            "total": r["total"],
            "wins": r["wins"] or 0,
            "losses": r["losses"] or 0,
            "win_rate": _win_rate(r["wins"] or 0, r["total"]),
        }
        for r in by_rsi_rows
        if r["rsi_bucket"] is not None
    ]

    monthly = [
        {
            "month": r["month"],
            "total": r["total"],
            "wins": r["wins"] or 0,
            "losses": r["losses"] or 0,
            "win_rate": _win_rate(r["wins"] or 0, r["total"]),
            "total_pips": r["total_pips"] or 0.0,
        }
        for r in monthly_rows
    ]

    return {
        "by_signal": by_signal,
        "by_trend": by_trend,
        "by_score": by_score,
        "by_rsi_range": by_rsi_range,
        "monthly": monthly,
        "total_closed": total_row["cnt"] if total_row else 0,
    }


# ============================================================
# Phase 27: バックテスト結果をapproval_historyに保存
# ============================================================

def save_backtest_results(
    trades: list,
    symbol: str,
    db_path: Path | None = None,
) -> int:
    """バックテスト取引結果をapproval_historyに一括保存する。

    - is_dummy_data=1、human_actionはBUY→buy_approved、SELL→sell_approved
    - outcome='open'の取引は保存しない（SL/TP未到達）
    - 戻り値: 保存件数
    """
    base_dt = datetime.utcnow()
    saved = 0

    with get_db(db_path) as conn:
        for i, trade in enumerate(trades):
            if trade.outcome == "open":
                continue

            signal = trade.signal
            human_action = HUMAN_ACTION_BUY if signal == "BUY" else HUMAN_ACTION_SELL
            daily_trend = "上昇" if signal == "BUY" else "下降"
            h4_trend = daily_trend
            score = int(trade.risk_reward)

            # 各トレードで created_at を少しずつずらす（i秒加算）
            from datetime import timedelta
            created_at = (base_dt + timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S")

            conn.execute(
                """
                INSERT INTO approval_history (
                    created_at, symbol, signal, human_action, is_dummy_data,
                    outcome, exit_price, pnl_pips, closed_at,
                    entry_price, stop_loss, take_profit, risk_reward,
                    score, daily_trend, h4_trend
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?
                )
                """,
                (
                    created_at,
                    symbol,
                    signal,
                    human_action,
                    1,
                    trade.outcome,
                    trade.exit_price,
                    trade.pnl_pips,
                    created_at,
                    trade.entry_price,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.risk_reward,
                    score,
                    daily_trend,
                    h4_trend,
                ),
            )
            saved += 1

    return saved


# ============================================================
# Phase 26: チャート用データ
# ============================================================

def get_chart_data(symbol: str | None = None, limit: int = 60, db_path: Path | None = None) -> list[dict]:
    """クローズ済み取引の時系列データを返す（チャート描画用）。

    Returns:
        累積pipsを含む取引リスト（古い順）
    """
    with get_db(db_path) as conn:
        params: list = []
        where = "WHERE human_action IN ('buy_approved', 'sell_approved') AND outcome IS NOT NULL"
        if symbol:
            where += " AND symbol = ?"
            params.append(symbol)
        rows = conn.execute(
            f"""
            SELECT created_at, signal, score, pnl_pips, outcome, symbol
            FROM approval_history
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params + [limit],
        ).fetchall()

    trades = [dict(r) for r in reversed(rows)]
    cumulative = 0.0
    for t in trades:
        cumulative += t["pnl_pips"] or 0.0
        t["cumulative_pips"] = round(cumulative, 1)
    return trades


# ---------------------------------------------------------------------------
# Phase 33: カスタムアラート CRUD
# ---------------------------------------------------------------------------

ALERT_CONDITION_TYPES = {
    "signal_type": "シグナル種別",
    "confluence_min": "TF一致度（以上）",
    "rsi_below": "RSI（未満）",
    "rsi_above": "RSI（以上）",
    "score_min": "スコア絶対値（以上）",
}


def create_alert(
    symbol: str,
    label: str,
    condition_type: str,
    condition_value: str,
    cooldown_minutes: int = 60,
    db_path: Path | None = None,
) -> int:
    """アラートを新規作成して ID を返す。"""
    if condition_type not in ALERT_CONDITION_TYPES:
        raise ValueError(f"無効な condition_type: {condition_type}")
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO alerts (created_at, symbol, label, condition_type, condition_value,
                                active, cooldown_minutes)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                label,
                condition_type,
                condition_value,
                cooldown_minutes,
            ),
        )
        return cursor.lastrowid


def get_alerts(db_path: Path | None = None) -> list[dict[str, Any]]:
    """全アラートを新しい順で返す。"""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_active_alerts(db_path: Path | None = None) -> list[dict[str, Any]]:
    """有効（active=1）なアラートだけ返す。"""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE active = 1"
        ).fetchall()
    return [dict(r) for r in rows]


def toggle_alert(alert_id: int, db_path: Path | None = None) -> bool:
    """アラートの active フラグを反転して、反転後の値を返す。"""
    with get_db(db_path) as conn:
        row = conn.execute("SELECT active FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        if row is None:
            raise ValueError(f"アラートが見つかりません: id={alert_id}")
        new_active = 0 if row["active"] else 1
        conn.execute("UPDATE alerts SET active = ? WHERE id = ?", (new_active, alert_id))
    return bool(new_active)


def delete_alert(alert_id: int, db_path: Path | None = None) -> None:
    """アラートを削除する。"""
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))


def update_alert_triggered(alert_id: int, db_path: Path | None = None) -> None:
    """last_triggered_at を現在時刻に更新する。"""
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE alerts SET last_triggered_at = ? WHERE id = ?",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), alert_id),
        )


# ---------------------------------------------------------------------------
# Phase 34: トレードジャーナル CRUD
# ---------------------------------------------------------------------------

JOURNAL_ENTRY_TYPES = [
    "ブレイクアウト",
    "押し目買い",
    "戻り売り",
    "反発",
    "ダマシ",
    "反省",
    "要検証",
    "その他",
]

JOURNAL_EMOTION_LABELS = {
    1: "😰 焦り",
    2: "😟 やや焦り",
    3: "😐 普通",
    4: "🙂 冷静",
    5: "😌 完全冷静",
}


def upsert_journal(
    approval_id: int,
    notes: str = "",
    tags: str = "",
    entry_type: str = "その他",
    emotion_score: int = 3,
    db_path: Path | None = None,
) -> int:
    """ジャーナルを新規作成または更新して ID を返す。"""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM trade_journal WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE trade_journal
                SET updated_at=?, notes=?, tags=?, entry_type=?, emotion_score=?
                WHERE approval_id=?
                """,
                (now, notes, tags, entry_type, emotion_score, approval_id),
            )
            return existing["id"]
        cursor = conn.execute(
            """
            INSERT INTO trade_journal (approval_id, created_at, updated_at, notes, tags, entry_type, emotion_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (approval_id, now, now, notes, tags, entry_type, emotion_score),
        )
        return cursor.lastrowid


def get_journal_entry(approval_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    """特定の承認IDのジャーナルを返す。存在しなければ None。"""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM trade_journal WHERE approval_id = ?", (approval_id,)
        ).fetchone()
    return dict(row) if row else None


def get_journal_entries(
    tag_filter: str | None = None,
    entry_type_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """ジャーナル一覧を approval_history と JOIN して返す。タグ・タイプで絞り込み可。"""
    where_clauses = ["j.notes IS NOT NULL"]
    params: list[Any] = []

    if tag_filter:
        where_clauses.append("j.tags LIKE ?")
        params.append(f"%{tag_filter}%")
    if entry_type_filter:
        where_clauses.append("j.entry_type = ?")
        params.append(entry_type_filter)

    where = " AND ".join(where_clauses)
    params += [limit, offset]

    with get_db(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                j.*,
                a.symbol, a.signal, a.human_action, a.current_price,
                a.entry_price, a.stop_loss, a.take_profit, a.risk_reward,
                a.pnl_pips, a.outcome, a.daily_trend, a.h4_trend,
                a.created_at as trade_date
            FROM trade_journal j
            JOIN approval_history a ON j.approval_id = a.id
            WHERE {where}
            ORDER BY j.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_journal_count(
    tag_filter: str | None = None,
    entry_type_filter: str | None = None,
    db_path: Path | None = None,
) -> int:
    """ジャーナル件数を返す。"""
    where_clauses = ["j.notes IS NOT NULL"]
    params: list[Any] = []

    if tag_filter:
        where_clauses.append("j.tags LIKE ?")
        params.append(f"%{tag_filter}%")
    if entry_type_filter:
        where_clauses.append("j.entry_type = ?")
        params.append(entry_type_filter)

    where = " AND ".join(where_clauses)

    with get_db(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) as cnt
            FROM trade_journal j
            JOIN approval_history a ON j.approval_id = a.id
            WHERE {where}
            """,
            params,
        ).fetchone()
    return row["cnt"] if row else 0


# ---------------------------------------------------------------------------
# Phase 35: CSV エクスポート用クエリ
# ---------------------------------------------------------------------------

def get_history_for_export(
    symbol: str | None = None,
    signal: str | None = None,
    human_action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """承認履歴をフィルター付きで全件取得する（エクスポート用）。"""
    where_clauses: list[str] = []
    params: list[Any] = []
    if symbol:
        where_clauses.append("symbol = ?")
        params.append(symbol)
    if signal:
        where_clauses.append("signal = ?")
        params.append(signal)
    if human_action:
        where_clauses.append("human_action = ?")
        params.append(human_action)
    if date_from:
        where_clauses.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("created_at <= ?")
        params.append(date_to + " 23:59:59")

    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    with get_db(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM approval_history {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_journal_for_export(
    tag_filter: str | None = None,
    entry_type_filter: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """ジャーナルを approval_history と JOIN して全件取得する（エクスポート用）。"""
    where_clauses = ["j.notes IS NOT NULL"]
    params: list[Any] = []
    if tag_filter:
        where_clauses.append("j.tags LIKE ?")
        params.append(f"%{tag_filter}%")
    if entry_type_filter:
        where_clauses.append("j.entry_type = ?")
        params.append(entry_type_filter)
    where = " AND ".join(where_clauses)
    with get_db(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                j.approval_id, j.entry_type, j.emotion_score, j.tags, j.notes,
                j.created_at as journal_created_at, j.updated_at,
                a.symbol, a.signal, a.human_action, a.current_price,
                a.entry_price, a.stop_loss, a.take_profit, a.risk_reward,
                a.pnl_pips, a.outcome, a.daily_trend, a.h4_trend,
                a.created_at as trade_date
            FROM trade_journal j
            JOIN approval_history a ON j.approval_id = a.id
            WHERE {where}
            ORDER BY j.updated_at DESC
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_demo_orders_for_export(db_path: Path | None = None) -> list[dict[str, Any]]:
    """デモ注文を全件取得する（エクスポート用）。"""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM demo_orders ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Phase 39: 経済指標カレンダー CRUD
# ---------------------------------------------------------------------------

IMPORTANCE_LEVELS = ["HIGH", "MEDIUM", "LOW"]
IMPORTANCE_LABELS = {"HIGH": "★★★ 高", "MEDIUM": "★★☆ 中", "LOW": "★☆☆ 低"}
WARNING_WINDOW_HOURS = 24  # この時間以内のHIGH/MEDIUMイベントを警戒表示


def create_economic_event(
    event_dt: str,
    currency: str,
    importance: str,
    event_name: str,
    note: str = "",
    db_path: Path | None = None,
) -> int:
    """経済指標イベントを登録して ID を返す。"""
    if importance not in IMPORTANCE_LEVELS:
        raise ValueError(f"importance は {IMPORTANCE_LEVELS} のいずれかにしてください。")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO economic_events (created_at, event_dt, currency, importance, event_name, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now, event_dt, currency.strip().upper(), importance, event_name.strip(), note.strip()),
        )
    return cur.lastrowid


def get_economic_events(
    limit: int = 50,
    offset: int = 0,
    currency: str | None = None,
    importance: str | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """登録済みイベントを event_dt 昇順で返す。"""
    where_clauses = []
    params: list = []
    if currency:
        where_clauses.append("currency = ?")
        params.append(currency.upper())
    if importance:
        where_clauses.append("importance = ?")
        params.append(importance)
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    with get_db(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM economic_events
            {where}
            ORDER BY event_dt ASC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
    return [dict(r) for r in rows]


def count_economic_events(
    currency: str | None = None,
    importance: str | None = None,
    db_path: Path | None = None,
) -> int:
    """イベント件数を返す。"""
    where_clauses = []
    params: list = []
    if currency:
        where_clauses.append("currency = ?")
        params.append(currency.upper())
    if importance:
        where_clauses.append("importance = ?")
        params.append(importance)
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    with get_db(db_path) as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM economic_events {where}", params
        ).fetchone()
    return row[0] if row else 0


def delete_economic_event(event_id: int, db_path: Path | None = None) -> bool:
    """イベントを削除して True を返す（存在しない場合は False）。"""
    with get_db(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM economic_events WHERE id = ?", (event_id,)
        )
    return cur.rowcount > 0


def get_upcoming_warning_events(
    window_hours: int = WARNING_WINDOW_HOURS,
    db_path: Path | None = None,
) -> list[dict]:
    """直近 window_hours 時間以内の HIGH/MEDIUM イベントを返す（警戒判定用）。"""
    now = datetime.utcnow()
    dt_from = now.strftime("%Y-%m-%d %H:%M:%S")
    dt_to = (now + timedelta(hours=window_hours)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM economic_events
            WHERE importance IN ('HIGH', 'MEDIUM')
              AND event_dt >= ?
              AND event_dt <= ?
            ORDER BY event_dt ASC
            """,
            (dt_from, dt_to),
        ).fetchall()
    return [dict(r) for r in rows]


def has_upcoming_warning(
    window_hours: int = WARNING_WINDOW_HOURS,
    db_path: Path | None = None,
) -> bool:
    """window_hours 以内に HIGH/MEDIUM イベントがあれば True を返す。"""
    return len(get_upcoming_warning_events(window_hours=window_hours, db_path=db_path)) > 0


# ---------------------------------------------------------------------------
# Phase 41: Web Push 購読情報 CRUD + VAPID 鍵管理
# ---------------------------------------------------------------------------

def save_push_subscription(
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str = "",
    db_path: Path | None = None,
) -> int:
    """Push 購読情報を保存して ID を返す（endpoint 重複時は更新）。"""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO push_subscriptions (created_at, endpoint, p256dh, auth, user_agent)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                p256dh=excluded.p256dh,
                auth=excluded.auth,
                user_agent=excluded.user_agent
            """,
            (now, endpoint, p256dh, auth, user_agent),
        )
    return cur.lastrowid


def delete_push_subscription(endpoint: str, db_path: Path | None = None) -> bool:
    """Push 購読情報を削除して True を返す（存在しない場合は False）。"""
    with get_db(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
        )
    return cur.rowcount > 0


def get_push_subscriptions(db_path: Path | None = None) -> list[dict]:
    """全購読情報を返す。"""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM push_subscriptions ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def count_push_subscriptions(db_path: Path | None = None) -> int:
    """購読件数を返す。"""
    with get_db(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()
    return row[0] if row else 0


def get_or_create_vapid_keys(db_path: Path | None = None) -> tuple[str, str]:
    """VAPID 鍵ペアを取得または生成して (public_b64url, private_pem) で返す。

    save_settings は _SETTINGS_DEFAULTS にないキーを無視するため、
    set_setting を直接呼び出す。
    """
    pub = get_setting("vapid_public_key", db_path=db_path)
    priv = get_setting("vapid_private_key_pem", db_path=db_path)
    if pub and priv:
        return pub, priv
    from app.services.push_sender import generate_vapid_keys
    pub, priv = generate_vapid_keys()
    set_setting("vapid_public_key", pub, db_path=db_path)
    set_setting("vapid_private_key_pem", priv, db_path=db_path)
    return pub, priv
