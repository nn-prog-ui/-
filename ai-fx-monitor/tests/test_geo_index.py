"""Phase 67: 判定画面への地政学リスク表示 テスト"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.scripts.geopolitical import (
    GeopoliticalAnalysis,
    GeopoliticalRecord,
    USD_IMPACT_COLORS,
    USD_IMPACT_LABELS,
    ensure_table,
    save_geopolitical_record,
    get_geopolitical_records,
)


# ── フィクスチャ ──────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    db = tmp_path / "test_geo.db"
    ensure_table(db)
    return db


def _make_analysis(usd_impact: str = "bullish") -> GeopoliticalAnalysis:
    return GeopoliticalAnalysis(
        event_text="FRBが0.25%の利上げを決定した。",
        category="FRB金融政策（利上げ・利下げ・QE）",
        usd_impact=usd_impact,
        confidence="high",
        reasoning="米国の金利上昇はドル資産への需要を高める。",
        similar_events=["2022年FRB利上げ局面でドル円150円超え"],
        short_term_outlook="短期的にドル高が継続する可能性が高い。",
        risk_factors="景気後退懸念が高まれば利下げ転換でドル安に転じるリスクがある。",
        ai_provider="mock",
    )


# ── USD_IMPACT_LABELS / USD_IMPACT_COLORS が揃っているか ─────────────────

class TestImpactConstants:
    ALL_KEYS = {"strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"}

    def test_labels_have_all_keys(self):
        assert self.ALL_KEYS.issubset(set(USD_IMPACT_LABELS.keys()))

    def test_colors_have_all_keys(self):
        assert self.ALL_KEYS.issubset(set(USD_IMPACT_COLORS.keys()))

    def test_labels_are_japanese_strings(self):
        for key, label in USD_IMPACT_LABELS.items():
            assert isinstance(label, str) and len(label) > 0, f"{key} label is empty"

    def test_colors_are_hex_strings(self):
        for key, color in USD_IMPACT_COLORS.items():
            assert color.startswith("#"), f"{key} color '{color}' is not a hex string"


# ── geo_risk 計算ロジック（routes.py 内のロジックを再現） ─────────────────

class TestGeoRiskCalculation:
    """判定画面での geo_risk 決定ロジックのユニットテスト"""

    def _compute_geo_risk(self, records: list) -> str:
        return records[0].usd_impact if records else "neutral"

    def test_empty_records_returns_neutral(self):
        assert self._compute_geo_risk([]) == "neutral"

    def test_single_bullish_record(self, tmp_db):
        save_geopolitical_record(_make_analysis("bullish"), "2026-05-22", tmp_db)
        records = get_geopolitical_records(limit=3, db_path=tmp_db)
        assert self._compute_geo_risk(records) == "bullish"

    def test_single_bearish_record(self, tmp_db):
        save_geopolitical_record(_make_analysis("bearish"), "2026-05-22", tmp_db)
        records = get_geopolitical_records(limit=3, db_path=tmp_db)
        assert self._compute_geo_risk(records) == "bearish"

    def test_most_recent_record_determines_risk(self, tmp_db):
        save_geopolitical_record(_make_analysis("bearish"), "2026-05-20", tmp_db)
        save_geopolitical_record(_make_analysis("strong_bullish"), "2026-05-22", tmp_db)
        records = get_geopolitical_records(limit=3, db_path=tmp_db)
        # get_geopolitical_records returns newest first
        assert self._compute_geo_risk(records) == "strong_bullish"

    def test_strong_bearish_passed_through(self, tmp_db):
        save_geopolitical_record(_make_analysis("strong_bearish"), "2026-05-22", tmp_db)
        records = get_geopolitical_records(limit=3, db_path=tmp_db)
        assert self._compute_geo_risk(records) == "strong_bearish"

    def test_neutral_passed_through(self, tmp_db):
        save_geopolitical_record(_make_analysis("neutral"), "2026-05-22", tmp_db)
        records = get_geopolitical_records(limit=3, db_path=tmp_db)
        assert self._compute_geo_risk(records) == "neutral"


# ── get_geopolitical_records limit=3 が守られるか ─────────────────────────

class TestGeoRecordsLimit:
    def test_limit_3_for_index(self, tmp_db):
        for i in range(5):
            save_geopolitical_record(_make_analysis("bullish"), f"2026-05-{i+1:02d}", tmp_db)
        records = get_geopolitical_records(limit=3, db_path=tmp_db)
        assert len(records) == 3

    def test_records_ordered_newest_first(self, tmp_db):
        save_geopolitical_record(_make_analysis("bearish"), "2026-05-20", tmp_db)
        save_geopolitical_record(_make_analysis("bullish"), "2026-05-22", tmp_db)
        records = get_geopolitical_records(limit=3, db_path=tmp_db)
        assert records[0].event_date == "2026-05-22"
        assert records[1].event_date == "2026-05-20"


# ── GeopoliticalRecord のフィールドがテンプレートで使えるか ──────────────

class TestGeopoliticalRecordFields:
    def test_record_has_event_text(self, tmp_db):
        save_geopolitical_record(_make_analysis(), "2026-05-22", tmp_db)
        r = get_geopolitical_records(db_path=tmp_db)[0]
        assert isinstance(r.event_text, str)

    def test_record_has_category(self, tmp_db):
        save_geopolitical_record(_make_analysis(), "2026-05-22", tmp_db)
        r = get_geopolitical_records(db_path=tmp_db)[0]
        assert isinstance(r.category, str)

    def test_record_has_event_date(self, tmp_db):
        save_geopolitical_record(_make_analysis(), "2026-05-22", tmp_db)
        r = get_geopolitical_records(db_path=tmp_db)[0]
        assert r.event_date == "2026-05-22"

    def test_record_has_reasoning(self, tmp_db):
        save_geopolitical_record(_make_analysis(), "2026-05-22", tmp_db)
        r = get_geopolitical_records(db_path=tmp_db)[0]
        assert isinstance(r.reasoning, str)

    def test_record_usd_impact_is_valid_key(self, tmp_db):
        save_geopolitical_record(_make_analysis("bullish"), "2026-05-22", tmp_db)
        r = get_geopolitical_records(db_path=tmp_db)[0]
        assert r.usd_impact in USD_IMPACT_LABELS
        assert r.usd_impact in USD_IMPACT_COLORS

    def test_event_text_truncation_safe(self, tmp_db):
        long_text = "FRBが利上げを決定した。" * 20
        analysis = GeopoliticalAnalysis(
            event_text=long_text,
            category="FRB金融政策（利上げ・利下げ・QE）",
            usd_impact="bullish",
            confidence="high",
            reasoning="test",
            similar_events=[],
            short_term_outlook="test",
            risk_factors="test",
            ai_provider="mock",
        )
        save_geopolitical_record(analysis, "2026-05-22", tmp_db)
        r = get_geopolitical_records(db_path=tmp_db)[0]
        # テンプレートは [:80] でトリミングするので元データは保存されている
        assert len(r.event_text) > 80
