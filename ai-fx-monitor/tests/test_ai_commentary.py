"""AIコメント生成モジュールのテスト"""
from unittest.mock import MagicMock, patch

import pytest

from app.services.ai_commentary import (
    MockCommentaryAdapter,
    OpenAICommentaryAdapter,
    _build_signal_prompt,
    _sanitize_commentary,
    generate_commentary,
)
from app.strategy.rules import SignalResult
from app.strategy.risk import TradeSetup


def make_signal_result(
    signal="BUY",
    daily_trend="上昇",
    h4_trend="上昇",
    h1_status="高値突破",
    rsi=55.0,
    atr_abnormal=False,
    data_sufficient=True,
    skip_reasons=None,
) -> SignalResult:
    return SignalResult(
        signal=signal,
        score=None,
        daily_trend=daily_trend,
        h4_trend=h4_trend,
        h1_status=h1_status,
        rsi=rsi,
        atr_abnormal=atr_abnormal,
        data_sufficient=data_sufficient,
        skip_reasons=skip_reasons or [],
        recent_high=151.0,
        recent_low=149.0,
    )


def make_setup(entry=150.5, stop=149.8, tp=151.9) -> TradeSetup:
    return TradeSetup(
        entry_price=entry,
        stop_loss=stop,
        take_profit=tp,
        risk_reward=round((tp - entry) / (entry - stop), 2),
        is_valid=True,
        invalid_reason=None,
    )


class TestSanitize:
    def test_clean_comment_unchanged(self):
        assert _sanitize_commentary("問題のないコメントです。") == "問題のないコメントです。"

    def test_forbidden_word_replaced(self):
        result = _sanitize_commentary("今すぐ全力で買いましょう。")
        assert "今すぐ全力" not in result
        assert "（表現を削除しました）" in result

    def test_multiple_forbidden_words(self):
        result = _sanitize_commentary("儲かる！勝率100%！")
        assert "儲かる" not in result
        assert "勝率100%" not in result


class TestBuildSignalPrompt:
    def test_contains_signal(self):
        result = make_signal_result(signal="BUY")
        prompt = _build_signal_prompt(result, None)
        assert "【判定】BUY" in prompt

    def test_contains_rsi(self):
        result = make_signal_result(rsi=68.3)
        prompt = _build_signal_prompt(result, None)
        assert "【RSI】68.3" in prompt

    def test_contains_setup_prices(self):
        result = make_signal_result()
        setup = make_setup()
        prompt = _build_signal_prompt(result, setup)
        assert "【エントリー価格】" in prompt
        assert "【損切り価格】" in prompt
        assert "【利確価格】" in prompt

    def test_data_insufficient_marked(self):
        result = make_signal_result(data_sufficient=False)
        prompt = _build_signal_prompt(result, None)
        assert "【データ状態】不足" in prompt

    def test_skip_reasons_included(self):
        result = make_signal_result(signal="SKIP", skip_reasons=["経済指標発表前後60分"])
        prompt = _build_signal_prompt(result, None)
        assert "経済指標発表前後60分" in prompt


class TestMockCommentaryAdapter:
    def test_buy_signal_comment(self):
        adapter = MockCommentaryAdapter()
        result = make_signal_result(signal="BUY")
        comment = adapter.generate(result)
        assert isinstance(comment, str)
        assert len(comment) > 0
        assert "買い候補" in comment

    def test_sell_signal_comment(self):
        adapter = MockCommentaryAdapter()
        result = make_signal_result(signal="SELL", daily_trend="下降", h4_trend="下降", h1_status="安値割れ")
        comment = adapter.generate(result)
        assert "売り候補" in comment

    def test_skip_signal_comment(self):
        adapter = MockCommentaryAdapter()
        result = make_signal_result(signal="SKIP", skip_reasons=["トレンド不一致"])
        comment = adapter.generate(result)
        assert "見送り" in comment

    def test_data_insufficient(self):
        adapter = MockCommentaryAdapter()
        result = make_signal_result(data_sufficient=False)
        comment = adapter.generate(result)
        assert "データが不足" in comment

    def test_no_forbidden_words_in_output(self):
        adapter = MockCommentaryAdapter()
        for signal in ("BUY", "SELL", "SKIP"):
            result = make_signal_result(signal=signal)
            comment = adapter.generate(result)
            for word in ["絶対に勝てる", "必ず上がる", "儲かる", "勝率100%"]:
                assert word not in comment


