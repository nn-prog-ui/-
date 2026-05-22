"""Phase 66: AI地政学リスク分析 テスト"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.scripts.geopolitical import (
    EVENT_CATEGORIES,
    USD_IMPACT_LABELS,
    USD_IMPACT_COLORS,
    GeopoliticalAnalysis,
    GeopoliticalRecord,
    EventCorrelation,
    _classify_category,
    _mock_analysis,
    analyze_geopolitical_event,
    analyze_and_save,
    delete_geopolitical_record,
    ensure_table,
    get_event_correlations,
    get_geopolitical_records,
    save_geopolitical_record,
    update_actual_result,
)


# ── フィクスチャ ───────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    db = tmp_path / "test_geo.db"
    ensure_table(db)
    return db


def _make_analysis(usd_impact: str = "bullish", category: str = "FRB金融政策（利上げ・利下げ・QE）") -> GeopoliticalAnalysis:
    return GeopoliticalAnalysis(
        event_text="FRBが0.25%の利上げを決定した。",
        category=category,
        usd_impact=usd_impact,
        confidence="high",
        reasoning="米国の金利上昇はドル資産への需要を高める。",
        similar_events=["2022年FRB利上げ局面でドル円150円超え"],
        short_term_outlook="短期的にドル高が継続する可能性が高い。",
        risk_factors="景気後退懸念が高まれば利下げ転換でドル安に転じるリスクがある。",
        ai_provider="mock",
    )


# ── 定数テスト ────────────────────────────────────────────────────────────

class TestConstants:
    def test_event_categories_not_empty(self):
        assert len(EVENT_CATEGORIES) >= 5

    def test_usd_impact_labels_keys(self):
        expected = {"strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"}
        assert expected.issubset(set(USD_IMPACT_LABELS.keys()))

    def test_usd_impact_colors_keys(self):
        expected = {"strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"}
        assert expected.issubset(set(USD_IMPACT_COLORS.keys()))

    def test_bullish_color_is_green(self):
        assert USD_IMPACT_COLORS["strong_bullish"].startswith("#4a") or \
               USD_IMPACT_COLORS["strong_bullish"].lower().startswith("#4")

    def test_bearish_color_is_red(self):
        color = USD_IMPACT_COLORS["strong_bearish"]
        assert color.startswith("#f8") or color.startswith("#f")


# ── カテゴリー分類テスト ─────────────────────────────────────────────────

class TestClassifyCategory:
    def test_frb_keyword(self):
        assert _classify_category("FRBが利上げを決定") == "FRB金融政策（利上げ・利下げ・QE）"

    def test_rate_hike_keyword(self):
        assert _classify_category("利上げが実施された") == "FRB金融政策（利上げ・利下げ・QE）"

    def test_rate_cut_keyword(self):
        assert _classify_category("利下げ決定") == "FRB金融政策（利上げ・利下げ・QE）"

    def test_president_keyword(self):
        assert _classify_category("大統領が就任した") == "米大統領・政権交代"

    def test_employment_keyword(self):
        assert _classify_category("NFPが予想を下回った") == "米雇用・経済指標"

    def test_war_keyword(self):
        assert _classify_category("中東で戦争が勃発した") == "地政学リスク（戦争・紛争）"

    def test_tariff_keyword(self):
        assert _classify_category("関税を25%引き上げ") == "貿易・関税政策"

    def test_boj_keyword(self):
        assert _classify_category("日銀が利上げを決定") == "日銀金融政策"

    def test_oil_keyword(self):
        assert _classify_category("原油価格が急騰") == "エネルギー・資源価格"

    def test_unknown_returns_other(self):
        assert _classify_category("全く関係ないテキスト") == "その他"


# ── モック分析テスト ─────────────────────────────────────────────────────

class TestMockAnalysis:
    def test_returns_geopolitical_analysis(self):
        result = _mock_analysis("FRBが利上げを決定した")
        assert isinstance(result, GeopoliticalAnalysis)
        assert result.ai_provider == "mock"

    def test_frb_rate_hike_is_bullish(self):
        result = _mock_analysis("FRBが利上げを実施した")
        assert result.usd_impact in ("bullish", "strong_bullish")

    def test_frb_rate_cut_is_bearish(self):
        result = _mock_analysis("FRBが利下げを決定した")
        assert result.usd_impact in ("bearish", "strong_bearish")

    def test_trump_election_is_bullish(self):
        result = _mock_analysis("トランプ大統領が再当選した")
        assert result.usd_impact in ("bullish", "strong_bullish")

    def test_war_is_bullish(self):
        result = _mock_analysis("中東で戦争が激化している")
        assert result.usd_impact in ("bullish", "strong_bullish")

    def test_boj_rate_hike_is_bearish(self):
        result = _mock_analysis("日銀が利上げを決定した")
        assert result.usd_impact in ("bearish", "strong_bearish")

    def test_unknown_event_is_neutral(self):
        result = _mock_analysis("よくわからない何かが起きた")
        assert result.usd_impact == "neutral"
        assert result.confidence == "low"

    def test_reasoning_not_empty(self):
        result = _mock_analysis("FRBが利上げを決定した")
        assert len(result.reasoning) > 0

    def test_similar_events_list(self):
        result = _mock_analysis("FRBが利上げを決定した")
        assert isinstance(result.similar_events, list)

    def test_category_assigned(self):
        result = _mock_analysis("FRBが利上げを決定した")
        assert result.category != ""


# ── analyze_geopolitical_event テスト ────────────────────────────────────

class TestAnalyzeGeopoliticalEvent:
    def test_no_api_key_uses_mock(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            result = analyze_geopolitical_event("FRBが利上げを決定した")
        assert isinstance(result, GeopoliticalAnalysis)
        assert result.ai_provider == "mock"

    def test_result_has_required_fields(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            result = analyze_geopolitical_event("日銀が利上げを検討中")
        assert result.usd_impact in ("strong_bullish", "bullish", "neutral", "bearish", "strong_bearish")
        assert result.confidence in ("high", "medium", "low")
        assert isinstance(result.similar_events, list)

    def test_empty_text_returns_neutral(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            result = analyze_geopolitical_event("")
        assert isinstance(result, GeopoliticalAnalysis)


# ── DB操作テスト ─────────────────────────────────────────────────────────

class TestDBOperations:
    def test_save_and_retrieve(self, tmp_db):
        analysis = _make_analysis()
        record_id = save_geopolitical_record(analysis, "2026-05-22", tmp_db)
        assert record_id > 0
        records = get_geopolitical_records(db_path=tmp_db)
        assert len(records) == 1
        r = records[0]
        assert r.id == record_id
        assert r.usd_impact == "bullish"
        assert r.confidence == "high"
        assert r.event_date == "2026-05-22"
        assert r.ai_provider == "mock"

    def test_similar_events_roundtrip(self, tmp_db):
        analysis = _make_analysis()
        save_geopolitical_record(analysis, "2026-05-22", tmp_db)
        records = get_geopolitical_records(db_path=tmp_db)
        assert isinstance(records[0].similar_events, list)
        assert len(records[0].similar_events) > 0

    def test_empty_db_returns_empty_list(self, tmp_db):
        assert get_geopolitical_records(db_path=tmp_db) == []

    def test_limit_respected(self, tmp_db):
        for i in range(5):
            save_geopolitical_record(_make_analysis(), f"2026-05-{i+1:02d}", tmp_db)
        records = get_geopolitical_records(limit=3, db_path=tmp_db)
        assert len(records) == 3

    def test_update_actual_result(self, tmp_db):
        analysis = _make_analysis()
        record_id = save_geopolitical_record(analysis, "2026-05-22", tmp_db)
        update_actual_result(record_id, "翌週ドル高+80pips", tmp_db)
        records = get_geopolitical_records(db_path=tmp_db)
        assert records[0].actual_result == "翌週ドル高+80pips"

    def test_delete_record(self, tmp_db):
        analysis = _make_analysis()
        record_id = save_geopolitical_record(analysis, "2026-05-22", tmp_db)
        delete_geopolitical_record(record_id, tmp_db)
        records = get_geopolitical_records(db_path=tmp_db)
        assert len(records) == 0

    def test_actual_result_default_none(self, tmp_db):
        save_geopolitical_record(_make_analysis(), "2026-05-22", tmp_db)
        records = get_geopolitical_records(db_path=tmp_db)
        assert records[0].actual_result is None

    def test_multiple_categories(self, tmp_db):
        save_geopolitical_record(_make_analysis("bullish", "FRB金融政策（利上げ・利下げ・QE）"), "2026-05-01", tmp_db)
        save_geopolitical_record(_make_analysis("bearish", "日銀金融政策"), "2026-05-02", tmp_db)
        save_geopolitical_record(_make_analysis("neutral", "その他"), "2026-05-03", tmp_db)
        records = get_geopolitical_records(db_path=tmp_db)
        assert len(records) == 3


# ── カテゴリー相関集計テスト ─────────────────────────────────────────────

class TestEventCorrelations:
    def test_empty_db(self, tmp_db):
        result = get_event_correlations(db_path=tmp_db)
        assert result == []

    def test_single_category(self, tmp_db):
        save_geopolitical_record(_make_analysis("bullish"), "2026-05-01", tmp_db)
        save_geopolitical_record(_make_analysis("strong_bullish"), "2026-05-02", tmp_db)
        correlations = get_event_correlations(db_path=tmp_db)
        assert len(correlations) == 1
        c = correlations[0]
        assert c.total_events == 2
        assert c.bullish_events == 2
        assert c.bearish_events == 0

    def test_mixed_impacts(self, tmp_db):
        save_geopolitical_record(_make_analysis("bullish"), "2026-05-01", tmp_db)
        save_geopolitical_record(_make_analysis("bearish"), "2026-05-02", tmp_db)
        save_geopolitical_record(_make_analysis("neutral"), "2026-05-03", tmp_db)
        correlations = get_event_correlations(db_path=tmp_db)
        assert len(correlations) == 1
        c = correlations[0]
        assert c.total_events == 3
        assert c.bullish_events == 1
        assert c.bearish_events == 1

    def test_multiple_categories_separate(self, tmp_db):
        save_geopolitical_record(_make_analysis("bullish", "FRB金融政策（利上げ・利下げ・QE）"), "2026-05-01", tmp_db)
        save_geopolitical_record(_make_analysis("bearish", "日銀金融政策"), "2026-05-02", tmp_db)
        correlations = get_event_correlations(db_path=tmp_db)
        assert len(correlations) == 2
        cats = {c.category for c in correlations}
        assert "FRB金融政策（利上げ・利下げ・QE）" in cats
        assert "日銀金融政策" in cats


# ── analyze_and_save テスト ──────────────────────────────────────────────

class TestAnalyzeAndSave:
    def test_returns_analysis_and_id(self, tmp_db):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            analysis, record_id = analyze_and_save("FRBが利上げを決定した", "2026-05-22", tmp_db)
        assert isinstance(analysis, GeopoliticalAnalysis)
        assert record_id > 0

    def test_saved_to_db(self, tmp_db):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            _, record_id = analyze_and_save("日銀が利上げを示唆した", "2026-05-22", tmp_db)
        records = get_geopolitical_records(db_path=tmp_db)
        assert len(records) == 1
        assert records[0].id == record_id
