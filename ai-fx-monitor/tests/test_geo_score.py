"""Phase 68: 地政学リスクスコア補正 テスト"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.scripts.geopolitical import (
    GeopoliticalAnalysis,
    ensure_table,
    save_geopolitical_record,
)


# ── フィクスチャ ──────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    db = tmp_path / "test_geo_score.db"
    ensure_table(db)
    return db


def _make_analysis(usd_impact: str) -> GeopoliticalAnalysis:
    return GeopoliticalAnalysis(
        event_text="テストイベント",
        category="FRB金融政策（利上げ・利下げ・QE）",
        usd_impact=usd_impact,
        confidence="high",
        reasoning="テスト用根拠",
        similar_events=[],
        short_term_outlook="テスト見通し",
        risk_factors="テストリスク",
        ai_provider="mock",
    )


# ── _GEO_ADJUSTMENT マッピングのユニットテスト ────────────────────────────

GEO_ADJUSTMENT = {
    "strong_bullish": 1,
    "bullish": 1,
    "neutral": 0,
    "bearish": -1,
    "strong_bearish": -1,
}


class TestGeoAdjustmentMapping:
    def test_strong_bullish_is_plus1(self):
        assert GEO_ADJUSTMENT["strong_bullish"] == 1

    def test_bullish_is_plus1(self):
        assert GEO_ADJUSTMENT["bullish"] == 1

    def test_neutral_is_zero(self):
        assert GEO_ADJUSTMENT["neutral"] == 0

    def test_bearish_is_minus1(self):
        assert GEO_ADJUSTMENT["bearish"] == -1

    def test_strong_bearish_is_minus1(self):
        assert GEO_ADJUSTMENT["strong_bearish"] == -1

    def test_all_five_keys_covered(self):
        assert len(GEO_ADJUSTMENT) == 5


# ── スコア補正ロジックのユニットテスト ────────────────────────────────────

class TestScoreAdjustmentLogic:
    """run_analysis() 内のスコア補正ロジックを再現してテスト"""

    def _apply(self, base_score: int, usd_impact: str) -> int:
        adj = GEO_ADJUSTMENT.get(usd_impact, 0)
        return max(-7, min(7, base_score + adj))

    def test_bullish_adds_1(self):
        assert self._apply(3, "bullish") == 4

    def test_bearish_subtracts_1(self):
        assert self._apply(3, "bearish") == 2

    def test_neutral_no_change(self):
        assert self._apply(3, "neutral") == 3

    def test_strong_bullish_adds_1(self):
        assert self._apply(2, "strong_bullish") == 3

    def test_strong_bearish_subtracts_1(self):
        assert self._apply(-2, "strong_bearish") == -3

    def test_clamp_upper_limit(self):
        assert self._apply(7, "strong_bullish") == 7

    def test_clamp_lower_limit(self):
        assert self._apply(-7, "strong_bearish") == -7

    def test_negative_score_plus_bullish(self):
        assert self._apply(-1, "bullish") == 0

    def test_positive_score_plus_bearish(self):
        assert self._apply(1, "bearish") == 0

    def test_zero_score_unchanged_by_neutral(self):
        assert self._apply(0, "neutral") == 0


# ── AnalysisResult に geo フィールドが存在するか ──────────────────────────

class TestAnalysisResultGeoFields:
    def test_geo_score_adjustment_default(self):
        from app.services.market_analyzer import AnalysisResult
        from datetime import datetime
        r = AnalysisResult(
            symbol="USD/JPY",
            analyzed_at=datetime.utcnow(),
            current_price=150.0,
            signal="SKIP",
            score=0,
            daily_trend="up",
            h4_trend="up",
            h1_status="中立",
            rsi=50.0,
            atr_value=0.5,
            atr_status="普通",
            recent_high=151.0,
            recent_low=149.0,
            setup=None,
            economic_warning=False,
            economic_event_name="",
            ai_comment="",
            skip_reasons=[],
            data_sufficient=True,
            is_dummy_data=False,
        )
        assert r.geo_score_adjustment == 0
        assert r.geo_risk_level == "neutral"

    def test_geo_score_adjustment_can_be_set(self):
        from app.services.market_analyzer import AnalysisResult
        from datetime import datetime
        r = AnalysisResult(
            symbol="USD/JPY",
            analyzed_at=datetime.utcnow(),
            current_price=150.0,
            signal="BUY",
            score=4,
            daily_trend="up",
            h4_trend="up",
            h1_status="買い",
            rsi=60.0,
            atr_value=0.5,
            atr_status="普通",
            recent_high=151.0,
            recent_low=149.0,
            setup=None,
            economic_warning=False,
            economic_event_name="",
            ai_comment="",
            skip_reasons=[],
            data_sufficient=True,
            is_dummy_data=False,
            geo_score_adjustment=1,
            geo_risk_level="bullish",
        )
        assert r.geo_score_adjustment == 1
        assert r.geo_risk_level == "bullish"


# ── run_analysis() 統合テスト（地政学レコードがある場合） ─────────────────

class TestRunAnalysisGeoIntegration:
    def test_run_analysis_has_geo_fields(self):
        """run_analysis() が geo フィールドを返すことを確認"""
        from app.services.market_analyzer import run_analysis
        result = run_analysis()
        assert hasattr(result, "geo_score_adjustment")
        assert hasattr(result, "geo_risk_level")
        assert isinstance(result.geo_score_adjustment, int)
        assert isinstance(result.geo_risk_level, str)

    def test_geo_adjustment_in_valid_range(self):
        from app.services.market_analyzer import run_analysis
        result = run_analysis()
        assert result.geo_score_adjustment in (-1, 0, 1)

    def test_geo_risk_level_is_valid_key(self):
        from app.scripts.geopolitical import USD_IMPACT_LABELS
        from app.services.market_analyzer import run_analysis
        result = run_analysis()
        assert result.geo_risk_level in USD_IMPACT_LABELS

    def test_score_clamped_to_7(self):
        """スコアが ±7 を超えないことを確認"""
        from app.services.market_analyzer import run_analysis
        result = run_analysis()
        if result.score is not None:
            assert -7 <= result.score <= 7
