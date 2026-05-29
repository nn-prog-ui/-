"""Phase 85: ローソク足パターン検出 テスト"""
from __future__ import annotations

import pandas as pd
import pytest

from app.indicators.candlestick_patterns import (
    CandlePattern,
    detect_patterns,
    _body,
    _upper_shadow,
    _lower_shadow,
    _detect_single,
    _detect_two_candle,
    _detect_three_candle,
)


# ── ヘルパー ──────────────────────────────────────────────────────────────────

def _make_df(*rows: tuple[float, float, float, float]) -> pd.DataFrame:
    """(open, high, low, close) のタプルリストから DataFrame を作成する。"""
    data = [{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in rows]
    idx = pd.date_range("2024-01-01", periods=len(data), freq="1h")
    return pd.DataFrame(data, index=idx)


def _names(patterns: list[CandlePattern]) -> list[str]:
    return [p.name for p in patterns]


# ── ヘルパー関数テスト ────────────────────────────────────────────────────────

class TestHelpers:
    def test_body_positive(self):
        """実体は絶対値（陽線）"""
        assert _body(100.0, 101.5) == pytest.approx(1.5)

    def test_body_negative(self):
        """実体は絶対値（陰線）"""
        assert _body(101.5, 100.0) == pytest.approx(1.5)

    def test_upper_shadow_bullish(self):
        """上ひげ: 高値 - max(open, close)"""
        assert _upper_shadow(100.0, 102.0, 101.0) == pytest.approx(1.0)

    def test_upper_shadow_bearish(self):
        """上ひげ: 高値 - max(open, close)"""
        assert _upper_shadow(101.0, 102.0, 100.0) == pytest.approx(1.0)

    def test_lower_shadow_bullish(self):
        """下ひげ: min(open, close) - 安値"""
        assert _lower_shadow(100.0, 98.0, 101.0) == pytest.approx(2.0)

    def test_lower_shadow_bearish(self):
        """下ひげ: min(open, close) - 安値"""
        assert _lower_shadow(101.0, 98.0, 100.0) == pytest.approx(2.0)


# ── 単体パターンテスト ────────────────────────────────────────────────────────

class TestSinglePatterns:
    def test_hammer_detected(self):
        """下影陽線（ハンマー）が検出される"""
        # 実体0.5、下ひげ1.5（実体×3）、上ひげ0.1
        patterns = _detect_single(100.0, 100.6, 98.5, 100.5)
        assert "下影陽線" in _names(patterns)

    def test_hammer_direction_bullish(self):
        """ハンマーは bullish"""
        patterns = _detect_single(100.0, 100.6, 98.5, 100.5)
        p = next(p for p in patterns if p.name == "下影陽線")
        assert p.direction == "bullish"

    def test_hammer_strength(self):
        """ハンマーの強度は2"""
        patterns = _detect_single(100.0, 100.6, 98.5, 100.5)
        p = next(p for p in patterns if p.name == "下影陽線")
        assert p.strength == 2

    def test_shooting_star_detected(self):
        """流れ星（シューティングスター）が検出される"""
        # 陰線: open=100.5, close=100.0, 上ひげ2.0, 下ひげ0.1
        patterns = _detect_single(100.5, 102.6, 99.9, 100.0)
        assert "流れ星" in _names(patterns)

    def test_shooting_star_direction_bearish(self):
        """流れ星は bearish"""
        patterns = _detect_single(100.5, 102.6, 99.9, 100.0)
        p = next(p for p in patterns if p.name == "流れ星")
        assert p.direction == "bearish"

    def test_strong_bullish_detected(self):
        """大陽線が検出される（実体が全体の70%以上、陽線）"""
        # open=100, close=102, high=102.1, low=99.9 → 実体2.0/全体2.2 ≈ 91%
        patterns = _detect_single(100.0, 102.1, 99.9, 102.0)
        assert "大陽線" in _names(patterns)

    def test_strong_bearish_detected(self):
        """大陰線が検出される（実体が全体の70%以上、陰線）"""
        patterns = _detect_single(102.0, 102.1, 99.9, 100.0)
        assert "大陰線" in _names(patterns)

    def test_no_pattern_on_doji(self):
        """同値足（実体0）ではパターン検出されない"""
        patterns = _detect_single(100.0, 100.5, 99.5, 100.0)
        assert patterns == []

    def test_no_pattern_on_flat(self):
        """値動きゼロではパターン検出されない"""
        patterns = _detect_single(100.0, 100.0, 100.0, 100.0)
        assert patterns == []

    def test_hanging_man_needs_uptrend(self):
        """首吊り線は上昇トレンド文脈が必要"""
        # 陰線: open=100.5, close=100.0, high=100.6(上ひげ小), low=98.5(下ひげ大)
        # body=0.5, upper=0.1(≤0.25=body×0.5 ✓), lower=1.5(≥1.0=body×2 ✓)
        patterns_up = _detect_single(100.5, 100.6, 98.5, 100.0, prev_trend="上昇")
        patterns_no = _detect_single(100.5, 100.6, 98.5, 100.0, prev_trend="")
        assert "首吊り線" in _names(patterns_up)
        assert "首吊り線" not in _names(patterns_no)

    def test_inverted_hammer_needs_downtrend(self):
        """上影陽線は下降トレンド文脈が必要"""
        patterns_down = _detect_single(100.0, 102.5, 99.9, 100.5, prev_trend="下降")
        patterns_no = _detect_single(100.0, 102.5, 99.9, 100.5, prev_trend="")
        assert "上影陽線" in _names(patterns_down)
        assert "上影陽線" not in _names(patterns_no)


# ── 2本パターンテスト ─────────────────────────────────────────────────────────

class TestTwoCandlePatterns:
    def test_bullish_engulfing_detected(self):
        """陽の包み足（強気エンゴルフィング）が検出される"""
        # 1本目: 陰線 open=101, close=99
        # 2本目: 陽線 open=98.5, close=101.5 → 1本目の実体を包む
        patterns = _detect_two_candle(
            101.0, 101.5, 98.5, 99.0,   # 1本目 陰線
            98.5, 102.0, 98.0, 101.5,   # 2本目 陽線
        )
        assert "陽の包み足" in _names(patterns)

    def test_bullish_engulfing_direction(self):
        """陽の包み足は bullish"""
        patterns = _detect_two_candle(
            101.0, 101.5, 98.5, 99.0,
            98.5, 102.0, 98.0, 101.5,
        )
        p = next(p for p in patterns if p.name == "陽の包み足")
        assert p.direction == "bullish"
        assert p.strength == 3

    def test_bearish_engulfing_detected(self):
        """陰の包み足（弱気エンゴルフィング）が検出される"""
        # 1本目: 陽線 open=99, close=101
        # 2本目: 陰線 open=101.5, close=98.5 → 1本目の実体を包む
        patterns = _detect_two_candle(
            99.0, 101.5, 98.5, 101.0,   # 1本目 陽線
            101.5, 102.0, 98.0, 98.5,   # 2本目 陰線
        )
        assert "陰の包み足" in _names(patterns)

    def test_bearish_engulfing_direction(self):
        """陰の包み足は bearish"""
        patterns = _detect_two_candle(
            99.0, 101.5, 98.5, 101.0,
            101.5, 102.0, 98.0, 98.5,
        )
        p = next(p for p in patterns if p.name == "陰の包み足")
        assert p.direction == "bearish"
        assert p.strength == 3

    def test_tweezer_bottom_detected(self):
        """二本たくり線（ツイーザーボトム）が検出される"""
        # 2本の安値がほぼ同じ、2本目は陽線
        patterns = _detect_two_candle(
            100.5, 101.0, 98.0, 99.0,   # 1本目（下ひげあり）
            98.5, 101.5, 98.0, 101.0,   # 2本目 陽線、安値≒同じ
        )
        assert "二本たくり線" in _names(patterns)

    def test_no_two_candle_pattern_on_small_body(self):
        """実体が極小では2本パターンなし"""
        patterns = _detect_two_candle(
            100.0, 100.01, 99.99, 100.0,  # 実体ほぼ0
            99.9, 100.1, 99.8, 100.0,
        )
        assert patterns == []


# ── 3本パターンテスト ─────────────────────────────────────────────────────────

class TestThreeCandlePatterns:
    def test_morning_star_detected(self):
        """三川明けの明星（モーニングスター）が検出される"""
        # 大陰線 → 小実体 → 大陽線（1本目中心超え）
        patterns = _detect_three_candle(
            105.0, 105.5, 99.5, 100.0,   # 1本目: 大陰線 実体5.0
            99.5,  100.5, 98.5, 100.0,   # 2本目: 小実体 (ドージ気味)
            100.0, 106.0, 99.8, 106.0,   # 3本目: 大陽線、1本目中心(102.5)超え
        )
        assert "三川明けの明星" in _names(patterns)

    def test_morning_star_direction(self):
        """モーニングスターは bullish"""
        patterns = _detect_three_candle(
            105.0, 105.5, 99.5, 100.0,
            99.5,  100.5, 98.5, 100.0,
            100.0, 106.0, 99.8, 106.0,
        )
        p = next(p for p in patterns if p.name == "三川明けの明星")
        assert p.direction == "bullish"
        assert p.strength == 3

    def test_evening_star_detected(self):
        """三川宵の明星（イブニングスター）が検出される"""
        # 大陽線 → 小実体 → 大陰線（1本目中心下回り）
        patterns = _detect_three_candle(
            100.0, 105.5, 99.8, 105.0,   # 1本目: 大陽線 実体5.0
            105.0, 106.0, 104.5, 105.2,  # 2本目: 小実体
            105.2, 105.5, 99.5, 100.0,   # 3本目: 大陰線、1本目中心(102.5)下回り
        )
        assert "三川宵の明星" in _names(patterns)

    def test_evening_star_direction(self):
        """イブニングスターは bearish"""
        patterns = _detect_three_candle(
            100.0, 105.5, 99.8, 105.0,
            105.0, 106.0, 104.5, 105.2,
            105.2, 105.5, 99.5, 100.0,
        )
        p = next(p for p in patterns if p.name == "三川宵の明星")
        assert p.direction == "bearish"
        assert p.strength == 3

    def test_three_white_soldiers_detected(self):
        """赤三兵（スリーホワイトソルジャーズ）が検出される"""
        patterns = _detect_three_candle(
            100.0, 101.5, 99.8, 101.0,   # 1本目: 陽線
            100.8, 102.5, 100.5, 102.0,  # 2本目: 陽線、前本高値内で始まり高値終値
            101.8, 103.5, 101.5, 103.0,  # 3本目: 陽線、同様
        )
        assert "赤三兵" in _names(patterns)

    def test_three_black_crows_detected(self):
        """黒三兵（スリーブラッククロウズ）が検出される"""
        patterns = _detect_three_candle(
            103.0, 103.5, 101.5, 102.0,  # 1本目: 陰線
            102.2, 102.5, 100.5, 101.0,  # 2本目: 陰線
            101.2, 101.5, 99.5, 100.0,   # 3本目: 陰線
        )
        assert "黒三兵" in _names(patterns)

    def test_no_three_candle_on_flat(self):
        """実体ゼロでは3本パターンなし"""
        patterns = _detect_three_candle(
            100.0, 100.0, 100.0, 100.0,
            100.0, 100.0, 100.0, 100.0,
            100.0, 100.0, 100.0, 100.0,
        )
        assert patterns == []


# ── detect_patterns（メイン関数）テスト ──────────────────────────────────────

class TestDetectPatterns:
    def test_returns_list(self):
        """リストを返す"""
        df = _make_df(
            (100.0, 101.5, 99.8, 101.0),
            (100.8, 102.5, 100.5, 102.0),
            (101.8, 103.5, 101.5, 103.0),
        )
        result = detect_patterns(df)
        assert isinstance(result, list)

    def test_empty_df_returns_empty(self):
        """空 DataFrame では空リスト"""
        assert detect_patterns(pd.DataFrame()) == []

    def test_none_df_returns_empty(self):
        """None では空リスト"""
        assert detect_patterns(None) == []

    def test_missing_columns_returns_empty(self):
        """OHLC カラムが不足している場合は空リスト"""
        df = pd.DataFrame({"price": [100, 101, 102]})
        assert detect_patterns(df) == []

    def test_deduplication(self):
        """同名パターンは重複しない"""
        df = _make_df(
            (100.0, 101.5, 99.8, 101.0),
            (100.8, 102.5, 100.5, 102.0),
            (101.8, 103.5, 101.5, 103.0),  # 赤三兵
        )
        result = detect_patterns(df)
        names = [p.name for p in result]
        assert len(names) == len(set(names)), "重複パターン名が存在する"

    def test_single_row_df(self):
        """1行のみでも動作する"""
        df = _make_df((100.0, 102.1, 99.9, 102.0))  # 大陽線
        result = detect_patterns(df)
        assert isinstance(result, list)

    def test_two_row_df(self):
        """2行のみでも動作する"""
        df = _make_df(
            (101.0, 101.5, 98.5, 99.0),
            (98.5, 102.0, 98.0, 101.5),
        )
        result = detect_patterns(df)
        assert isinstance(result, list)

    def test_pattern_has_required_fields(self):
        """CandlePattern に必須フィールドが揃っている"""
        df = _make_df(
            (100.0, 102.1, 99.9, 102.0),  # 大陽線
        )
        result = detect_patterns(df)
        if result:
            p = result[0]
            assert hasattr(p, "name")
            assert hasattr(p, "name_en")
            assert hasattr(p, "direction")
            assert hasattr(p, "strength")
            assert hasattr(p, "description")

    def test_direction_valid_values(self):
        """direction は bullish / bearish / neutral のいずれか"""
        df = _make_df(
            (101.0, 101.5, 98.5, 99.0),
            (98.5, 102.0, 98.0, 101.5),
            (100.0, 103.5, 99.8, 103.0),
        )
        result = detect_patterns(df)
        for p in result:
            assert p.direction in ("bullish", "bearish", "neutral"), \
                f"無効な direction: {p.direction}"

    def test_strength_valid_range(self):
        """strength は 1〜3 の整数"""
        df = _make_df(
            (105.0, 105.5, 99.5, 100.0),
            (99.5,  100.5, 98.5, 100.0),
            (100.0, 106.0, 99.8, 106.0),
        )
        result = detect_patterns(df)
        for p in result:
            assert 1 <= p.strength <= 3, f"strength が範囲外: {p.strength}"

    def test_with_prev_trend(self):
        """prev_trend を指定しても動作する"""
        df = _make_df(
            (100.5, 101.0, 98.5, 100.0),
        )
        result_up = detect_patterns(df, prev_trend="上昇")
        result_down = detect_patterns(df, prev_trend="下降")
        assert isinstance(result_up, list)
        assert isinstance(result_down, list)

    def test_large_df_uses_last_3_rows(self):
        """100行 DF でも最後の3行だけを使う（クラッシュしない）"""
        rows = [(100.0 + i * 0.1, 100.5 + i * 0.1, 99.5 + i * 0.1, 100.2 + i * 0.1)
                for i in range(100)]
        df = _make_df(*rows)
        result = detect_patterns(df)
        assert isinstance(result, list)


# ── CandlePattern データクラステスト ─────────────────────────────────────────

class TestCandlePatternDataclass:
    def test_instantiation(self):
        """CandlePattern を直接インスタンス化できる"""
        p = CandlePattern(
            name="テスト",
            name_en="Test",
            direction="bullish",
            strength=2,
            description="テスト説明",
        )
        assert p.name == "テスト"
        assert p.name_en == "Test"
        assert p.direction == "bullish"
        assert p.strength == 2
        assert p.description == "テスト説明"

    def test_repr_contains_name(self):
        """repr に名前が含まれる"""
        p = CandlePattern("下影陽線", "Hammer", "bullish", 2, "説明")
        assert "下影陽線" in repr(p)
