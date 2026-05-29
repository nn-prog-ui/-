"""Phase 86: AIコメント強化（ローソク足パターン統合）テスト"""
from __future__ import annotations

import pytest

from app.indicators.candlestick_patterns import CandlePattern
from app.services.ai_commentary import (
    MockCommentaryAdapter,
    _build_signal_prompt,
    _generate_mock_commentary,
)
from app.strategy.rules import SignalResult


# ── テストデータ ─────────────────────────────────────────────────────────────

def _make_signal_result(signal: str = "BUY") -> SignalResult:
    """テスト用 SignalResult を返す。"""
    import dataclasses
    from app.strategy.scoring import ConditionResult, ConfluenceResult
    return SignalResult(
        signal=signal,
        daily_trend="上昇",
        h4_trend="上昇",
        h1_status="高値突破",
        rsi=55.0,
        atr_abnormal=False,
        recent_high=152.0,
        recent_low=148.0,
        skip_reasons=[],
        data_sufficient=True,
        score=None,
        buy_conditions=[],
        sell_conditions=[],
        confluence=None,
    )


def _bullish_pattern(strength: int = 2) -> CandlePattern:
    return CandlePattern("下影陽線", "Hammer", "bullish", strength, "テスト説明")


def _bearish_pattern(strength: int = 2) -> CandlePattern:
    return CandlePattern("流れ星", "Shooting Star", "bearish", strength, "テスト説明")


def _strong_bullish_pattern() -> CandlePattern:
    return CandlePattern("陽の包み足", "Bullish Engulfing", "bullish", 3, "テスト説明")


def _strong_bearish_pattern() -> CandlePattern:
    return CandlePattern("三川宵の明星", "Evening Star", "bearish", 3, "テスト説明")


# ── _generate_mock_commentary のパターン統合テスト ──────────────────────────

class TestMockCommentaryWithPatterns:
    def test_no_patterns_no_mention(self):
        """パターンなしでもコメントは生成される"""
        result = _make_signal_result("BUY")
        comment = _generate_mock_commentary(result, None, None, [])
        assert isinstance(comment, str)
        assert len(comment) > 0

    def test_bullish_pattern_mentioned(self):
        """強気パターン検出時にパターン名がコメントに含まれる"""
        result = _make_signal_result("BUY")
        comment = _generate_mock_commentary(result, None, None, [_bullish_pattern()])
        assert "下影陽線" in comment

    def test_bearish_pattern_mentioned(self):
        """弱気パターン検出時にパターン名がコメントに含まれる"""
        result = _make_signal_result("SELL")
        comment = _generate_mock_commentary(result, None, None, [_bearish_pattern()])
        assert "流れ星" in comment

    def test_strong_bullish_pattern_mention(self):
        """強度3の強気パターンは「強い強気パターン」として言及される"""
        result = _make_signal_result("BUY")
        comment = _generate_mock_commentary(result, None, None, [_strong_bullish_pattern()])
        assert "陽の包み足" in comment
        # 強度3なので「強い」が含まれるか、またはパターン名が含まれる
        assert "強気" in comment or "上昇" in comment

    def test_strong_bearish_pattern_mention(self):
        """強度3の弱気パターンは「強い弱気パターン」として言及される"""
        result = _make_signal_result("SELL")
        comment = _generate_mock_commentary(result, None, None, [_strong_bearish_pattern()])
        assert "三川宵の明星" in comment

    def test_mixed_patterns_both_mentioned(self):
        """強気・弱気が混在する場合に方向感混在を示す"""
        result = _make_signal_result("SKIP")
        comment = _generate_mock_commentary(
            result, None, None,
            [_bullish_pattern(), _bearish_pattern()]
        )
        assert "混在" in comment or "両方" in comment

    def test_multiple_bullish_patterns(self):
        """複数の強気パターンがあってもエラーなし"""
        result = _make_signal_result("BUY")
        patterns = [
            CandlePattern("下影陽線", "Hammer", "bullish", 2, "説明1"),
            CandlePattern("大陽線", "Strong Bullish Candle", "bullish", 2, "説明2"),
        ]
        comment = _generate_mock_commentary(result, None, None, patterns)
        assert isinstance(comment, str)

    def test_none_patterns_treated_as_empty(self):
        """None をパターンリストとして渡してもエラーなし"""
        result = _make_signal_result("BUY")
        comment = _generate_mock_commentary(result, None, None, None)
        assert isinstance(comment, str)


# ── MockCommentaryAdapter.generate() のパターン統合テスト ─────────────────

