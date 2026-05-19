"""Phase 46: シグナル品質スコアリング

過去の取引履歴から、現在のシグナル条件（スコア・RSI・トレンド一致）と
同じパターンの勝率を計算し、品質ラベル（S/A/B/C/D）を付与する。

注文は一切発生しない。分析・集計のみ。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import DB_PATH, SUPPORTED_SYMBOLS
from app.database.db import get_db

# 品質ラベル（勝率ベース）
QUALITY_LABELS: dict[int, str] = {5: "S", 4: "A", 3: "B", 2: "C", 1: "D", 0: "N/A"}
QUALITY_CSS: dict[int, str] = {
    5: "quality-s",
    4: "quality-a",
    3: "quality-b",
    2: "quality-c",
    1: "quality-d",
    0: "quality-na",
}
QUALITY_DESCRIPTIONS: dict[int, str] = {
    5: "非常に高い信頼性（過去勝率65%以上）",
    4: "高い信頼性（過去勝率55%以上）",
    3: "中程度の信頼性（過去勝率45%以上）",
    2: "低い信頼性（過去勝率35%以上）",
    1: "非常に低い信頼性（過去勝率35%未満）",
    0: "データ不足（参考値なし）",
}

# 勝率→品質レベル閾値
_WIN_RATE_THRESHOLDS = [(65.0, 5), (55.0, 4), (45.0, 3), (35.0, 2)]
MIN_TRADES_FOR_QUALITY = 3


def _score_bucket(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score >= 4:
        return "high"
    if score >= 1:
        return "mid"
    return "low"


def _rsi_bucket(rsi: float | None) -> str:
    if rsi is None:
        return "unknown"
    if rsi < 40:
        return "oversold"
    if rsi > 60:
        return "overbought"
    return "neutral"


def _trend_match(daily_trend: str | None, h4_trend: str | None) -> str:
    if not daily_trend or not h4_trend:
        return "unknown"
    return "aligned" if daily_trend == h4_trend else "mixed"


def _quality_level(win_rate: float | None, trades: int) -> int:
    if trades < MIN_TRADES_FOR_QUALITY or win_rate is None:
        return 0
    for threshold, level in _WIN_RATE_THRESHOLDS:
        if win_rate >= threshold:
            return level
    return 1


@dataclass
class QualityStats:
    dimension: str             # マッチしたパターンの説明
    trades: int                # 対象取引数
    wins: int                  # 勝ち数
    win_rate: float | None     # 勝率 (0〜100)
    avg_pips: float | None     # 平均損益
    quality_label: str         # S/A/B/C/D/N/A
    quality_level: int         # 5/4/3/2/1/0
    quality_description: str   # 品質の説明テキスト
    score_bucket: str          # high/mid/low/unknown
    rsi_bucket: str            # oversold/neutral/overbought/unknown
    trend_match: str           # aligned/mixed/unknown


def _query_stats(
    conn,
    human_action: str,
    symbol: str | None,
    extra_clauses: list[str],
    extra_params: list,
) -> tuple[int, int, float | None]:
    """指定条件で取引統計を返す (trades, wins, avg_pips)。"""
    clauses = [
        "human_action = ?",
        "outcome IS NOT NULL",
    ]
    params: list = [human_action]

    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    clauses.extend(extra_clauses)
    params.extend(extra_params)

    where = " AND ".join(clauses)
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS trades,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
            AVG(pnl_pips) AS avg_pips
        FROM approval_history
        WHERE {where}
        """,
        params,
    ).fetchone()

    trades = row["trades"] or 0
    wins = row["wins"] or 0
    avg_pips = row["avg_pips"]
    return trades, wins, avg_pips


