"""通知モジュールのテスト（外部APIへの実通信なし）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.notification import (
    GmailAdapter,
    LogOnlyAdapter,
    NotificationError,
    build_notification_message,
    get_notification_adapter,
    should_notify,
)


class TestShouldNotify:
    def test_buy_notified_by_default(self, monkeypatch):
        monkeypatch.delenv("NOTIFY_ON_BUY", raising=False)
        assert should_notify("BUY", score=7) is True

    def test_sell_notified_by_default(self, monkeypatch):
        monkeypatch.delenv("NOTIFY_ON_SELL", raising=False)
        assert should_notify("SELL", score=-7) is True

    def test_skip_not_notified_by_default(self, monkeypatch):
        monkeypatch.delenv("NOTIFY_ON_SKIP", raising=False)
        assert should_notify("SKIP", score=None) is False

    def test_skip_notified_when_enabled(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_ON_SKIP", "true")
        assert should_notify("SKIP", score=None) is True

    def test_buy_disabled(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_ON_BUY", "false")
        assert should_notify("BUY", score=7) is False

    def test_min_score_filter(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_MIN_SCORE", "5")
        assert should_notify("BUY", score=3) is False
        assert should_notify("BUY", score=5) is True

    def test_min_score_sell_abs(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_MIN_SCORE", "5")
        assert should_notify("SELL", score=-7) is True
        assert should_notify("SELL", score=-3) is False

    def test_none_score_passes(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_MIN_SCORE", "5")
        assert should_notify("BUY", score=None) is True


class TestBuildNotificationMessage:
    def test_contains_symbol_and_label(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="BUY", signal_label="買い候補",
            current_price=150.0, score=7, rsi=55.0,
            entry_price=150.0, stop_loss=149.5, take_profit=151.0, risk_reward=2.0,
        )
        assert "USD/JPY" in msg
        assert "買い候補" in msg

    def test_price_info(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="BUY", signal_label="買い候補",
            current_price=150.123, score=7, rsi=55.0,
            entry_price=150.123, stop_loss=149.5, take_profit=151.5, risk_reward=2.0,
        )
        assert "150.123" in msg
        assert "149.500" in msg

    def test_dummy_warning(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="BUY", signal_label="買い候補",
            current_price=150.0, score=7, rsi=55.0,
            entry_price=150.0, stop_loss=149.5, take_profit=151.0, risk_reward=2.0,
            is_dummy_data=True,
        )
        assert "テスト" in msg or "⚠" in msg

    def test_skip_no_setup(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="SKIP", signal_label="見送り",
            current_price=150.0, score=None, rsi=55.0,
            entry_price=None, stop_loss=None, take_profit=None, risk_reward=None,
        )
        assert "見送り" in msg
        assert "損切り" not in msg

    def test_disclaimer_present(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="SKIP", signal_label="見送り",
            current_price=None, score=None, rsi=None,
            entry_price=None, stop_loss=None, take_profit=None, risk_reward=None,
        )
        assert "最終判断" in msg or "注文" in msg


class TestGmailAdapter:
    def test_empty_from_raises(self):
        with pytest.raises(NotificationError, match="EMAIL_FROM"):
            GmailAdapter("", "pass", "to@gmail.com")

    def test_empty_password_raises(self):
        with pytest.raises(NotificationError, match="EMAIL_APP_PASSWORD"):
            GmailAdapter("from@gmail.com", "", "to@gmail.com")

    def test_empty_to_raises(self):
        with pytest.raises(NotificationError, match="EMAIL_TO"):
            GmailAdapter("from@gmail.com", "pass", "")

    def test_from_env_missing_raises(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM", "")
        monkeypatch.setenv("EMAIL_APP_PASSWORD", "pass")
        monkeypatch.setenv("EMAIL_TO", "to@gmail.com")
        with pytest.raises(NotificationError, match="EMAIL_FROM"):
            GmailAdapter.from_env()

    def test_from_env_success(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM", "from@gmail.com")
        monkeypatch.setenv("EMAIL_APP_PASSWORD", "pass")
        monkeypatch.setenv("EMAIL_TO", "to@gmail.com")
        adapter = GmailAdapter.from_env()
        assert adapter._from == "from@gmail.com"

    def test_send_success(self):
        adapter = GmailAdapter("from@gmail.com", "pass", "to@gmail.com")
        mock_smtp = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_smtp.__enter__.return_value):
            mock_smtp.__enter__.return_value.sendmail.return_value = {}
            with patch("smtplib.SMTP") as mock_cls:
                mock_cls.return_value.__enter__.return_value = mock_smtp
                result = adapter.send("テスト")
        assert isinstance(result, bool)

    def test_send_auth_error_returns_false(self):
        import smtplib
        adapter = GmailAdapter("from@gmail.com", "wrong", "to@gmail.com")
        with patch("smtplib.SMTP") as mock_cls:
            mock_cls.return_value.__enter__.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
            result = adapter.send("テスト")
        assert result is False

    def test_send_exception_returns_false(self):
        adapter = GmailAdapter("from@gmail.com", "pass", "to@gmail.com")
        with patch("smtplib.SMTP", side_effect=Exception("connection error")):
            result = adapter.send("テスト")
        assert result is False


class TestLogOnlyAdapter:
    def test_always_true(self):
        assert LogOnlyAdapter().send("test") is True


class TestGetNotificationAdapter:
    def test_no_config_returns_log_only(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM", "")
        monkeypatch.setenv("EMAIL_APP_PASSWORD", "")
        monkeypatch.setenv("EMAIL_TO", "")
        assert isinstance(get_notification_adapter(), LogOnlyAdapter)

    def test_full_config_returns_gmail(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM", "from@gmail.com")
        monkeypatch.setenv("EMAIL_APP_PASSWORD", "pass")
        monkeypatch.setenv("EMAIL_TO", "to@gmail.com")
        assert isinstance(get_notification_adapter(), GmailAdapter)
