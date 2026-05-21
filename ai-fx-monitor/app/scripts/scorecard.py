"""Phase 53: システムスコアカード

勝率・期待値・SQN・ドローダウン・プロフィットファクター等の指標を
レターグレード（A〜F）で評価し、総合スコアを算出する。
注文は発生しない。集計・分析のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db


# ── グレード定義 ────────────────────────────────────────────────────

GRADES = ("A", "B", "C", "D", "F")
GRADE_COLORS = {
    "A": "#4ade80",
    "B": "#60a5fa",
    "C": "#fbbf24",
    "D": "#fb923c",
    "F": "#f87171",
    "N/A": "#666",
}
GRADE_SCORE = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1, "N/A": 0}


@dataclass
class MetricGrade:
    name: str           # 指標名（日本語）
    key: str            # 識別キー
    value: float | None
    unit: str           # "%" / "pips" / "" など
    grade: str          # "A" / "B" / "C" / "D" / "F" / "N/A"
    comment: str        # 一言コメント


@dataclass
class Scorecard:
    symbol: str | None
    metrics: list[MetricGrade]
    overall_grade: str          # 加重平均グレード
    overall_score: float        # 1〜5
    total_trades: int
    recommendation: str         # 改善提案テキスト
    radar_labels: list[str] = field(default_factory=list)
    radar_values: list[float] = field(default_factory=list)  # 0〜5 (グレードスコア)


# ── グレーディング関数 ──────────────────────────────────────────────

def _grade_win_rate(v: float | None) -> tuple[str, str]:
    if v is None:
        return "N/A", "データ不足"
    if v >= 60:
        return "A", "非常に高い勝率"
    if v >= 52:
        return "B", "良好な勝率"
    if v >= 45:
        return "C", "平均的"
    if v >= 38:
        return "D", "改善が必要"
    return "F", "勝率が低すぎます"


def _grade_expectancy(v: float | None) -> tuple[str, str]:
    """期待値 (pips/トレード)"""
    if v is None:
        return "N/A", "データ不足"
    if v >= 5:
        return "A", "強い期待値"
    if v >= 2:
        return "B", "良好な期待値"
    if v > 0:
        return "C", "わずかにプラス"
    if v > -2:
        return "D", "期待値がほぼゼロ"
    return "F", "負の期待値"


def _grade_profit_factor(v: float | None) -> tuple[str, str]:
    if v is None:
        return "N/A", "データ不足"
    if v >= 2.0:
        return "A", "優秀なPF"
    if v >= 1.5:
        return "B", "良好なPF"
    if v >= 1.1:
        return "C", "わずかにプラス"
    if v >= 0.9:
        return "D", "損益がほぼ均衡"
    return "F", "損失超過"


def _grade_max_drawdown_pct(v: float | None) -> tuple[str, str]:
    """最大ドローダウン %（小さいほど良い）"""
    if v is None:
        return "N/A", "データ不足"
    if v <= 5:
        return "A", "ドローダウン小"
    if v <= 10:
        return "B", "許容範囲内"
    if v <= 20:
        return "C", "要注意"
    if v <= 30:
        return "D", "リスク高"
    return "F", "危険なドローダウン"


def _grade_sqn(v: float | None) -> tuple[str, str]:
    """System Quality Number"""
    if v is None:
        return "N/A", "30件未満でSQN算出不可"
    if v >= 3.0:
        return "A", "Excellent"
    if v >= 2.0:
        return "B", "Good"
    if v >= 1.6:
        return "C", "Average"
    if v > 0:
        return "D", "Poor"
    return "F", "負のSQN"


def _grade_recovery_factor(v: float | None) -> tuple[str, str]:
    if v is None:
        return "N/A", "データ不足"
    if v >= 3.0:
        return "A", "高いRF"
    if v >= 2.0:
        return "B", "良好"
    if v >= 1.0:
        return "C", "普通"
    if v > 0:
        return "D", "低め"
    return "F", "損失回収困難"


def _grade_win_streak(v: float | None) -> tuple[str, str]:
    """最大連勝数"""
    if v is None:
        return "N/A", "データ不足"
    if v >= 8:
        return "A", "強いトレンド追随力"
    if v >= 5:
        return "B", "良好"
    if v >= 3:
        return "C", "普通"
    if v >= 2:
        return "D", "低め"
    return "F", "連勝なし"


def _grade_avg_pips(v: float | None) -> tuple[str, str]:
    """平均損益 (pips/トレード)"""
    if v is None:
        return "N/A", "データ不足"
    if v >= 10:
        return "A", "高い平均利益"
    if v >= 5:
        return "B", "良好"
    if v >= 1:
        return "C", "わずかにプラス"
    if v >= -2:
        return "D", "ほぼ損益ゼロ"
    return "F", "平均でマイナス"


def _grade_monthly_positive_rate(v: float | None) -> tuple[str, str]:
    """プラス月率 (%)"""
    if v is None:
        return "N/A", "データ不足"
    if v >= 75:
        return "A", "安定したプラス月"
    if v >= 60:
        return "B", "良好"
    if v >= 50:
        return "C", "普通"
    if v >= 35:
        return "D", "マイナス月が多め"
    return "F", "損失月が大半"


def _overall_grade(scores: list[int]) -> tuple[str, float]:
    valid = [s for s in scores if s > 0]
    if not valid:
        return "N/A", 0.0
    avg = sum(valid) / len(valid)
    if avg >= 4.5:
        return "A", avg
    if avg >= 3.5:
        return "B", avg
    if avg >= 2.5:
        return "C", avg
    if avg >= 1.5:
        return "D", avg
    return "F", avg


def _make_recommendation(metrics: list[MetricGrade]) -> str:
    """最も低いグレードの指標をもとに改善提案を生成する。"""
    grade_map = {m.key: m for m in metrics if m.grade not in ("N/A",)}
    if not grade_map:
        return "まずトレードを記録して成績を蓄積してください。"

    worst = min(grade_map.values(), key=lambda m: GRADE_SCORE.get(m.grade, 0))
    suggestions = {
        "win_rate": "エントリー条件を見直し、シグナル品質スコアの高い場面のみ入れてください。",
        "expectancy": "損切りを早め、利確を引き伸ばすことで期待値を改善できます。",
        "profit_factor": "損切りを小さくするか、利確ターゲットを大きくしてPFを改善してください。",
        "max_dd": "ポジションサイジングを見直し、1トレードのリスクを減らしてください。",
        "sqn": "取引回数を増やして統計的信頼性を高めるか、システムの改善が必要です。",
        "recovery_factor": "ドローダウン後の回復力を高めるため、連敗時のロットを落としてください。",
        "win_streak": "同一方向の連続シグナル時のフィルタリングを検討してください。",
        "avg_pips": "利確ターゲットを広げてRR比を改善してください。",
        "monthly_positive": "月次でコンスタントにプラスを出すため、月初の成績が悪い場合はロットを落としてください。",
    }
    return suggestions.get(worst.key, "各指標を総合的に見直してください。")


# ── メイン関数 ──────────────────────────────────────────────────────

def get_scorecard(symbol: str | None = None, db_path=None) -> Scorecard:
    """全指標を計算してスコアカードを返す。"""
    path = db_path or DB_PATH

    # ── DB から必要データを一括取得 ──
    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy_approved', 'sell_approved')",
    ]
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    with get_db(path) as conn:
        rows = conn.execute(
            f"""SELECT outcome, pnl_pips, created_at
                FROM approval_history
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at ASC""",
            params,
        ).fetchall()

    n = len(rows)
    if n == 0:
        return Scorecard(
            symbol=symbol,
            metrics=[],
            overall_grade="N/A",
            overall_score=0.0,
            total_trades=0,
            recommendation="まずトレードを記録して成績を蓄積してください。",
        )

    wins = [float(r["pnl_pips"] or 0) for r in rows if r["outcome"] == "win"]
    losses = [abs(float(r["pnl_pips"] or 0)) for r in rows if r["outcome"] == "loss"]
    all_pnl = [float(r["pnl_pips"] or 0) for r in rows]

    win_rate = len(wins) / n * 100 if n > 0 else None
    avg_pips = sum(all_pnl) / n if n > 0 else None
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    total_pips = sum(all_pnl)

    # 期待値
    if avg_win is not None and avg_loss is not None:
        p = len(wins) / n
        expectancy = p * avg_win - (1 - p) * avg_loss
    else:
        expectancy = None

    # プロフィットファクター
    sum_win = sum(wins)
    sum_loss = sum(losses)
    profit_factor = sum_win / sum_loss if sum_loss > 0 else None

    # 最大ドローダウン %
    peak = 0.0
    cum = 0.0
    max_dd_pct: float | None = None
    for pnl in all_pnl:
        cum += pnl
        if cum > peak:
            peak = cum
        dd = (peak - cum) / (peak + 1e-9) * 100
        if max_dd_pct is None or dd > max_dd_pct:
            max_dd_pct = dd

    # リカバリーファクター
    max_dd_pips = None
    peak2, cum2 = 0.0, 0.0
    for pnl in all_pnl:
        cum2 += pnl
        if cum2 > peak2:
            peak2 = cum2
        dd2 = peak2 - cum2
        if max_dd_pips is None or dd2 > max_dd_pips:
            max_dd_pips = dd2
    recovery_factor = (total_pips / max_dd_pips) if (max_dd_pips and max_dd_pips > 0) else None

    # SQN
    import math
    import statistics
    sqn: float | None = None
    if n >= 2 and avg_loss and avg_loss > 0:
        r_vals = [p / avg_loss for p in all_pnl]
        mean_r = statistics.mean(r_vals)
        std_r = statistics.stdev(r_vals) if n >= 2 else None
        if std_r and std_r > 0:
            sqn = round(math.sqrt(n) * mean_r / std_r, 2)

    # 最大連勝
    max_win_streak = 0
    cur = 0
    for r in rows:
        if r["outcome"] == "win":
            cur += 1
            max_win_streak = max(max_win_streak, cur)
        else:
            cur = 0

    # プラス月率
    monthly: dict[str, float] = {}
    for r in rows:
        try:
            from datetime import datetime
            dt = datetime.strptime(str(r["created_at"])[:10], "%Y-%m-%d")
            key = dt.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0) + float(r["pnl_pips"] or 0)
        except Exception:
            continue
    monthly_positive_rate = (
        sum(1 for v in monthly.values() if v > 0) / len(monthly) * 100
        if monthly else None
    )

    # ── グレーディング ──
    def _m(name, key, value, unit, grade_fn):
        g, comment = grade_fn(value)
        fmt_v = round(value, 2) if value is not None else None
        return MetricGrade(name=name, key=key, value=fmt_v, unit=unit, grade=g, comment=comment)

    metrics = [
        _m("勝率",             "win_rate",            win_rate,             "%",     _grade_win_rate),
        _m("期待値",           "expectancy",           expectancy,           "pips",  _grade_expectancy),
        _m("プロフィットF",    "profit_factor",        profit_factor,        "",      _grade_profit_factor),
        _m("最大DD",          "max_dd",               max_dd_pct,           "%",     _grade_max_drawdown_pct),
        _m("SQN",             "sqn",                  sqn,                  "",      _grade_sqn),
        _m("リカバリーF",      "recovery_factor",      recovery_factor,      "",      _grade_recovery_factor),
        _m("最大連勝",         "win_streak",           float(max_win_streak),"連",    _grade_win_streak),
        _m("平均損益",         "avg_pips",             avg_pips,             "pips",  _grade_avg_pips),
        _m("プラス月率",       "monthly_positive",     monthly_positive_rate,"%",     _grade_monthly_positive_rate),
    ]

    scores = [GRADE_SCORE.get(m.grade, 0) for m in metrics]
    overall_grade, overall_score = _overall_grade(scores)
    recommendation = _make_recommendation(metrics)

    radar_labels = [m.name for m in metrics]
    radar_values = [float(GRADE_SCORE.get(m.grade, 0)) for m in metrics]

    return Scorecard(
        symbol=symbol,
        metrics=metrics,
        overall_grade=overall_grade,
        overall_score=round(overall_score, 2),
        total_trades=n,
        recommendation=recommendation,
        radar_labels=radar_labels,
        radar_values=radar_values,
    )
