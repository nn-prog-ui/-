"""Phase 43: モンテカルロ分析エンジン

バックテストで得られた損益(pips)リストをランダムシャッフルして
N回シミュレーションを行い、期待損益・最大DD・破産確率の分布を算出する。

注文は一切発生しない。分析・集計のみ。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from app.database.db import get_db


DEFAULT_N_SIMULATIONS = 1000
DEFAULT_RUIN_THRESHOLD = -200.0   # この損益(pips)以下になると「破産」とみなす


@dataclass
class PercentileStats:
    """パーセンタイル統計。"""
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float
    mean: float
    minimum: float
    maximum: float


@dataclass
class MonteCarloResult:
    """モンテカルロ分析の結果。"""
    n_trades: int
    n_simulations: int
    ruin_threshold: float

    # 入力トレード統計
    raw_win_rate: float | None        # 元データの勝率
    raw_total_pips: float             # 元データの合計pips
    raw_max_drawdown: float           # 元データの最大DD

    # シミュレーション分布
    final_pips: PercentileStats | None = None
    max_drawdown: PercentileStats | None = None

    # 確率指標
    ruin_probability: float = 0.0       # 破産確率（0〜1）
    profit_probability: float = 0.0     # プラス収益確率（0〜1）

    # 勝率95%信頼区間（Wilson score）
    win_rate_ci_lower: float | None = None
    win_rate_ci_upper: float | None = None

    assessment: str = ""


def _max_drawdown(cumulative: list[float]) -> float:
    """累積損益リストから最大ドローダウン（負の値）を計算する。"""
    if not cumulative:
        return 0.0
    peak = cumulative[0]
    max_dd = 0.0
    for v in cumulative:
        if v > peak:
            peak = v
        dd = v - peak
        if dd < max_dd:
            max_dd = dd
    return round(max_dd, 2)


def _cumulative(pips: list[float]) -> list[float]:
    total = 0.0
    result = []
    for p in pips:
        total += p
        result.append(round(total, 2))
    return result


def _percentile_stats(values: list[float]) -> PercentileStats:
    """ソート済みリストからパーセンタイル統計を計算する。"""
    n = len(values)
    sorted_v = sorted(values)

    def pct(p: float) -> float:
        idx = (n - 1) * p / 100
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return round(sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * (idx - lo), 2)

    return PercentileStats(
        p5=pct(5), p25=pct(25), p50=pct(50), p75=pct(75), p95=pct(95),
        mean=round(sum(sorted_v) / n, 2),
        minimum=round(sorted_v[0], 2),
        maximum=round(sorted_v[-1], 2),
    )


def _wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 信頼区間。wins/n の95%CIを返す。"""
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / denom
    return max(0.0, round((center - spread) * 100, 1)), min(100.0, round((center + spread) * 100, 1))


def run_monte_carlo(
    pnl_pips: list[float],
    n_simulations: int = DEFAULT_N_SIMULATIONS,
    ruin_threshold: float = DEFAULT_RUIN_THRESHOLD,
    seed: int | None = None,
) -> MonteCarloResult:
    """モンテカルロ分析を実行する。

    Args:
        pnl_pips:       トレードごとの損益(pips)リスト（バックテスト結果）
        n_simulations:  シミュレーション回数
        ruin_threshold: 破産とみなす累積損益の閾値（例: -200.0）
        seed:           乱数シード（テスト用）
    """
    rng = random.Random(seed)

    wins_raw = sum(1 for p in pnl_pips if p > 0)
    n = len(pnl_pips)

    raw_cum = _cumulative(pnl_pips)
    raw_total = raw_cum[-1] if raw_cum else 0.0
    raw_dd = _max_drawdown(raw_cum) if raw_cum else 0.0
    raw_wr = round(wins_raw / n * 100, 1) if n > 0 else None

    result = MonteCarloResult(
        n_trades=n,
        n_simulations=n_simulations,
        ruin_threshold=ruin_threshold,
        raw_win_rate=raw_wr,
        raw_total_pips=round(raw_total, 2),
        raw_max_drawdown=raw_dd,
    )

    if n == 0:
        result.assessment = "トレードデータがありません"
        return result

    final_list: list[float] = []
    dd_list: list[float] = []
    ruin_count = 0
    profit_count = 0

    for _ in range(n_simulations):
        shuffled = pnl_pips[:]
        rng.shuffle(shuffled)
        cum = _cumulative(shuffled)
        final = cum[-1]
        dd = _max_drawdown(cum)

        final_list.append(final)
        dd_list.append(dd)
        if final <= ruin_threshold:
            ruin_count += 1
        if final > 0:
            profit_count += 1

    result.final_pips = _percentile_stats(final_list)
    result.max_drawdown = _percentile_stats(dd_list)
    result.ruin_probability = round(ruin_count / n_simulations, 4)
    result.profit_probability = round(profit_count / n_simulations, 4)

    ci_lo, ci_hi = _wilson_ci(wins_raw, n)
    result.win_rate_ci_lower = ci_lo
    result.win_rate_ci_upper = ci_hi

    result.assessment = _assess(result)
    return result


def _assess(r: MonteCarloResult) -> str:
    """モンテカルロ結果を日本語で評価する。"""
    parts = []

    if r.ruin_probability <= 0.05:
        parts.append("破産リスク: 低（≤ 5%）")
    elif r.ruin_probability <= 0.20:
        parts.append("破産リスク: 中（5〜20%）")
    else:
        parts.append("破産リスク: 高（> 20%）")

    if r.profit_probability >= 0.70:
        parts.append("収益期待: 高（≥ 70%）")
    elif r.profit_probability >= 0.50:
        parts.append("収益期待: 中（50〜70%）")
    else:
        parts.append("収益期待: 低（< 50%）")

    if r.final_pips is not None:
        p50 = r.final_pips.p50
        if p50 > 0:
            parts.append(f"中央値損益: +{p50:.1f}pips（プラス）")
        else:
            parts.append(f"中央値損益: {p50:.1f}pips（マイナス）")

    return " / ".join(parts) if parts else "評価データ不足"


def get_pnl_pips_from_db(
    symbol: str | None = None,
    is_simulation: bool | None = None,
    db_path: Path | None = None,
) -> list[float]:
    """DBからクローズ済みトレードの損益(pips)リストを取得する。

    Args:
        symbol:        通貨ペア（None = 全ペア）
        is_simulation: True = バックテスト結果のみ、False = 実承認のみ、None = 両方
        db_path:       DBパス（テスト用）
    """
    conditions = ["outcome IN ('win', 'loss')", "pnl_pips IS NOT NULL"]
    params: list = []

    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol)

    if is_simulation is True:
        conditions.append("is_dummy_data = 1")
    elif is_simulation is False:
        conditions.append("is_dummy_data = 0")

    where = " AND ".join(conditions)
    sql = f"SELECT pnl_pips FROM approval_history WHERE {where} ORDER BY created_at ASC"

    with get_db(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [float(r["pnl_pips"]) for r in rows]
