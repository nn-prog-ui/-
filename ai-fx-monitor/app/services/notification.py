"""通知アダプターモジュール

Gmail（SMTP）を使ってBUY/SELL判定時にメールで通知する。

設定（.env）:
    EMAIL_FROM=your_gmail@gmail.com      # 送信元Gmailアドレス
    EMAIL_APP_PASSWORD=xxxx xxxx xxxx    # Gmailアプリパスワード（16文字）
    EMAIL_TO=your_gmail@gmail.com        # 送信先（自分宛でOK）
    NOTIFY_ON_BUY=true
    NOTIFY_ON_SELL=true
    NOTIFY_ON_SKIP=false
    NOTIFY_MIN_SCORE=0

Gmailアプリパスワード取得手順:
    1. Googleアカウント → セキュリティ → 2段階認証をONにする
    2. セキュリティ → 「アプリパスワード」を検索
    3. アプリ名を入力（例: FX通知）→ 作成
    4. 表示された16文字をEMAIL_APP_PASSWORDに設定
"""
from __future__ import annotations

import logging
import os
import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


class NotificationError(Exception):
    pass


class NotificationAdapter(ABC):
    @abstractmethod
    def send(self, message: str) -> bool:
        raise NotImplementedError


class GmailAdapter(NotificationAdapter):
    """Gmail SMTPアダプター。"""

    def __init__(self, from_addr: str, app_password: str, to_addr: str):
        if not from_addr:
            raise NotificationError("EMAIL_FROM が設定されていません。")
        if not app_password:
            raise NotificationError("EMAIL_APP_PASSWORD が設定されていません。")
        if not to_addr:
            raise NotificationError("EMAIL_TO が設定されていません。")
        self._from = from_addr
        self._password = app_password
        self._to = to_addr

    @classmethod
    def from_env(cls) -> "GmailAdapter":
        from_addr = os.getenv("EMAIL_FROM", "")
        app_password = os.getenv("EMAIL_APP_PASSWORD", "")
        to_addr = os.getenv("EMAIL_TO", "")
        if not from_addr:
            raise NotificationError("EMAIL_FROM が .env に設定されていません。")
        if not app_password:
            raise NotificationError("EMAIL_APP_PASSWORD が .env に設定されていません。")
        if not to_addr:
            raise NotificationError("EMAIL_TO が .env に設定されていません。")
        return cls(from_addr, app_password, to_addr)

    def send(self, message: str) -> bool:
        subject = self._make_subject(message)
        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = self._to

        try:
            with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self._from, self._password)
                smtp.sendmail(self._from, self._to, msg.as_string())
            logger.info("メール通知送信成功: %s → %s", self._from, self._to)
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("Gmailログイン失敗: アプリパスワードを確認してください")
            return False
        except Exception as exc:
            logger.error("メール送信エラー: %s", exc)
            return False

    @staticmethod
    def _make_subject(message: str) -> str:
        first_line = message.strip().split("\n")[0]
        return first_line[:50]


class LogOnlyAdapter(NotificationAdapter):
    """通知設定未設定時のフォールバック（ログ出力のみ）。"""

    def send(self, message: str) -> bool:
        logger.info("[通知（未送信）] %s", message)
        return True


def get_notification_adapter() -> NotificationAdapter:
    """設定に応じた通知アダプターを返す。未設定時はLogOnlyAdapter。"""
    from_addr = os.getenv("EMAIL_FROM", "")
    app_password = os.getenv("EMAIL_APP_PASSWORD", "")
    to_addr = os.getenv("EMAIL_TO", "")
    if from_addr and app_password and to_addr:
        return GmailAdapter(from_addr, app_password, to_addr)
    logger.debug("Email未設定 → 通知はログ出力のみ")
    return LogOnlyAdapter()


def should_notify(signal: str, score: int | None) -> bool:
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
    lines = [f"【AI FX市場監視】{symbol} {signal_label}"]

    if is_dummy_data:
        lines.append("※ テストデータ使用中")

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
        lines.append(f"AI: {ai_comment[:100]}")

    lines.append("※ 最終判断は必ず人間が行ってください。注文は自動発生しません。")
    return "\n".join(lines)


def notify_analysis_result(result: "AnalysisResult") -> bool:  # type: ignore[name-defined]
    from app.services.market_analyzer import AnalysisResult

    if not isinstance(result, AnalysisResult):
        return False
    if not should_notify(result.signal, result.score):
        logger.debug("通知条件未満のためスキップ: signal=%s score=%s", result.signal, result.score)
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
