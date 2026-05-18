"""Phase 33: カスタムアラート評価エンジン

スキャン実行後に有効なアラートを評価し、条件一致時に通知を送る。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# 条件タイプと評価ロジックの対応
_CONDITION_TYPES = {
    "signal_type",    # BUY / SELL / BUY_OR_SELL
    "confluence_min", # int: TF一致度スコアが N 以上
    "rsi_below",      # float: RSI が値未満
    "rsi_above",      # float: RSI が値以上
    "score_min",      # int: |score| が値以上
}


def _is_in_cooldown(alert: dict[str, Any]) -> bool:
    """クールダウン中かどうかを判定する。"""
    last = alert.get("last_triggered_at")
    if not last:
        return False
    try:
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
        cooldown = int(alert.get("cooldown_minutes", 60))
        return datetime.utcnow() < last_dt + timedelta(minutes=cooldown)
    except (ValueError, TypeError):
        return False


def _evaluate_condition(alert: dict[str, Any], result: Any) -> bool:
    """1件のアラート条件を評価して True/False を返す。"""
    ctype = alert["condition_type"]
    cvalue = alert["condition_value"]

    if ctype == "signal_type":
        if cvalue == "BUY_OR_SELL":
            return result.signal in ("BUY", "SELL")
        return result.signal == cvalue

    if ctype == "confluence_min":
        if result.confluence is None:
            return False
        try:
            return result.confluence.confluence_score >= int(cvalue)
        except (ValueError, TypeError):
            return False

    if ctype == "rsi_below":
        if result.rsi is None:
            return False
        try:
            return result.rsi < float(cvalue)
        except (ValueError, TypeError):
            return False

    if ctype == "rsi_above":
        if result.rsi is None:
            return False
        try:
            return result.rsi >= float(cvalue)
        except (ValueError, TypeError):
            return False

    if ctype == "score_min":
        if result.score is None:
            return False
        try:
            return abs(result.score) >= int(cvalue)
        except (ValueError, TypeError):
            return False

    return False


def evaluate_alerts(result: Any) -> list[dict[str, Any]]:
    """分析結果に対して有効なアラートを評価し、発火したアラートリストを返す。

    発火したアラートは last_triggered_at を更新し、通知を送る。
    通知失敗は握りつぶしてログに記録するのみ（スキャンを止めない）。
    """
    from app.database.repository import get_active_alerts, update_alert_triggered
    from app.services.notification import GmailAdapter, LogOnlyAdapter
    import os

    triggered: list[dict[str, Any]] = []

    try:
        alerts = get_active_alerts()
    except Exception as exc:
        logger.error("アラート取得エラー: %s", exc)
        return triggered

    for alert in alerts:
        if alert["symbol"] != result.symbol:
            continue
        if _is_in_cooldown(alert):
            logger.debug("クールダウン中のためスキップ: alert_id=%s", alert["id"])
            continue
        try:
            if not _evaluate_condition(alert, result):
                continue
        except Exception as exc:
            logger.error("アラート評価エラー (id=%s): %s", alert["id"], exc)
            continue

        triggered.append(alert)
        try:
            update_alert_triggered(alert["id"])
        except Exception as exc:
            logger.error("last_triggered_at 更新エラー (id=%s): %s", alert["id"], exc)

        # 通知送信
        try:
            _send_alert_notification(alert, result)
        except Exception as exc:
            logger.error("アラート通知エラー (id=%s): %s", alert["id"], exc)

    return triggered


def _send_alert_notification(alert: dict[str, Any], result: Any) -> None:
    """アラート発火通知を送る。"""
    from app.services.notification import GmailAdapter, LogOnlyAdapter
    import os

    label = alert.get("label", "アラート")
    symbol = result.symbol
    signal = result.signal
    rsi = f"{result.rsi:.1f}" if result.rsi is not None else "---"
    score = result.score if result.score is not None else "---"
    confluence_label = result.confluence.label if result.confluence else "---"

    message = (
        f"【FXアラート】{label}\n"
        f"通貨ペア: {symbol}\n"
        f"シグナル: {signal}\n"
        f"TF一致度: {confluence_label}\n"
        f"RSI: {rsi}\n"
        f"スコア: {score}\n"
        f"条件: {alert['condition_type']} = {alert['condition_value']}"
    )

    from_addr = os.getenv("EMAIL_FROM", "")
    app_pw = os.getenv("EMAIL_APP_PASSWORD", "")
    to_addr = os.getenv("EMAIL_TO", "")

    if from_addr and app_pw and to_addr:
        try:
            adapter = GmailAdapter(from_addr, app_pw, to_addr)
            adapter.send(message)
            logger.info("アラート通知送信: %s / %s", label, symbol)
            return
        except Exception as exc:
            logger.warning("Gmail送信失敗（LogOnlyにフォールバック）: %s", exc)

    from app.services.notification import LogOnlyAdapter
    LogOnlyAdapter().send(message)
