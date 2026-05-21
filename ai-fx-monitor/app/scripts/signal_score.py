"""Phase 56: シグナルスコア分析（Signal Score Analysis）

シグナルスコア（1〜5）と実トレード結果の相関を集計・可視化する。
高スコアほど勝率・期待値が高いか（予測力）を検証する。
注文は一切発生しない。集計・可視化のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db

SCORE_RANGE = range(1, 6)   # 1〜5


@dataclass
class ScoreBucket:
    score: int
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pips: float = 0.0
    win_rate: float | None = None       # None if no trades
    expectancy: float | None = None
    profit_factor: float | None = None
    avg_pips: float | None = None


@dataclass
class ScoreReport:
    symbol: str | None
    total_trades: int
    buckets: list[ScoreBucket] = field(default_factory=list)
    # chart series (index = score-1, i.e. score 1..5)
    score_labels: list[str] = field(default_factory=list)   # ["1", "2", "3", "4", "5"]
    win_rate_series: list[float | None] = field(default_factory=list)
    expectancy_series: list[float | None] = field(default_factory=list)
    trade_count_series: list[int] = field(default_factory=list)
    profit_factor_series: list[float | None] = field(default_factory=list)
    # calibration assessment
    is_calibrated: bool | None = None   # None = insufficient data
    calibration_label: str = ""
    # best / worst score
    best_score: int | None = None
    worst_score: int | None = None


def _assess_calibration(buckets: list[ScoreBucket]) -> tuple[bool | None, str]:
    """高スコアほど期待値が高い（単調増加）かを検証。"""
    filled = [b for b in buckets if b.expectancy is not None and b.trades >= 3]
    if len(filled) < 3:
        return None, "データ不足（各スコア 3 件以上必要）"

    # Spearman-like: count concordant vs discordant pairs
    concordant = 0
    discordant = 0
    for i in range(len(filled)):
        for j in range(i + 1, len(filled)):
            s_diff = filled[j].score - filled[i].score
            e_diff = (filled[j].expectancy or 0.0) - (filled[i].expectancy or 0.0)
            if s_diff * e_diff > 0:
                concordant += 1
            elif s_diff * e_diff < 0:
                discordant += 1

    total_pairs = concordant + discordant
    if total_pairs == 0:
        return None, "判定不能"

    rho = (concordant - discordant) / total_pairs  # -1..+1
    if rho >= 0.5:
        return True, f"スコアと期待値に正の相関あり（ρ={rho:.2f}）。高スコアが有効です。"
    elif rho <= -0.3:
        return False, f"スコアと期待値に負の相関（ρ={rho:.2f}）。スコア基準の見直しを検討してください。"
    else:
        return False, f"スコアと期待値に明確な相関なし（ρ={rho:.2f}）。フィルター効果が弱い可能性があります。"


def get_score_report(
    symbol: str | None = None,
    db_path=None,
) -> ScoreReport:
    """スコア別成績レポートを返す。注文は発生しない。"""
    path = db_path or DB_PATH
    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy_approved', 'sell_approved')",
        "pnl_pips IS NOT NULL",
        "score IS NOT NULL",
    ]
    params: list = []

    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    with get_db(path) as conn:
        rows = conn.execute(
            f"SELECT score, outcome, pnl_pips FROM approval_history "
            f"WHERE {' AND '.join(clauses)} ORDER BY score ASC",
            params,
        ).fetchall()

    report = ScoreReport(symbol=symbol, total_trades=len(rows))

    # Initialize buckets for scores 1..5
    buckets: dict[int, ScoreBucket] = {s: ScoreBucket(score=s) for s in SCORE_RANGE}

    for row in rows:
        score = int(row["score"])
        if score not in buckets:
            continue
        b = buckets[score]
        b.trades += 1
        pnl = float(row["pnl_pips"])
        b.total_pips += pnl
        if row["outcome"] == "win":
            b.wins += 1
        else:
            b.losses += 1

    for b in buckets.values():
        if b.trades > 0:
            b.win_rate = round(b.wins / b.trades * 100, 1)
            b.expectancy = round(b.total_pips / b.trades, 2)
            b.avg_pips = b.expectancy
            gross_profit = sum(
                float(row["pnl_pips"])
                for row in rows
                if int(row["score"]) == b.score and float(row["pnl_pips"]) > 0
            )
            gross_loss = abs(sum(
                float(row["pnl_pips"])
                for row in rows
                if int(row["score"]) == b.score and float(row["pnl_pips"]) < 0
            ))
            b.profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else None

    report.buckets = [buckets[s] for s in SCORE_RANGE]

    # Chart series
    report.score_labels = [str(s) for s in SCORE_RANGE]
    for s in SCORE_RANGE:
        b = buckets[s]
        report.win_rate_series.append(b.win_rate)
        report.expectancy_series.append(b.expectancy)
        report.trade_count_series.append(b.trades)
        report.profit_factor_series.append(b.profit_factor)

    # Calibration
    report.is_calibrated, report.calibration_label = _assess_calibration(report.buckets)

    # Best / worst by expectancy (min 3 trades)
    active = [b for b in report.buckets if b.trades >= 3 and b.expectancy is not None]
    if active:
        report.best_score = max(active, key=lambda b: b.expectancy or 0.0).score
        report.worst_score = min(active, key=lambda b: b.expectancy or 0.0).score

    return report