def get_signal_quality(
    symbol: str,
    signal: str,
    score: int | None = None,
    rsi: float | None = None,
    daily_trend: str | None = None,
    h4_trend: str | None = None,
    db_path=None,
) -> QualityStats:
    """現在のシグナル条件と最も近い過去パターンの品質を返す。

    最も具体的な条件から順に照合し、十分なデータがある最初のレベルを採用する。
    signal は "BUY" / "SELL" のみ対応（SKIP は N/A を返す）。
    """
    sb = _score_bucket(score)
    rb = _rsi_bucket(rsi)
    tm = _trend_match(daily_trend, h4_trend)

    if signal == "BUY":
        action = "buy"
    elif signal == "SELL":
        action = "sell"
    else:
        return QualityStats(
            dimension="シグナルなし",
            trades=0, wins=0, win_rate=None, avg_pips=None,
            quality_label="N/A", quality_level=0,
            quality_description=QUALITY_DESCRIPTIONS[0],
            score_bucket=sb, rsi_bucket=rb, trend_match=tm,
        )

    path = db_path or DB_PATH

    # 照合レベル: 具体 → 抽象
    candidates: list[tuple[str, list[str], list]] = []

    if sb != "unknown" and rb != "unknown" and tm != "unknown":
        candidates.append((
            f"{symbol} {signal} スコア{sb}/RSI{rb}/トレンド{tm}",
            ["score_bucket = ?", "rsi_bucket = ?", "trend_match = ?"],
            [sb, rb, tm],
        ))
    if sb != "unknown" and tm != "unknown":
        candidates.append((
            f"{symbol} {signal} スコア{sb}/トレンド{tm}",
            ["score_bucket = ?", "trend_match = ?"],
            [sb, tm],
        ))
    if sb != "unknown" and rb != "unknown":
        candidates.append((
            f"{symbol} {signal} スコア{sb}/RSI{rb}",
            ["score_bucket = ?", "rsi_bucket = ?"],
            [sb, rb],
        ))
    if sb != "unknown":
        candidates.append((
            f"{symbol} {signal} スコア{sb}",
            ["score_bucket = ?"],
            [sb],
        ))
    # 最も抽象的: symbol + signal のみ
    candidates.append((
        f"{symbol} {signal} 全体",
        [],
        [],
    ))

    with get_db(path) as conn:
        # score_bucket / rsi_bucket / trend_match 列が存在するか確認
        cols = {row[1] for row in conn.execute("PRAGMA table_info(approval_history)").fetchall()}
        has_extra_cols = {"score_bucket", "rsi_bucket", "trend_match"}.issubset(cols)

        chosen_dim = f"{symbol} {signal} 全体"
        chosen_trades = 0
        chosen_wins = 0
        chosen_avg_pips = None

        for dim, extra_clauses, extra_params in candidates:
            # 拡張列がない場合は基本クエリのみ
            if extra_clauses and not has_extra_cols:
                continue
            t, w, avg = _query_stats(conn, action, symbol, extra_clauses, extra_params)
            if t >= MIN_TRADES_FOR_QUALITY:
                chosen_dim = dim
                chosen_trades = t
                chosen_wins = w
                chosen_avg_pips = avg
                break

        # フォールバック: データが少なくても最も抽象レベルを返す
        if chosen_trades == 0:
            t, w, avg = _query_stats(conn, action, symbol, [], [])
            chosen_dim = f"{symbol} {signal} 全体"
            chosen_trades = t
            chosen_wins = w
            chosen_avg_pips = avg

    win_rate = (chosen_wins / chosen_trades * 100) if chosen_trades > 0 else None
    level = _quality_level(win_rate, chosen_trades)

    return QualityStats(
        dimension=chosen_dim,
        trades=chosen_trades,
        wins=chosen_wins,
        win_rate=win_rate,
        avg_pips=float(chosen_avg_pips) if chosen_avg_pips is not None else None,
        quality_label=QUALITY_LABELS[level],
        quality_level=level,
        quality_description=QUALITY_DESCRIPTIONS[level],
        score_bucket=sb,
        rsi_bucket=rb,
        trend_match=tm,
    )


def get_all_pattern_stats(
    symbol: str | None = None,
    db_path=None,
) -> list[dict]:
    """全シグナルパターンの統計一覧を返す（分析ページ用）。"""
    path = db_path or DB_PATH
    clauses = ["outcome IS NOT NULL", "human_action IN ('buy', 'sell')"]
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    where = " AND ".join(clauses)
    sql = f"""
        SELECT
            symbol,
            human_action,
            signal,
            daily_trend,
            h4_trend,
            COUNT(*) AS trades,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
            AVG(pnl_pips) AS avg_pips
        FROM approval_history
        WHERE {where}
        GROUP BY symbol, human_action, signal, daily_trend, h4_trend
        ORDER BY trades DESC
    """

    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()

    results = []
    for row in rows:
        trades = row["trades"] or 0
        wins = row["wins"] or 0
        win_rate = (wins / trades * 100) if trades > 0 else None
        level = _quality_level(win_rate, trades)
        results.append({
            "symbol": row["symbol"],
            "signal": row["signal"],
            "daily_trend": row["daily_trend"],
            "h4_trend": row["h4_trend"],
            "trades": trades,
            "wins": wins,
            "win_rate": win_rate,
            "avg_pips": row["avg_pips"],
            "quality_label": QUALITY_LABELS[level],
            "quality_level": level,
        })
    return results
