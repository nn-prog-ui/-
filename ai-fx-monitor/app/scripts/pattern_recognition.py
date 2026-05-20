"""Phase 49: トレードパターン認識

エントリー条件（RSI帯・トレンド組み合わせ・スコア・時間帯・シグナル種別）を
クラスタリングして、パターン別の勝率・損益統計を提供する。

注文は発生しない。集計・分析のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db


@dataclass
class PatternCluster:
    """1パターン（クラスタ）の統計。"""
    pattern_key: str    # 内部識別キー
    label: str          # 表示ラベル
    category: str       # "signal" / "rsi" / "trend" / "score" / "session"
    trades: int
    win_count: int
    loss_count: int
    win_rate: float | None
    total_pips: float
    avg_pips: float | None
    profit_factor: float | None


@dataclass
class PatternReport:
    by_signal: list[PatternCluster] = field(default_factory=list)
    by_rsi: list[PatternCluster] = field(default_factory=list)
    by_trend: list[PatternCluster] = field(default_factory=list)
    by_score: list[PatternCluster] = field(default_factory=list)
    by_session: list[PatternCluster] = field(default_factory=list)
    total_closed: int = 0


def _rsi_bucket(rsi: float | None) -> str:
    if rsi is None:
        return "不明"
    if rsi < 30:
        return "売られ過ぎ (<30)"
    if rsi < 40:
        return "30–40"
    if rsi < 50:
        return "40–50"
    if rsi < 60:
        return "50–60"
    if rsi < 70:
        return "60–70"
    return "買われ過ぎ (≥70)"


_RSI_ORDER = [
    "売られ過ぎ (<30)", "30–40", "40–50",
    "50–60", "60–70", "買われ過ぎ (≥70)", "不明",
]


def _session_label(created_at: str) -> str:
    """JST 時刻からセッション名を返す（UTC+9 簡易変換）。"""
    try:
        hour_utc = int(created_at[11:13])
        hour_jst = (hour_utc + 9) % 24
    except (IndexError, ValueError):
        return "不明"
    if 0 <= hour_jst < 7:
        return "深夜 (0–7時)"
    if 7 <= hour_jst < 10:
        return "東京午前 (7–10時)"
    if 10 <= hour_jst < 16:
        return "東京午後 (10–16時)"
    if 16 <= hour_jst < 22:
        return "欧州 (16–22時)"
    return "NY (22–24時)"


_SESSION_ORDER = [
    "東京午前 (7–10時)", "東京午後 (10–16時)",
    "欧州 (16–22時)", "NY (22–24時)", "深夜 (0–7時)", "不明",
]


def _make_cluster(
    key: str, label: str, category: str, group: list
) -> PatternCluster:
    wins = [r for r in group if r["outcome"] == "win"]
    losses = [r for r in group if r["outcome"] == "loss"]
    n = len(group)
    win_pips = sum(float(r["pnl_pips"] or 0) for r in wins)
    loss_pips = sum(abs(float(r["pnl_pips"] or 0)) for r in losses)
    total_pips = sum(float(r["pnl_pips"] or 0) for r in group)
    win_rate = (len(wins) / n * 100) if n > 0 else None
    avg_pips = (total_pips / n) if n > 0 else None
    pf = (win_pips / loss_pips) if loss_pips > 0 else None
    return PatternCluster(
        pattern_key=key,
        label=label,
        category=category,
        trades=n,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=round(win_rate, 1) if win_rate is not None else None,
        total_pips=round(total_pips, 2),
        avg_pips=round(avg_pips, 2) if avg_pips is not None else None,
        profit_factor=round(pf, 2) if pf is not None else None,
    )


def get_pattern_report(
    symbol: str | None = None,
    db_path=None,
) -> PatternReport:
    """エントリー条件別パターン統計レポートを返す。"""
    path = db_path or DB_PATH
    clauses = [
        "human_action IN ('buy_approved', 'sell_approved')",
        "outcome IN ('win', 'loss')",
    ]
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    where = " AND ".join(clauses)
    sql = f"""
        SELECT created_at, symbol, human_action, signal, outcome,
               pnl_pips, score, rsi, daily_trend, h4_trend
        FROM approval_history
        WHERE {where}
        ORDER BY created_at ASC
    """

    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()

    if not rows:
        return PatternReport(total_closed=0)

    total_closed = len(rows)

    # ── 1. シグナル種別 ──────────────────────────────────────────
    sig_groups: dict[str, list] = {}
    for r in rows:
        sig = r["signal"] or ("BUY" if r["human_action"] == "buy_approved" else "SELL")
        sig_groups.setdefault(sig, []).append(r)

    by_signal = [
        _make_cluster(sig, sig, "signal", grp)
        for sig, grp in sorted(sig_groups.items())
    ]

    # ── 2. RSI帯 ─────────────────────────────────────────────────
    rsi_groups: dict[str, list] = {}
    for r in rows:
        bucket = _rsi_bucket(r["rsi"])
        rsi_groups.setdefault(bucket, []).append(r)

    by_rsi = [
        _make_cluster(b, b, "rsi", rsi_groups[b])
        for b in _RSI_ORDER if b in rsi_groups
    ]

    # ── 3. トレンド組み合わせ ─────────────────────────────────────
    trend_groups: dict[str, list] = {}
    for r in rows:
        daily = r["daily_trend"] or "不明"
        h4 = r["h4_trend"] or "不明"
        key = f"{daily} / {h4}"
        trend_groups.setdefault(key, []).append(r)

    by_trend = sorted(
        [
            _make_cluster(k, k, "trend", grp)
            for k, grp in trend_groups.items()
        ],
        key=lambda c: c.trades,
        reverse=True,
    )

    # ── 4. スコア帯 ───────────────────────────────────────────────
    score_groups: dict[str, list] = {}
    for r in rows:
        sc = r["score"]
        key = f"スコア {sc}" if sc is not None else "スコア不明"
        score_groups.setdefault(key, []).append(r)

    score_order = [f"スコア {i}" for i in range(6)] + ["スコア不明"]
    by_score = [
        _make_cluster(k, k, "score", score_groups[k])
        for k in score_order if k in score_groups
    ]

    # ── 5. 時間帯（セッション） ───────────────────────────────────
    session_groups: dict[str, list] = {}
    for r in rows:
        sess = _session_label(r["created_at"])
        session_groups.setdefault(sess, []).append(r)

    by_session = [
        _make_cluster(s, s, "session", session_groups[s])
        for s in _SESSION_ORDER if s in session_groups
    ]

    return PatternReport(
        by_signal=by_signal,
        by_rsi=by_rsi,
        by_trend=by_trend,
        by_score=by_score,
        by_session=by_session,
        total_closed=total_closed,
    )
