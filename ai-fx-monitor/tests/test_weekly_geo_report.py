"""Phase 70: 週次レポートへの地政学サマリー統合 テスト"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from app.scripts.weekly_report import (
    WeeklyMetrics,
    _build_weekly_prompt,
    _generate_mock_narrative,
    _summarize_geo_risk,
    week_bounds,
)


# ── _summarize_geo_risk テスト ────────────────────────────────────────────

class TestSummarizeGeoRisk:
    def test_empty_returns_empty_string(self):
        assert _summarize_geo_risk([]) == ""

    def test_all_bullish(self):
        events = [
            {"usd_impact": "bullish"},
            {"usd_impact": "strong_bullish"},
        ]
        result = _summarize_geo_risk(events)
        assert "ドル高バイアス 2件" in result

    def test_all_bearish(self):
        events = [
            {"usd_impact": "bearish"},
            {"usd_impact": "strong_bearish"},
        ]
        result = _summarize_geo_risk(events)
        assert "ドル安バイアス 2件" in result

    def test_neutral_only(self):
        events = [{"usd_impact": "neutral"}]
        result = _summarize_geo_risk(events)
        assert "中立 1件" in result

    def test_mixed_impacts(self):
        events = [
            {"usd_impact": "bullish"},
            {"usd_impact": "bearish"},
            {"usd_impact": "neutral"},
        ]
        result = _summarize_geo_risk(events)
        assert "ドル高バイアス 1件" in result
        assert "ドル安バイアス 1件" in result
        assert "中立 1件" in result

    def test_result_is_string(self):
        events = [{"usd_impact": "bullish"}]
        assert isinstance(_summarize_geo_risk(events), str)

    def test_separator_slash(self):
        events = [
            {"usd_impact": "bullish"},
            {"usd_impact": "bearish"},
        ]
        result = _summarize_geo_risk(events)
        assert " / " in result


# ── WeeklyMetrics 地政学フィールド テスト ─────────────────────────────────

class TestWeeklyMetricsGeoFields:
    def test_geo_events_default_empty_list(self):
        m = WeeklyMetrics(
            week_label="2026-W21",
            week_start="2026-05-18",
            week_end="2026-05-24",
            symbol="",
        )
        assert m.geo_events == []

    def test_geo_risk_summary_default_empty_string(self):
        m = WeeklyMetrics(
            week_label="2026-W21",
            week_start="2026-05-18",
            week_end="2026-05-24",
            symbol="",
        )
        assert m.geo_risk_summary == ""

    def test_can_set_geo_events(self):
        m = WeeklyMetrics(
            week_label="2026-W21",
            week_start="2026-05-18",
            week_end="2026-05-24",
            symbol="",
            geo_events=[
                {"date": "2026-05-20", "category": "FRB金融政策", "usd_impact": "bullish", "event_text": "FRB利上げ"}
            ],
            geo_risk_summary="ドル高バイアス 1件",
        )
        assert len(m.geo_events) == 1
        assert m.geo_risk_summary == "ドル高バイアス 1件"


# ── _build_weekly_prompt 地政学セクション テスト ──────────────────────────

class TestBuildWeeklyPromptGeo:
    def _make_metrics(self, geo_events=None, geo_risk_summary="") -> WeeklyMetrics:
        return WeeklyMetrics(
            week_label="2026-W21",
            week_start="2026-05-18",
            week_end="2026-05-24",
            symbol="",
            geo_events=geo_events or [],
            geo_risk_summary=geo_risk_summary,
        )

    def test_no_geo_events_no_geo_section(self):
        m = self._make_metrics()
        prompt = _build_weekly_prompt(m)
        assert "地政学" not in prompt

    def test_geo_events_added_to_prompt(self):
        m = self._make_metrics(
            geo_events=[
                {
                    "date": "2026-05-20",
                    "category": "FRB金融政策（利上げ・利下げ・QE）",
                    "usd_impact": "bullish",
                    "event_text": "FRBが利上げを決定した",
                }
            ],
            geo_risk_summary="ドル高バイアス 1件",
        )
        prompt = _build_weekly_prompt(m)
        assert "地政学リスク分析" in prompt
        assert "FRBが利上げを決定した" in prompt
        assert "ドル高" in prompt

    def test_geo_summary_in_prompt(self):
        m = self._make_metrics(
            geo_events=[{"date": "2026-05-20", "category": "日銀金融政策",
                         "usd_impact": "bearish", "event_text": "日銀が利上げを示唆"}],
            geo_risk_summary="ドル安バイアス 1件",
        )
        prompt = _build_weekly_prompt(m)
        assert "ドル安バイアス 1件" in prompt

    def test_max_5_geo_events_in_prompt(self):
        events = [
            {"date": f"2026-05-{i+18}", "category": "FRB", "usd_impact": "bullish",
             "event_text": f"イベント{i}"}
            for i in range(7)
        ]
        m = self._make_metrics(geo_events=events, geo_risk_summary="ドル高バイアス 7件")
        prompt = _build_weekly_prompt(m)
        # 最大5件しか含まれないはず
        assert prompt.count("イベント") <= 5

    def test_usd_impact_translated_to_japanese(self):
        m = self._make_metrics(
            geo_events=[{"date": "2026-05-20", "category": "地政学リスク",
                         "usd_impact": "strong_bearish", "event_text": "中東で紛争激化"}],
            geo_risk_summary="ドル安バイアス 1件",
        )
        prompt = _build_weekly_prompt(m)
        assert "強いドル安" in prompt


# ── _generate_mock_narrative 地政学コンテキスト テスト ────────────────────

class TestMockNarrativeGeo:
    def _make_metrics(self, geo_events=None, geo_risk_summary="") -> WeeklyMetrics:
        return WeeklyMetrics(
            week_label="2026-W21",
            week_start="2026-05-18",
            week_end="2026-05-24",
            symbol="",
            geo_events=geo_events or [],
            geo_risk_summary=geo_risk_summary,
        )

    def test_no_geo_no_geo_mention(self):
        m = self._make_metrics()
        narrative = _generate_mock_narrative(m)
        assert "地政学" not in narrative

    def test_geo_events_mentioned_in_narrative(self):
        m = self._make_metrics(
            geo_events=[
                {"date": "2026-05-20", "category": "FRB", "usd_impact": "bullish",
                 "event_text": "FRB利上げ"}
            ],
            geo_risk_summary="ドル高バイアス 1件",
        )
        narrative = _generate_mock_narrative(m)
        assert "地政学" in narrative
        assert "ドル高バイアス 1件" in narrative

    def test_narrative_is_non_empty_string(self):
        m = self._make_metrics()
        assert isinstance(_generate_mock_narrative(m), str)
        assert len(_generate_mock_narrative(m)) > 0


# ── get_geopolitical_records との統合（DB フィルタ確認） ──────────────────

class TestGeoFetchInCollectMetrics:
    """_collect_metrics() が geopolitical_log から今週分のみ取得することをテスト"""

    def test_week_bounds_returns_correct_range(self):
        start, end = week_bounds("2026-W21")
        assert start == "2026-05-18"
        assert end == "2026-05-24"

    def test_geo_events_filtered_by_week(self, tmp_path):
        """この週の geo_events だけ含まれることを確認（実DB使用）"""
        from app.scripts.geopolitical import (
            GeopoliticalAnalysis, ensure_table, save_geopolitical_record
        )
        from app.scripts.weekly_report import _collect_metrics
        from app.database.db import init_db

        db_path = tmp_path / "test_weekly_geo.db"
        init_db(db_path)
        ensure_table(db_path)

        def _make_analysis(impact: str) -> GeopoliticalAnalysis:
            return GeopoliticalAnalysis(
                event_text="テストイベント",
                category="FRB金融政策（利上げ・利下げ・QE）",
                usd_impact=impact,
                confidence="high",
                reasoning="テスト",
                similar_events=[],
                short_term_outlook="テスト",
                risk_factors="テスト",
                ai_provider="mock",
            )

        # 今週内
        save_geopolitical_record(_make_analysis("bullish"), "2026-05-20", db_path)
        save_geopolitical_record(_make_analysis("bearish"), "2026-05-22", db_path)
        # 今週外
        save_geopolitical_record(_make_analysis("strong_bullish"), "2026-05-10", db_path)

        metrics = _collect_metrics("", "2026-W21", db_path)
        assert len(metrics.geo_events) == 2
        dates = [e["date"] for e in metrics.geo_events]
        assert "2026-05-20" in dates
        assert "2026-05-22" in dates
        assert "2026-05-10" not in dates

    def test_geo_risk_summary_computed(self, tmp_path):
        from app.scripts.geopolitical import (
            GeopoliticalAnalysis, ensure_table, save_geopolitical_record
        )
        from app.scripts.weekly_report import _collect_metrics
        from app.database.db import init_db

        db_path = tmp_path / "test_weekly_geo2.db"
        init_db(db_path)
        ensure_table(db_path)

        analysis = GeopoliticalAnalysis(
            event_text="FRB利上げ", category="FRB金融政策",
            usd_impact="bullish", confidence="high",
            reasoning="test", similar_events=[], short_term_outlook="test",
            risk_factors="test", ai_provider="mock",
        )
        save_geopolitical_record(analysis, "2026-05-20", db_path)

        metrics = _collect_metrics("", "2026-W21", db_path)
        assert "ドル高バイアス" in metrics.geo_risk_summary

    def test_no_geo_table_does_not_crash(self, tmp_path):
        """geopolitical_log テーブルが存在しなくてもクラッシュしない"""
        from app.scripts.weekly_report import _collect_metrics
        from app.database.db import init_db

        db_path = tmp_path / "test_weekly_nogeo.db"
        init_db(db_path)
        # geopolitical_log を作らない

        metrics = _collect_metrics("", "2026-W21", db_path)
        assert metrics.geo_events == []
        assert metrics.geo_risk_summary == ""
