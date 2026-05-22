"""Phase 71: 地政学リスクアラート通知

strong_bullish / strong_bearish のイベントが記録されたとき、
既存の Gmail SMTP アダプターでメール通知を送信する。
自動注文は発生しない。
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# アラートを送信する USD 影響レベル
ALERT_IMPACTS: frozenset[str] = frozenset({"strong_bullish", "strong_bearish"})

_IMPACT_LABELS: dict[str, str] = {
    "strong_bullish": "強いドル高 ▲▲",
    "strong_bearish": "強いドル安 ▼▼",
}


def should_geo_alert(usd_impact: str) -> bool:
    """アラートを送信すべきか判定する。

    環境変数 NOTIFY_GEO_ALERT=false で無効化できる（デフォルト: true）。
    """
    enabled = os.getenv("NOTIFY_GEO_ALERT", "true").lower() == "true"
    return enabled and usd_impact in ALERT_IMPACTS


def build_geo_alert_message(analysis: object) -> str:
    """GeopoliticalAnalysis から通知メッセージ文字列を生成する。"""
    label = _IMPACT_LABELS.get(getattr(analysis, "usd_impact", ""), analysis.usd_impact)  # type: ignore[attr-defined]
    lines = [
        f"【地政学アラート】{label}リスク検出",
        f"カテゴリー: {analysis.category}",  # type: ignore[attr-defined]
        f"イベント: {analysis.event_text[:120]}",  # type: ignore[attr-defined]
        f"根拠: {analysis.reasoning[:160]}",  # type: ignore[attr-defined]
    ]
    outlook = getattr(analysis, "short_term_outlook", "")
    if outlook:
        lines.append(f"短期見通し: {outlook[:120]}")
    risk = getattr(analysis, "risk_factors", "")
    if risk:
        lines.append(f"リスク: {risk[:120]}")
    lines.append(f"分析プロバイダー: {getattr(analysis, 'ai_provider', 'unknown')}")
    lines.append("※ 投資判断は自己責任で。自動注文は発生しません。")
    return "\n".join(lines)


def send_geo_alert(analysis: object) -> bool:
    """地政学リスクアラートをメールで送信する。

    - strong_bullish / strong_bearish のみ対象
    - NOTIFY_GEO_ALERT=false で無効化可能
    - メール未設定時は LogOnlyAdapter でログ出力のみ
    - 失敗しても例外を外に出さない（分析処理を止めない）
    """
    usd_impact = getattr(analysis, "usd_impact", "neutral")
    if not should_geo_alert(usd_impact):
        return False

    try:
        from app.services.notification import get_notification_adapter
        adapter = get_notification_adapter()
        message = build_geo_alert_message(analysis)
        result = adapter.send(message)
        if result:
            logger.info("地政学アラート送信完了: %s", usd_impact)
        return result
    except Exception as exc:
        logger.warning("地政学アラート送信エラー: %s", exc)
        return False
