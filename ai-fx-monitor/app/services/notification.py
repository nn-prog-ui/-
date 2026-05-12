"""通知アダプターモジュール

LINE Notify を使ってBUY/SELL判定時にスマホへ通知する。
将来はSlack・メールへの切り替えが可能な設計。

設定（.env）:
    LINE_NOTIFY_TOKEN=your_token_here
    NOTIFY_ON_BUY=true       # BUY判定時に通知（デフォルト: true）
    NOTIFY_ON_SELL=true      # SELL判定時に通知（デフォルト: true）
    NOTIFY_ON_SKIP=false     # SKIP判定時に通知（デフォルト: false）
    NOTIFY_MIN_SCORE=5       # 通知する最低スコア絶対値（デフォルト: 0）

LINE Notify トークン取得方法:
    1. https://notify-bot.line.me/ja/ にアクセス
    2. ログイン → マイページ → トークンを発行する
    3. トークン名と通知先グループを選択
    4. 発行されたトークンを NOTIFY_ON_* に設定
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"


class NotificationError(Exception):
    pass


class NotificationAdapter(ABC):
    """通知アダプターの基底クラス。"""

    @abstractmethod
    def send(self, message: str) -> bool:
        """通知を送信する。成功時True、失敗時False。"""
        raise NotImplementedError


class LineNotifyAdapter(NotificationAdapter):
    """LINE Notify アダプター。"""

    def __init__(self, token: str):
        if not token:
            raise NotificationError("LINE_NOTIFY_TOKEN が設定されていません。")
        self._token = token

    @classmethod
    def from_env(cls) -> "LineNotifyAdapter":
        token = os.getenv("LINE_NOTIFY_TOKEN", "")
        if not token:
            raise NotificationError(
                "LINE_NOTIFY_TOKEN が .env に設定されていません。"
                "https://notify-bot.line.me でトークンを取得してください。"
            )
        return cls(token)

    def send(self, message: str) -> bool:
        try:
            import requests
        except ImportError:
            raise NotificationError("'requests' パッケージが必要です: pip install requests")

        try:
            resp = requests.post(
                LINE_NOTIFY_URL,
                headers={"Authorization": f"Bearer {self._token}"},
                data={"message": message},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("LINE通知送信成功")
                return True
            else:
                logger.warning("LINE通知失敗: status=%d body=%s", resp.status_code, resp.text[:100])
                return False
        except Exception as exc:
            logger.error("LINE通知エラー: %s", exc)
            return False


class LogOnlyAdapter(NotificationAdapter):
    """通知トークン未設定時のフォールバック（ログ出力のみ）。"""

    def send(self, message: str) -> bool:
        logger.info("[通知（未送信）] %s", message)
        return True


def get_notification_adapter() -> NotificationAdapter:
    """設定に応じた通知アダプターを返す。トークン未設定時はLogOnlyAdapter。"""
    token = os.getenv("LINE_NOTIFY_TOKEN", "")
    if token:
        return LineNotifyAdapter(token)
    logger.debug("LINE_NOTIFY_TOKEN未設定 → 通知はログ出力のみ")
    return LogOnlyAdapter()


def should_notify(signal: str, score: int | None) -> bool:
    """通知条件を判定する。

    NOTIFY_ON_BUY / NOTIFY_ON_SELL / NOTIFY_ON_SKIP と
    NOTIFY_MIN_SCORE で制御する。
    """
    notify_buy = os.getenv("NOTIFY_ON_BUY", "true").lower() == "true"
    notify_sell = os.getenv("NOTIFY_ON_SELL", "true").lower() == "true"
    notify_skip = os.getenv("NOTIFY_ON_SKIP", "false").lower() == "true"
    min_score = int(os.getenv("NOTIFY_MIN_SCORE", "0"))

    if signal == "BUY" and not notify_buy:
        return False
    if signal == "SELL" and not notify_sell:
        return False
    if signal == "SKIP" and not notify_skip:
        return False

    if score is not None and abs(score) < min_score:
        return False

    return True


def build_notification_message(
    symbol: str,
    signal: str,
    signal_label: str,
    current_price: float | None,
    score: int | None,
    rsi: float | None,
    entry_price: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    risk_reward: float | None,
    ai_comment: str = "",
    is_dummy_data: bool = False,
) -> str:
    """LINE通知メッセージを組み立てる。"""
    lines = [f"\n【AI FX市場監視】{symbol} {signal_label}"]

    if is_dummy_data:
        lines.append("⚠️ テストデータ使用中")

    if current_price is not None:
        lines.append(f"現在価格: {current_price:.3f}")

    if score is not None:
        lines.append(f"スコア: {'+' if score > 0 else ''}{score}")

    if rsi is not None:
        lines.append(f"RSI: {rsi:.1f}")

    if signal in ("BUY", "SELL"):
        if entry_price is not None:
            lines.append(f"エントリー: {entry_price:.3f}")
        if stop_loss is not None:
            lines.append(f"損切り: {stop_loss:.3f}")
        if take_profit is not None:
            lines.append(f"利確: {take_profit:.3f}")
        if risk_reward is not None:
            lines.append(f"RR: {risk_reward:.2f}")

    if ai_comment:
        # コメントは先頭100文字まで
        lines.append(f"AI: {ai_comment[:100]}")

    lines.append("※ 最終判断は必ず人間が行ってください。注文は自動発生しません。")

    return "\n".join(lines)


def notify_analysis_result(result: "AnalysisResult") -> bool:  # type: ignore[name-defined]
    """分析結果を通知する。通知条件を満たさない場合は何もしない。"""
    from app.services.market_analyzer import AnalysisResult

    if not isinstance(result, AnalysisResult):
        return False

    if not should_notify(result.signal, result.score):
        logger.debug("通知条件未満のため送信スキップ: signal=%s score=%s", result.signal, result.score)
        return False

    message = build_notification_message(
        symbol=result.symbol,
        signal=result.signal,
        signal_label=result.signal_label,
        current_price=result.current_price,
        score=result.score,
        rsi=result.rsi,
        entry_price=result.entry_price,
        stop_loss=result.stop_loss,
        take_profit=result.take_profit,
        risk_reward=result.risk_reward,
        ai_comment=result.ai_comment,
        is_dummy_data=result.is_dummy_data,
    )

    adapter = get_notification_adapter()
    return adapter.send(message)
