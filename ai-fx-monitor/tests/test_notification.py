"""通知モジュールのテスト（外部APIへの実通信なし・モック使用）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.notification import (
    LineMessagingAdapter,
    LogOnlyAdapter,
    NotificationError,
    build_notification_message,
    get_notification_adapter,
    should_notify,
)


class TestShouldNotify:
    def test_buy_signal_notified_by_default(self, monkeypatch):
        monkeypatch.delenv("NOTIFY_ON_BUY", raising=False)
        assert should_notify("BUY", score=7) is True

    def test_sell_signal_notified_by_default(self, monkeypatch):
        monkeypatch.delenv("NOTIFY_ON_SELL", raising=False)
        assert should_notify("SELL", score=-7) is True

    def test_skip_signal_not_notified_by_default(self, monkeypatch):
        monkeypatch.delenv("NOTIFY_ON_SKIP", raising=False)
        assert should_notify("SKIP", score=None) is False

    def test_skip_notified_when_enabled(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_ON_SKIP", "true")
        assert should_notify("SKIP", score=None) is True

    def test_buy_not_notified_when_disabled(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_ON_BUY", "false")
        assert should_notify("BUY", score=7) is False

    def test_min_score_filter(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_MIN_SCORE", "5")
        assert should_notify("BUY", score=3) is False
        assert should_notify("BUY", score=5) is True
        assert should_notify("BUY", score=7) is True

    def test_min_score_sell_uses_abs(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_MIN_SCORE", "5")
        assert should_notify("SELL", score=-7) is True
        assert should_notify("SELL", score=-3) is False

    def test_none_score_passes_min_score(self, monkeypatch):
        monkeypatch.setenv("NOTIFY_MIN_SCORE", "5")
        assert should_notify("BUY", score=None) is True


class TestBuildNotificationMessage:
    def test_contains_symbol(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="BUY", signal_label="買い候補",
            current_price=150.0, score=7, rsi=55.0,
            entry_price=150.0, stop_loss=149.5, take_profit=151.0, risk_reward=2.0,
        )
        assert "USD/JPY" in msg
        assert "買い候補" in msg

    def test_contains_price_info(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="BUY", signal_label="買い候補",
            current_price=150.123, score=7, rsi=55.0,
            entry_price=150.123, stop_loss=149.5, take_profit=151.5, risk_reward=2.0,
        )
        assert "150.123" in msg
        assert "149.500" in msg
        assert "151.500" in msg

    def test_dummy_data_warning_shown(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="BUY", signal_label="買い候補",
            current_price=150.0, score=7, rsi=55.0,
            entry_price=150.0, stop_loss=149.5, take_profit=151.0, risk_reward=2.0,
            is_dummy_data=True,
        )
        assert "テスト" in msg or "ダミー" in msg or "⚠" in msg

    def test_skip_signal_no_price_setup(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="SKIP", signal_label="見送り",
            current_price=150.0, score=None, rsi=55.0,
            entry_price=None, stop_loss=None, take_profit=None, risk_reward=None,
        )
        assert "見送り" in msg
        assert "損切り" not in msg

    def test_disclaimer_always_present(self):
        msg = build_notification_message(
            symbol="USD/JPY", signal="SKIP", signal_label="見送り",
            current_price=None, score=None, rsi=None,
            entry_price=None, stop_loss=None, take_profit=None, risk_reward=None,
        )
        assert "最終判断" in msg or "注文" in msg


class TestLineMessagingAdapter:
    def test_empty_token_raises(self):
        with pytest.raises(NotificationError, match="LINE_CHANNEL_TOKEN"):
            LineMessagingAdapter("", "U123456")

    def test_empty_user_id_raises(self):
        with pytest.raises(NotificationError, match="LINE_USER_ID"):
            LineMessagingAdapter("token123", "")

    def test_from_env_missing_token_raises(self, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_TOKEN", "")
        monkeypatch.setenv("LINE_USER_ID", "U123456")
        with pytest.raises(NotificationError, match="LINE_CHANNEL_TOKEN"):
            LineMessagingAdapter.from_env()

    def test_from_env_missing_user_id_raises(self, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_TOKEN", "token123")
        monkeypatch.setenv("LINE_USER_ID", "")
        with pytest.raises(NotificationError, match="LINE_USER_ID"):
            LineMessagingAdapter.from_env()

    def test_from_env_with_values(self, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_TOKEN", "token123")
        monkeypatch.setenv("LINE_USER_ID", "U123456")
        adapter = LineMessagingAdapter.from_env()
        assert adapter._channel_token == "token123"
        assert adapter._user_id == "U123456"

    def test_send_success(self):
        adapter = LineMessagingAdapter("token123", "U123456")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.post", return_value=mock_resp):
            result = adapter.send("テストメッセージ")
        assert result is True

    def test_send_failure_status(self):
        adapter = LineMessagingAdapter("token123", "U123456")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        with patch("requests.post", return_value=mock_resp):
            result = adapter.send("テストメッセージ")
        assert result is False

    def test_send_exception_returns_false(self):
        adapter = LineMessagingAdapter("token123", "U123456")
        with patch("requests.post", side_effect=Exception("Connection error")):
            result = adapter.send("テストメッセージ")
        assert result is False

    def test_send_calls_push_api(self):
        adapter = LineMessagingAdapter("my_token", "U999")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.post", return_value=mock_resp) as mock_post:
            adapter.send("hello")
        call_args = mock_post.call_args
        assert "api.line.me" in call_args[0][0]
        assert "Bearer my_token" in call_args[1]["headers"]["Authorization"]
        assert call_args[1]["json"]["to"] == "U999"
        assert call_args[1]["json"]["messages"][0]["type"] == "text"


class TestLogOnlyAdapter:
    def test_always_returns_true(self):
        adapter = LogOnlyAdapter()
        assert adapter.send("test") is True


class TestGetNotificationAdapter:
    def test_no_token_returns_log_only(self, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_TOKEN", "")
        monkeypatch.setenv("LINE_USER_ID", "")
        adapter = get_notification_adapter()
        assert isinstance(adapter, LogOnlyAdapter)

    def test_only_token_no_user_id_returns_log_only(self, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_TOKEN", "token123")
        monkeypatch.setenv("LINE_USER_ID", "")
        adapter = get_notification_adapter()
        assert isinstance(adapter, LogOnlyAdapter)

    def test_both_set_returns_line_adapter(self, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_TOKEN", "token123")
        monkeypatch.setenv("LINE_USER_ID", "U123456")
        adapter = get_notification_adapter()
        assert isinstance(adapter, LineMessagingAdapter)
