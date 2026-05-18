"""スコアリングモジュール：条件合否からスコアを計算する"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

SIGNAL_BUY = "BUY"
SIGNAL_SELL = "SELL"


@dataclass
class ConfluenceResult:
    """日足・4時間足・1時間足の方向一致度を表す。"""

    daily_agrees: bool
    h4_agrees: bool
    h1_agrees: bool

    @property
    def confluence_score(self) -> int:
        return sum([self.daily_agrees, self.h4_agrees, self.h1_agrees])

    @property
    def confluence_strength(self) -> float:
        return self.confluence_score / 3.0

    @property
    def label(self) -> str:
        score = self.confluence_score
        if score == 3:
            return "3/3 全TF一致"
        if score == 2:
            return "2/3 一致"
        if score == 1:
            return "1/3 一致"
        return "0/3 不一致"

    @property
    def css_class(self) -> str:
        score = self.confluence_score
        if score == 3:
            return "confluence-strong"
        if score == 2:
            return "confluence-medium"
        return "confluence-weak"


def calculate_timeframe_confluence(
    daily_trend: str,
    h4_trend: str,
    h1_breakout: bool,
    direction: str,
) -> ConfluenceResult:
    """各時間足が指定方向に一致しているかを判定する。"""
    if direction == SIGNAL_BUY:
        return ConfluenceResult(
            daily_agrees=daily_trend == "上昇",
            h4_agrees=h4_trend == "上昇",
            h1_agrees=h1_breakout,
        )
    # SELL
    return ConfluenceResult(
        daily_agrees=daily_trend == "下降",
        h4_agrees=h4_trend == "下降",
        h1_agrees=h1_breakout,
    )


@dataclass
class ConditionResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ScoreResult:
    score: int
    max_score: int
    conditions: list[ConditionResult] = field(default_factory=list)
    direction: str = "BUY"

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.conditions if c.passed)

    @property
    def failed_conditions(self) -> list[ConditionResult]:
        return [c for c in self.conditions if not c.passed]

    @property
    def passed_conditions(self) -> list[ConditionResult]:
        return [c for c in self.conditions if c.passed]


def calculate_score(conditions: list[ConditionResult], direction: str = "BUY") -> ScoreResult:
    """条件リストからスコアを計算する。

    スコア = 通過した条件数
    方向が BUY なら正のスコア、SELL なら負のスコアとして表現する。
    """
    passed = sum(1 for c in conditions if c.passed)
    score = passed if direction == "BUY" else -passed
    return ScoreResult(
        score=score,
        max_score=len(conditions),
        conditions=conditions,
        direction=direction,
    )
