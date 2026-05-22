"""Phase 71: 地政学リスクアラート通知 テスト"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.geo_alert import (
    ALERT_IMPACTS,
    build_geo_alert_message,
    send_geo_alert,
    should_geo_alert,
)
from app.scripts.geopolitical import GeopoliticalAnalysis


# ── フィクスチャ ──────────────────────────────────────────────────────────

def _make_analysis(usd_impact: str = "strong_bullish") -> GeopoliticalAnalysis:
    return GeopoliticalAnalysis(
        event_text="FRBが0.5%の大幅利上げを決定した。市場は急激なドル高で反応。",
        category="FRB金融政策（利上げ・利下げ・QE）",
        usd_impact=usd_impact,
        confidence="high",
        reasoning="大幅利上げはドル資産の魅力を高め、強いドル買い圧力になる。",
        similar_events=["2022年FRB 0.75%利上げでドル円急騰"],
        short_term_outlook="短期的にドル円は上昇圧力が続く可能性が高い。",
        risk_factors="景気後退懸念が高まれば利下げ転換リスクがある。",
        ai_provider="mock",
    )


# ── ALERT_IMPACTS 定数テスト ──────────────────────────────────────────────

class TestAlertImpacts:
    def test_strong_bullish_in_alert_impacts(self):
        assert "strong_bullish" in ALERT_IMPACTS

    def test_strong_bearish_in_alert_impacts(self):
        assert "strong_bearish" in ALERT_IMPACTS

    def test_bullish_not_in_alert_impacts(self):
        assert "bullish" not in ALERT_IMPACTS

    def test_bearish_not_in_alert_impacts(self):
        assert "bearish" not in ALERT_IMPACTS

    def test_neutral_not_in_alert_impacts(self):
        assert "neutral" not in ALERT_IMPACTS


# ── should_geo_alert テスト ───────────────────────────────────────────────

class TestShouldGeoAlert:
    def test_strong_bullish_returns_true(self):
        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}):
            assert should_geo_alert("strong_bullish") is True

    def test_strong_bearish_returns_true(self):
        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}):
            assert should_geo_alert("strong_bearish") is True

    def test_bullish_returns_false(self):
        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}):
            assert should_geo_alert("bullish") is False

    def test_bearish_returns_false(self):
        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}):
            assert should_geo_alert("bearish") is False

    def test_neutral_returns_false(self):
        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}):
            assert should_geo_alert("neutral") is False

    def test_disabled_by_env_strong_bullish(self):
        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "false"}):
            assert should_geo_alert("strong_bullish") is False

    def test_disabled_by_env_strong_bearish(self):
        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "false"}):
            assert should_geo_alert("strong_bearish") is False

    def test_default_enabled(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "NOTIFY_GEO_ALERT"}
        with patch.dict("os.environ", env, clear=True):
            assert should_geo_alert("strong_bullish") is True


# ── build_geo_alert_message テスト ───────────────────────────────────────

class TestBuildGeoAlertMessage:
    def test_strong_bullish_label_in_message(self):
        analysis = _make_analysis("strong_bullish")
        msg = build_geo_alert_message(analysis)
        assert "強いドル高" in msg

    def test_strong_bearish_label_in_message(self):
        analysis = _make_analysis("strong_bearish")
        analysis.usd_impact = "strong_bearish"
        msg = build_geo_alert_message(analysis)
        assert "強いドル安" in msg

    def test_category_in_message(self):
        analysis = _make_analysis()
        msg = build_geo_alert_message(analysis)
        assert "FRB金融政策" in msg

    def test_event_text_in_message(self):
        analysis = _make_analysis()
        msg = build_geo_alert_message(analysis)
        assert "FRBが0.5%の大幅利上げを決定した" in msg

    def test_reasoning_in_message(self):
        analysis = _make_analysis()
        msg = build_geo_alert_message(analysis)
        assert "大幅利上げはドル資産" in msg

    def test_safety_disclaimer_in_message(self):
        analysis = _make_analysis()
        msg = build_geo_alert_message(analysis)
        assert "自動注文は発生しません" in msg

    def test_message_is_string(self):
        analysis = _make_analysis()
        assert isinstance(build_geo_alert_message(analysis), str)

    def test_message_not_empty(self):
        analysis = _make_analysis()
        assert len(build_geo_alert_message(analysis)) > 50

    def test_ai_provider_in_message(self):
        analysis = _make_analysis()
        msg = build_geo_alert_message(analysis)
        assert "mock" in msg


# ── send_geo_alert テスト ─────────────────────────────────────────────────

class TestSendGeoAlert:
    def test_strong_bullish_sends_notification(self):
        analysis = _make_analysis("strong_bullish")
        mock_adapter = MagicMock()
        mock_adapter.send.return_value = True

        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}), \
             patch("app.services.notification.get_notification_adapter", return_value=mock_adapter):
            result = send_geo_alert(analysis)

        assert result is True
        mock_adapter.send.assert_called_once()

    def test_strong_bearish_sends_notification(self):
        analysis = _make_analysis("strong_bearish")
        mock_adapter = MagicMock()
        mock_adapter.send.return_value = True

        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}), \
             patch("app.services.notification.get_notification_adapter", return_value=mock_adapter):
            result = send_geo_alert(analysis)

        assert result is True
        mock_adapter.send.assert_called_once()

    def test_bullish_skips_notification(self):
        analysis = _make_analysis("bullish")
        mock_adapter = MagicMock()

        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}), \
             patch("app.services.notification.get_notification_adapter", return_value=mock_adapter):
            result = send_geo_alert(analysis)

        assert result is False
        mock_adapter.send.assert_not_called()

    def test_neutral_skips_notification(self):
        analysis = _make_analysis("neutral")
        mock_adapter = MagicMock()

        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}), \
             patch("app.services.notification.get_notification_adapter", return_value=mock_adapter):
            result = send_geo_alert(analysis)

        assert result is False
        mock_adapter.send.assert_not_called()

    def test_disabled_env_skips_notification(self):
        analysis = _make_analysis("strong_bullish")
        mock_adapter = MagicMock()

        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "false"}), \
             patch("app.services.notification.get_notification_adapter", return_value=mock_adapter):
            result = send_geo_alert(analysis)

        assert result is False
        mock_adapter.send.assert_not_called()

    def test_adapter_exception_returns_false(self):
        analysis = _make_analysis("strong_bullish")

        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}), \
             patch("app.services.notification.get_notification_adapter", side_effect=RuntimeError("SMTP error")):
            result = send_geo_alert(analysis)

        assert result is False

    def test_message_passed_to_adapter(self):
        analysis = _make_analysis("strong_bullish")
        mock_adapter = MagicMock()
        mock_adapter.send.return_value = True

        with patch.dict("os.environ", {"NOTIFY_GEO_ALERT": "true"}), \
             patch("app.services.notification.get_notification_adapter", return_value=mock_adapter):
            send_geo_alert(analysis)

        sent_msg = mock_adapter.send.call_args[0][0]
        assert "地政学アラート" in sent_msg
        assert "強いドル高" in sent_msg


# ── analyze_and_save 統合テスト（アラートトリガー確認） ───────────────────

class TestAnalyzeAndSaveAlertIntegration:
    def test_strong_bullish_triggers_alert(self, tmp_path):
        """analyze_and_save() が strong_bullish 結果でアラートを呼ぶ"""
        from app.scripts.geopolitical import analyze_and_save, ensure_table

        db = tmp_path / "geo.db"
        ensure_table(db)

        mock_adapter = MagicMock()
        mock_adapter.send.return_value = True

        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "NOTIFY_GEO_ALERT": "true"
        }), patch("app.services.notification.get_notification_adapter", return_value=mock_adapter):
            # FRB利上げは strong_bullish にマッチしやすい
            analysis, record_id = analyze_and_save("FRBが0.5%の大幅利上げを決定", "2026-05-23", db)

        assert record_id > 0
        # strong_bullish の場合のみアダプターが呼ばれる
        if analysis.usd_impact in ("strong_bullish", "strong_bearish"):
            mock_adapter.send.assert_called_once()

    def test_neutral_does_not_trigger_alert(self, tmp_path):
        """analyze_and_save() が neutral 結果ではアラートを呼ばない"""
        from app.scripts.geopolitical import analyze_and_save, ensure_table

        db = tmp_path / "geo.db"
        ensure_table(db)

        mock_adapter = MagicMock()

        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "NOTIFY_GEO_ALERT": "true"
        }), patch("app.services.notification.get_notification_adapter", return_value=mock_adapter):
            analysis, _ = analyze_and_save("よくわからない何かが起きた", "2026-05-23", db)

        if analysis.usd_impact not in ("strong_bullish", "strong_bearish"):
            mock_adapter.send.assert_not_called()
