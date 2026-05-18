"""Phase 32: マルチタイムフレーム一致度（ConfluenceResult）のテスト"""
from __future__ import annotations

import pytest

from app.strategy.scoring import ConfluenceResult, calculate_timeframe_confluence


class TestConfluenceResult:
    def test_all_agree_score_3(self):
        cf = ConfluenceResult(daily_agrees=True, h4_agrees=True, h1_agrees=True)
        assert cf.confluence_score == 3
        assert cf.confluence_strength == pytest.approx(1.0)
        assert cf.label == "3/3 全TF一致"
        assert cf.css_class == "confluence-strong"

    def test_two_agree_score_2(self):
        cf = ConfluenceResult(daily_agrees=True, h4_agrees=True, h1_agrees=False)
        assert cf.confluence_score == 2
        assert cf.confluence_strength == pytest.approx(2 / 3)
        assert cf.label == "2/3 一致"
        assert cf.css_class == "confluence-medium"

    def test_one_agree_score_1(self):
        cf = ConfluenceResult(daily_agrees=True, h4_agrees=False, h1_agrees=False)
        assert cf.confluence_score == 1
        assert cf.confluence_strength == pytest.approx(1 / 3)
        assert cf.label == "1/3 一致"
        assert cf.css_class == "confluence-weak"

    def test_none_agree_score_0(self):
        cf = ConfluenceResult(daily_agrees=False, h4_agrees=False, h1_agrees=False)
        assert cf.confluence_score == 0
        assert cf.confluence_strength == pytest.approx(0.0)
        assert cf.label == "0/3 不一致"
        assert cf.css_class == "confluence-weak"


class TestCalculateTimeframeConfluence:
    def test_buy_all_uptrend(self):
        cf = calculate_timeframe_confluence(
            daily_trend="上昇", h4_trend="上昇", h1_breakout=True, direction="BUY"
        )
        assert cf.daily_agrees is True
        assert cf.h4_agrees is True
        assert cf.h1_agrees is True
        assert cf.confluence_score == 3

    def test_buy_daily_only(self):
        cf = calculate_timeframe_confluence(
            daily_trend="上昇", h4_trend="下降", h1_breakout=False, direction="BUY"
        )
        assert cf.daily_agrees is True
        assert cf.h4_agrees is False
        assert cf.h1_agrees is False
        assert cf.confluence_score == 1

    def test_sell_all_downtrend(self):
        cf = calculate_timeframe_confluence(
            daily_trend="下降", h4_trend="下降", h1_breakout=True, direction="SELL"
        )
        assert cf.daily_agrees is True
        assert cf.h4_agrees is True
        assert cf.h1_agrees is True
        assert cf.confluence_score == 3

    def test_sell_partial(self):
        cf = calculate_timeframe_confluence(
            daily_trend="下降", h4_trend="上昇", h1_breakout=False, direction="SELL"
        )
        assert cf.daily_agrees is True
        assert cf.h4_agrees is False
        assert cf.h1_agrees is False
        assert cf.confluence_score == 1

    def test_buy_uptrend_no_h1_breakout(self):
        cf = calculate_timeframe_confluence(
            daily_trend="上昇", h4_trend="上昇", h1_breakout=False, direction="BUY"
        )
        assert cf.confluence_score == 2
        assert cf.label == "2/3 一致"

    def test_buy_sideways_trend(self):
        cf = calculate_timeframe_confluence(
            daily_trend="横ばい", h4_trend="横ばい", h1_breakout=True, direction="BUY"
        )
        assert cf.daily_agrees is False
        assert cf.h4_agrees is False
        assert cf.h1_agrees is True
        assert cf.confluence_score == 1