class TestGenerateCommentaryDispatch:
    def test_uses_mock_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = make_signal_result()
        comment = generate_commentary(result)
        assert isinstance(comment, str)
        assert len(comment) > 0

    def test_uses_claude_when_api_key_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake")
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="日足・4時間足ともに上昇方向で、短期的にも高値突破が確認されています。")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("app.services.ai_commentary.ClaudeCommentaryAdapter") as mock_cls:
            mock_adapter = MagicMock()
            mock_adapter.generate.return_value = "日足・4時間足ともに上昇方向で、短期的にも高値突破が確認されています。"
            mock_cls.return_value = mock_adapter

            result = make_signal_result()
            comment = generate_commentary(result)

        assert "上昇" in comment
        mock_adapter.generate.assert_called_once()

    def test_falls_back_to_mock_on_api_error(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake")
        from app.services.ai_commentary import ClaudeCommentaryAdapter

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")

        with patch("anthropic.Anthropic", return_value=mock_client):
            adapter = ClaudeCommentaryAdapter()
            result = make_signal_result()
            comment = adapter.generate(result)

        assert isinstance(comment, str)
        assert len(comment) > 0

    def test_claude_prompt_caching_param_sent(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake")
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="補足コメントです。")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        from app.services.ai_commentary import ClaudeCommentaryAdapter
        with patch("anthropic.Anthropic", return_value=mock_client):
            adapter = ClaudeCommentaryAdapter()
            result = make_signal_result()
            adapter.generate(result)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system = call_kwargs["system"]
        assert isinstance(system, list)
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_uses_openai_when_only_openai_key_set(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fake")

        with patch("app.services.ai_commentary.OpenAICommentaryAdapter") as mock_cls:
            mock_adapter = MagicMock()
            mock_adapter.generate.return_value = "OpenAIからのコメントです。"
            mock_cls.return_value = mock_adapter

            result = make_signal_result()
            comment = generate_commentary(result)

        assert comment == "OpenAIからのコメントです。"
        mock_adapter.generate.assert_called_once()

    def test_claude_takes_priority_over_openai(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fake")

        with patch("app.services.ai_commentary.ClaudeCommentaryAdapter") as claude_cls, \
             patch("app.services.ai_commentary.OpenAICommentaryAdapter") as openai_cls:
            claude_adapter = MagicMock()
            claude_adapter.generate.return_value = "Claudeからのコメントです。"
            claude_cls.return_value = claude_adapter

            result = make_signal_result()
            comment = generate_commentary(result)

        assert comment == "Claudeからのコメントです。"
        openai_cls.assert_not_called()


class TestOpenAICommentaryAdapter:
    def test_buy_signal_returns_comment(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
        mock_choice = MagicMock()
        mock_choice.message.content = "日足・4時間足ともに上昇方向で買い候補条件が揃っています。"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            adapter = OpenAICommentaryAdapter()
            result = make_signal_result(signal="BUY")
            comment = adapter.generate(result)

        assert "上昇" in comment
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_falls_back_to_mock_on_api_error(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        with patch("openai.OpenAI", return_value=mock_client):
            adapter = OpenAICommentaryAdapter()
            result = make_signal_result()
            comment = adapter.generate(result)

        assert isinstance(comment, str)
        assert len(comment) > 0

    def test_data_insufficient_returns_early(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
        mock_client = MagicMock()

        with patch("openai.OpenAI", return_value=mock_client):
            adapter = OpenAICommentaryAdapter()
            result = make_signal_result(data_sufficient=False)
            comment = adapter.generate(result)

        assert "データが不足" in comment
        mock_client.chat.completions.create.assert_not_called()

    def test_forbidden_words_sanitized(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
        mock_choice = MagicMock()
        mock_choice.message.content = "儲かる！今すぐ全力で買いましょう。"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            adapter = OpenAICommentaryAdapter()
            result = make_signal_result(signal="BUY")
            comment = adapter.generate(result)

        assert "儲かる" not in comment
        assert "今すぐ全力" not in comment
