"""スコアリングモジュール：条件合否からスコアを計算する"""
from __future__ import annotations

from dataclasses import dataclass, field


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
