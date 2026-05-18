"""Phase 33: カスタムアラート評価エンジンのテスト"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.services.alert_evaluator import _evaluate_condition, _is_in_cooldown
from app.strategy.scoring import ConfluenceResult


def _make_result(
    signal="BUY",
    rsi=55.0,
    score=6,
    confluence_score=3,
):
    result = MagicMock()
    result.signal = signal
    result.rsi = rsi
    result.score = score
    result.confluence = ConfluenceResult(
        daily_agrees=(confluence_score >= 1),
        h4_agrees=(confluence_score >= 2),
        h1_agrees=(confluence_score >= 3),
    )
    return result


def _alert(ctype: str, cvalue: str) -> dict:
    return {
        "id": 1,
        "symbol": "USD/JPY",
        "label": "test",
        "condition_type": ctype,
        "condition_value": cvalue,
        "active": 1,
        "cooldown_minutes": 60,
        "last_triggered_at": None,
    }


class TestEvaluateCondition:
    def test_signal_type_buy_matches(self):
        assert _evaluate_condition(_alert("signal_type", "BUY"), _make_result(signal="BUY")) is True

    def test_signal_type_buy_no_match(self):
        assert _evaluate_condition(_alert("signal_type", "BUY"), _make_result(signal="SELL")) is False

    def test_signal_type_sell_matches(self):
        assert _evaluate_condition(_alert("signal_type", "SELL"), _make_result(signal="SELL")) is True

    def test_signal_type_buy_or_sell_buy(self):
        assert _evaluate_condition(_alert("signal_type", "BUY_OR_SELL"), _make_result(signal="BUY")) is True

    def test_signal_type_buy_or_sell_sell(self):
        assert _evaluate_condition(_alert("signal_type", "BUY_OR_SELL"), _make_result(signal="SELL")) is True

    def test_signal_type_buy_or_sell_skip(self):
        assert _evaluate_condition(_alert("signal_type", "BUY_OR_SELL"), _make_result(signal="SKIP")) is False

    def test_confluence_min_meets(self):
        result = _make_result(confluence_score=3)
        assert _evaluate_condition(_alert("confluence_min", "3"), result) is True

    def test_confluence_min_not_enough(self):
        result = _make_result(confluence_score=2)
        assert _evaluate_condition(_alert("confluence_min", "3"), result) is False

    def test_confluence_min_partial(self):
        result = _make_result(confluence_score=2)
        assert _evaluate_condition(_alert("confluence_min", "2"), result) is True

    def test_rsi_below_triggers(self):
        result = _make_result(rsi=35.0)
        assert _evaluate_condition(_alert("rsi_below", "40"), result) is True

    def test_rsi_below_no_trigger(self):
        result = _make_result(rsi=45.0)
        assert _evaluate_condition(_alert("rsi_below", "40"), result) is False

    def test_rsi_below_boundary(self):
        result = _make_result(rsi=40.0)
        assert _evaluate_condition(_alert("rsi_below", "40"), result) is False  # 未満なのでFalse

    def test_rsi_above_triggers(self):
        result = _make_result(rsi=65.0)
        assert _evaluate_condition(_alert("rsi_above", "60"), result) is True

    def test_rsi_above_no_trigger(self):
        result = _make_result(rsi=55.0)
        assert _evaluate_condition(_alert("rsi_above", "60"), result) is False

    def test_score_min_meets(self):
        result = _make_result(score=6)
        assert _evaluate_condition(_alert("score_min", "5"), result) is True

    def test_score_min_not_enough(self):
        result = _make_result(score=4)
        assert _evaluate_condition(_alert("score_min", "5"), result) is False

    def test_score_min_negative_score(self):
        result = _make_result(score=-6)
        assert _evaluate_condition(_alert("score_min", "5"), result) is True

    def test_rsi_none_returns_false(self):
        result = _make_result(rsi=None)
        assert _evaluate_condition(_alert("rsi_below", "40"), result) is False

    def test_confluence_none_returns_false(self):
        result = _make_result()
        result.confluence = None
        assert _evaluate_condition(_alert("confluence_min", "2"), result) is False


class TestCooldown:
    def test_no_last_triggered(self):
        al = _alert("signal_type", "BUY")
        al["last_triggered_at"] = None
        assert _is_in_cooldown(al) is False

    def test_recent_trigger_is_cooling(self):
        from datetime import datetime, timedelta
        al = _alert("signal_type", "BUY")
        al["cooldown_minutes"] = 60
        al["last_triggered_at"] = (datetime.utcnow() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        assert _is_in_cooldown(al) is True

    def test_old_trigger_cooldown_expired(self):
        from datetime import datetime, timedelta
        al = _alert("signal_type", "BUY")
        al["cooldown_minutes"] = 60
        al["last_triggered_at"] = (datetime.utcnow() - timedelta(minutes=90)).strftime("%Y-%m-%d %H:%M:%S")
        assert _is_in_cooldown(al) is False
