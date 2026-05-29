"""Phase 87: Claude API 実接続 テスト"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


# ── /api/test-claude エンドポイントテスト ────────────────────────────────────

class TestClaudeTestEndpoint:
    def test_no_api_key_returns_error(self):
        """/api/test-claude: APIキー未設定は ok=False を返す"""
        with patch.dict(os.environ, {}, clear=False):
            env = {k: v for k, v in os.environ.items()
                   if k != "ANTHROPIC_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                resp = client.post("/api/test-claude")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "ANTHROPIC_API_KEY" in data.get("error", "") or "ANTHROPIC" in data.get("help", "")

    def test_no_api_key_has_help_message(self):
        """/api/test-claude: APIキー未設定時にセットアップのヒントが含まれる"""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            resp = client.post("/api/test-claude")
        data = resp.json()
        assert data["ok"] is False
        # ヒントメッセージが何かあること
        assert data.get("help") or data.get("error")

    def test_with_api_key_calls_anthropic(self):
        """/api/test-claude: APIキーがある場合 anthropic.Anthropic を呼ぶ"""
        mock_content = MagicMock()
        mock_content.text = "OK"
        mock_resp = MagicMock()
        mock_resp.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                resp = client.post("/api/test-claude")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["source"] == "claude"
        assert data["reply"] == "OK"

    def test_with_api_key_returns_model_info(self):
        """接続成功時にモデル名が返る"""
        mock_content = MagicMock()
        mock_content.text = "OK"
        mock_resp = MagicMock()
        mock_resp.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key",
                                      "CLAUDE_MODEL": "claude-haiku-4-5"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                resp = client.post("/api/test-claude")

        data = resp.json()
        assert data.get("model") == "claude-haiku-4-5"

    def test_api_error_returns_ok_false(self):
        """anthropic が例外を投げた場合は ok=False"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-bad-key"}):
            with patch("anthropic.Anthropic", side_effect=Exception("Auth error")):
                resp = client.post("/api/test-claude")

        data = resp.json()
        assert data["ok"] is False
        assert data["source"] == "claude"
        assert "Auth error" in data.get("error", "")

    def test_api_error_has_help_message(self):
        """接続失敗時にもヒントメッセージがある"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-bad-key"}):
            with patch("anthropic.Anthropic", side_effect=Exception("Auth error")):
                resp = client.post("/api/test-claude")

        data = resp.json()
        assert data.get("help")

    def test_endpoint_method_is_post(self):
        """/api/test-claude は GET では 405 Method Not Allowed"""
        resp = client.get("/api/test-claude")
        assert resp.status_code == 405


# ── ai_source がindex ページに渡されるテスト ─────────────────────────────────

class TestAiSourceInIndex:
    def test_index_returns_ok(self):
        """index ページが 200 を返す"""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_contains_ai_comment_section(self):
        """index ページに AIコメントカードが含まれる"""
        resp = client.get("/")
        assert "AIによる補足コメント" in resp.text

    def test_index_shows_mock_source_when_no_key(self):
        """APIキー未設定時に ルールベース自動生成 バッジが表示される"""
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            resp = client.get("/")
        # バッジテキストまたはソース情報が含まれる
        assert "ルールベース自動生成" in resp.text or "ai-source-mock" in resp.text

    def test_index_shows_claude_badge_when_key_set(self):
        """APIキー設定時に Claude AI バッジが表示される"""
        mock_content = MagicMock()
        mock_content.text = "テスト"
        mock_resp_obj = MagicMock()
        mock_resp_obj.content = [mock_content]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp_obj

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("anthropic.Anthropic", return_value=mock_client):
                resp = client.get("/")

        assert "Claude AI" in resp.text or "ai-source-claude" in resp.text


# ── ai_commentary.py の ClaudeCommentaryAdapter 単体テスト ──────────────────

class TestClaudeCommentaryAdapter:
    def test_adapter_calls_anthropic_when_key_set(self):
        """ClaudeCommentaryAdapter が anthropic.Anthropic を呼ぶ"""
        from app.services.ai_commentary import ClaudeCommentaryAdapter
        from tests.test_ai_commentary_phase86 import _make_signal_result

        mock_content = MagicMock()
        mock_content.text = "テスト AIコメントです。"
        mock_resp = MagicMock()
        mock_resp.content = [mock_content]
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_resp

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("anthropic.Anthropic", return_value=mock_client_instance):
                adapter = ClaudeCommentaryAdapter()
                result = _make_signal_result("BUY")
                comment = adapter.generate(result, None, None)

        assert "テスト AIコメントです。" in comment
        assert mock_client_instance.messages.create.called

    def test_adapter_falls_back_on_error(self):
        """API エラー時はモックコメントにフォールバックする"""
        from app.services.ai_commentary import ClaudeCommentaryAdapter
        from tests.test_ai_commentary_phase86 import _make_signal_result

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.side_effect = Exception("rate limit")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("anthropic.Anthropic", return_value=mock_client_instance):
                adapter = ClaudeCommentaryAdapter()
                result = _make_signal_result("BUY")
                comment = adapter.generate(result, None, None)

        # フォールバックでも何かコメントが返る
        assert isinstance(comment, str)
        assert len(comment) > 0

    def test_adapter_data_insufficient_returns_early(self):
        """データ不足時は API を呼ばずに早期リターンする"""
        from app.services.ai_commentary import ClaudeCommentaryAdapter
        from tests.test_ai_commentary_phase86 import _make_signal_result
        import dataclasses

        mock_client_instance = MagicMock()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("anthropic.Anthropic", return_value=mock_client_instance):
                adapter = ClaudeCommentaryAdapter()
                result = _make_signal_result("SKIP")
                # data_sufficient=False にする
                result = dataclasses.replace(result, data_sufficient=False)
                comment = adapter.generate(result, None, None)

        assert "データが不足" in comment
        assert not mock_client_instance.messages.create.called

    def test_adapter_passes_patterns_to_prompt(self):
        """ローソク足パターンがプロンプトに含まれる"""
        from app.indicators.candlestick_patterns import CandlePattern
        from app.services.ai_commentary import ClaudeCommentaryAdapter
        from tests.test_ai_commentary_phase86 import _make_signal_result

        captured_prompt = []

        def mock_create(**kwargs):
            msg = kwargs.get("messages", [])
            if msg:
                captured_prompt.append(msg[0].get("content", ""))
            mock_content = MagicMock()
            mock_content.text = "コメント"
            mock_resp = MagicMock()
            mock_resp.content = [mock_content]
            return mock_resp

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.side_effect = mock_create

        pattern = CandlePattern("下影陽線", "Hammer", "bullish", 2, "説明")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("anthropic.Anthropic", return_value=mock_client_instance):
                adapter = ClaudeCommentaryAdapter()
                result = _make_signal_result("BUY")
                adapter.generate(result, None, None, candlestick_patterns=[pattern])

        # プロンプトにパターン名が含まれているはず
        assert any("下影陽線" in p for p in captured_prompt)


# ── settings ページのテスト ──────────────────────────────────────────────────

class TestSettingsPage:
    def test_settings_page_loads(self):
        """/settings が 200 を返す"""
        resp = client.get("/settings")
        assert resp.status_code == 200

    def test_settings_shows_claude_section(self):
        """/settings に Claude AI の設定セクションがある"""
        resp = client.get("/settings")
        assert "Claude AI" in resp.text or "ANTHROPIC_API_KEY" in resp.text

    def test_settings_shows_test_button(self):
        """/settings に接続テストボタンがある"""
        resp = client.get("/settings")
        assert "接続テスト" in resp.text or "claude-test-btn" in resp.text

    def test_settings_shows_setup_help_when_no_key(self):
        """/settings: APIキー未設定時にセットアップ手順が表示される"""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            resp = client.get("/settings")
        # セットアップ手順のテキストが含まれること
        assert "console.anthropic.com" in resp.text or "APIキー" in resp.text