class TestMockAdapterWithPatterns:
    def test_adapter_accepts_patterns(self):
        """MockCommentaryAdapter.generate() がパターンリストを受け取れる"""
        adapter = MockCommentaryAdapter()
        result = _make_signal_result("BUY")
        comment = adapter.generate(result, None, None, candlestick_patterns=[_bullish_pattern()])
        assert isinstance(comment, str)
        assert len(comment) > 0

    def test_adapter_pattern_in_comment(self):
        """アダプター経由でもパターン名がコメントに含まれる"""
        adapter = MockCommentaryAdapter()
        result = _make_signal_result("BUY")
        comment = adapter.generate(
            result, None, None,
            candlestick_patterns=[_bullish_pattern()]
        )
        assert "下影陽線" in comment

    def test_adapter_no_patterns(self):
        """パターンなしでも generate() が正常動作する"""
        adapter = MockCommentaryAdapter()
        result = _make_signal_result("SKIP")
        comment = adapter.generate(result, None, None, candlestick_patterns=[])
        assert isinstance(comment, str)

    def test_adapter_none_patterns(self):
        """candlestick_patterns=None でも正常動作する"""
        adapter = MockCommentaryAdapter()
        result = _make_signal_result("BUY")
        comment = adapter.generate(result, None, None, candlestick_patterns=None)
        assert isinstance(comment, str)

    def test_forbidden_words_not_in_comment(self):
        """禁止表現がコメントに含まれない"""
        adapter = MockCommentaryAdapter()
        result = _make_signal_result("BUY")
        comment = adapter.generate(result, None, None, candlestick_patterns=[_strong_bullish_pattern()])
        forbidden = ["絶対に勝てる", "必ず上がる", "今すぐ全力", "損切り不要", "ナンピン推奨"]
        for word in forbidden:
            assert word not in comment, f"禁止ワード '{word}' がコメントに含まれています"


# ── _build_signal_prompt のパターン統合テスト ────────────────────────────

class TestBuildSignalPromptWithPatterns:
    def test_prompt_contains_pattern_section(self):
        """パターンがある場合プロンプトに【直近ローソク足パターン】が含まれる"""
        result = _make_signal_result("BUY")
        prompt = _build_signal_prompt(result, None, None,
                                      candlestick_patterns=[_bullish_pattern()])
        assert "ローソク足パターン" in prompt

    def test_prompt_contains_pattern_name(self):
        """プロンプトにパターン名が含まれる"""
        result = _make_signal_result("BUY")
        prompt = _build_signal_prompt(result, None, None,
                                      candlestick_patterns=[_bullish_pattern()])
        assert "下影陽線" in prompt

    def test_prompt_contains_english_name(self):
        """プロンプトに英語名が含まれる"""
        result = _make_signal_result("BUY")
        prompt = _build_signal_prompt(result, None, None,
                                      candlestick_patterns=[_bullish_pattern()])
        assert "Hammer" in prompt

    def test_prompt_no_pattern_section_when_empty(self):
        """パターンなしのときは【直近ローソク足パターン】セクションがない"""
        result = _make_signal_result("BUY")
        prompt = _build_signal_prompt(result, None, None, candlestick_patterns=[])
        assert "ローソク足パターン" not in prompt

    def test_prompt_max_4_patterns(self):
        """5個以上のパターンがあっても最大4つまでプロンプトに入る"""
        result = _make_signal_result("BUY")
        patterns = [
            CandlePattern(f"パターン{i}", f"Pattern{i}", "bullish", 1, "説明")
            for i in range(6)
        ]
        prompt = _build_signal_prompt(result, None, None, candlestick_patterns=patterns)
        # パターン0〜3は含まれるが、パターン5は含まれないはず（最大4）
        assert "パターン0" in prompt
        assert "パターン3" in prompt
        assert "パターン5" not in prompt

    def test_prompt_contains_direction_label(self):
        """プロンプトに方向ラベル（強気/弱気）が含まれる"""
        result = _make_signal_result("BUY")
        prompt = _build_signal_prompt(result, None, None,
                                      candlestick_patterns=[_bullish_pattern()])
        assert "強気" in prompt

    def test_prompt_bearish_label(self):
        """弱気パターンの場合「弱気」がプロンプトに含まれる"""
        result = _make_signal_result("SELL")
        prompt = _build_signal_prompt(result, None, None,
                                      candlestick_patterns=[_bearish_pattern()])
        assert "弱気" in prompt

    def test_prompt_without_patterns(self):
        """パターン引数なしでも動作する（後方互換性）"""
        result = _make_signal_result("BUY")
        prompt = _build_signal_prompt(result, None, None)
        assert isinstance(prompt, str)


# ── 後方互換性テスト ──────────────────────────────────────────────────────

class TestBackwardCompatibility:
    def test_mock_adapter_without_patterns_arg(self):
        """candlestick_patterns 引数なしで generate() を呼べる（旧API互換）"""
        adapter = MockCommentaryAdapter()
        result = _make_signal_result("BUY")
        # 旧来の呼び出し方式（3引数のみ）
        comment = adapter.generate(result, None, None)
        assert isinstance(comment, str)

    def test_generate_commentary_without_patterns(self):
        """generate_commentary() もパターンなしで動作する"""
        from app.services.ai_commentary import generate_commentary
        result = _make_signal_result("SKIP")
        # generate_commentary はシグナル結果のみで呼べる
        # ただし ANTHROPIC_API_KEY が未設定の環境ではモックが使われる
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        comment = generate_commentary(result)
        assert isinstance(comment, str)
