"""Phase 61: 連勝・連敗ストリーク分析（Win/Loss Streak Analysis）

取引履歴から連勝・連敗の流れを分析し、現在のストリーク・過去最大・
ストリーク長の分布を集計する。注文は一切発生しない。集計・可視化のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.config import DB_PATH
from app.database.db import get_db


@dataclass
class StreakRun:
    """連続した同一 outcome のひとかたまり。"""
    outcome: str    # "win" | "loss"
    length: int
    start_index: int


@dataclass
class StreakReport:
    symbol: str | None
    total_trades: int

    # Current streak
    current_outcome: str | None = None   # "win" | "loss" | None
    current_streak: int = 0

    # All-time bests
    max_win_streak: int = 0
    max_loss_streak: int = 0

    # Average streak lengths (across all completed runs)
    avg_win_streak: float | None = None
    avg_loss_streak: float | None = None

    # Distribution: how many runs of length 1, 2, 3, 4, 5+
    win_streak_dist: list[int] = field(default_factory=list)   # index 0 = length 1
    loss_streak_dist: list[int] = field(default_factory=list)  # index 0 = length 1

    # Chart series for streak-over-time (running streak value; positive=win, negative=loss)
    timeline_labels: list[str] = field(default_factory=list)   # trade index labels
    streak_timeline: list[int] = field(default_factory=list)   # signed streak value

    # All completed runs (for table)
    runs: list[StreakRun] = field(default_factory=list)

    DIST_MAX = 5   # bucket lengths 1..4 individually, 5+ together


def _parse_dt(text: str) -> datetime | None:
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:n], fmt)
        except ValueError:
            continue
    return None


def _build_dist(runs: list[StreakRun], outcome: str, dist_max: int) -> list[int]:
    """指定 outcome の run 長さ分布を返す（長さ 1..dist_max-1 個別, dist_max+ まとめ）。"""
    dist = [0] * dist_max
    for r in runs:
        if r.outcome == outcome:
            idx = min(r.length, dist_max) - 1
            dist[idx] += 1
    return dist


def get_streak_report(
    symbol: str | None = None,
    db_path=None,
) -> StreakReport:
    """連勝・連敗ストリークレポートを返す。注文は発生しない。"""
    path = db_path or DB_PATH
    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy_approved', 'sell_approved')",
        "pnl_pips IS NOT NULL",
    ]
    params: list = []

    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    with get_db(path) as conn:
        rows = conn.execute(
            f"SELECT created_at, outcome "
            f"FROM approval_history WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at ASC",
            params,
        ).fetchall()

    report = StreakReport(symbol=symbol, total_trades=len(rows))

    if not rows:
        dist_max = StreakReport.DIST_MAX
        report.win_streak_dist = [0] * dist_max
        report.loss_streak_dist = [0] * dist_max
        return report

    outcomes = [str(r["outcome"]) for r in rows]

    # Build streak runs
    runs: list[StreakRun] = []
    current_outcome = outcomes[0]
    current_len = 1
    start_idx = 0

    for i, oc in enumerate(outcomes[1:], start=1):
        if oc == current_outcome:
            current_len += 1
        else:
            runs.append(StreakRun(outcome=current_outcome, length=current_len, start_index=start_idx))
            current_outcome = oc
            current_len = 1
            start_idx = i

    # Last run (still open / current)
    runs.append(StreakRun(outcome=current_outcome, length=current_len, start_index=start_idx))

    report.runs = runs

    # Current streak = last run
    report.current_outcome = runs[-1].outcome
    report.current_streak = runs[-1].length

    # Max streaks
    report.max_win_streak = max((r.length for r in runs if r.outcome == "win"), default=0)
    report.max_loss_streak = max((r.length for r in runs if r.outcome == "loss"), default=0)

    # Average streak lengths (exclude current ongoing run for unbiased estimate)
    completed = runs[:-1]
    win_runs_c = [r.length for r in completed if r.outcome == "win"]
    loss_runs_c = [r.length for r in completed if r.outcome == "loss"]
    report.avg_win_streak = round(sum(win_runs_c) / len(win_runs_c), 2) if win_runs_c else None
    report.avg_loss_streak = round(sum(loss_runs_c) / len(loss_runs_c), 2) if loss_runs_c else None

    # Distribution (all runs including current)
    dist_max = StreakReport.DIST_MAX
    report.win_streak_dist = _build_dist(runs, "win", dist_max)
    report.loss_streak_dist = _build_dist(runs, "loss", dist_max)

    # Streak timeline: running signed streak value (+N win, -N loss)
    signed: list[int] = []
    running = 0
    prev_oc = None
    for oc in outcomes:
        if oc == prev_oc:
            running = (running + 1) if oc == "win" else (running - 1)
        else:
            running = 1 if oc == "win" else -1
        signed.append(running)
        prev_oc = oc

    report.streak_timeline = signed
    report.timeline_labels = [str(i + 1) for i in range(len(outcomes))]

    return report
