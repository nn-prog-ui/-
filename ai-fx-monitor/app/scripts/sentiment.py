"""Phase 75: ニュースセンチメント集計

geopolitical_log テーブルに記録された AI 地政学分析の結果を集計し、
センチメント傾向（ドル高/ドル安/中立）をグラフ用データとして返す。
自動注文は発生しない。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db

# ── USD 影響グループ分類 ─────────────────────────────────────────────────

_BULLISH_GROUP = {"bullish", "strong_bullish"}
_BEARISH_GROUP = {"bearish", "strong_bearish"}
_NEUTRAL_GROUP = {"neutral"}


def _classify(usd_impact: str) -> str:
    """usd_impact 文字列を 'bullish' / 'bearish' / 'neutral' に正規化する。"""
    if usd_impact in _BULLISH_GROUP:
        return "bullish"
    if usd_impact in _BEARISH_GROUP:
        return "bearish"
    return "neutral"


# ── データクラス ────────────────────────────────────────────────────────

@dataclass
class SentimentSummary:
    """全体センチメントサマリー。"""
    total: int = 0
    bullish: int = 0
    bearish: int = 0
    neutral: int = 0
    strong_bullish: int = 0
    strong_bearish: int = 0
    bullish_pct: float = 0.0
    bearish_pct: float = 0.0
    neutral_pct: float = 0.0


@dataclass
class CategorySentiment:
    """カテゴリー別センチメント。"""
    category: str = ""
    total: int = 0
    bullish: int = 0
    bearish: int = 0
    neutral: int = 0
    bullish_pct: float = 0.0
    bearish_pct: float = 0.0


@dataclass
class DailySentiment:
    """日別センチメントポイント（グラフ用）。"""
    date: str = ""           # "YYYY-MM-DD"
    bullish: int = 0
    bearish: int = 0
    neutral: int = 0
    net_score: int = 0       # bullish - bearish


@dataclass
class TopEvent:
    """影響が大きかったイベント（strong 系）。"""
    event_date: str = ""
    category: str = ""
    usd_impact: str = ""
    event_text: str = ""
    confidence: str = ""
    ai_provider: str = ""


@dataclass
class SentimentReport:
    """センチメントページ用の集計レポート。"""
    summary: SentimentSummary = field(default_factory=SentimentSummary)
    categories: list[CategorySentiment] = field(default_factory=list)
    daily: list[DailySentiment] = field(default_factory=list)
    top_events: list[TopEvent] = field(default_factory=list)
    total_days: int = 0        # データのある日数
    date_from: str = ""
    date_to: str = ""


# ── 集計ロジック ────────────────────────────────────────────────────────

def _pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def get_sentiment_report(db_path=None, days: int = 90) -> SentimentReport:
    """geopolitical_log から センチメントレポートを生成する。

    Args:
        db_path: DBパス（Noneの場合はデフォルト）
        days: 集計対象の日数（デフォルト90日）
    """
    path = db_path or DB_PATH

    try:
        from app.scripts.geopolitical import ensure_table
        ensure_table(path)
    except Exception:
        pass

    try:
        with get_db(path) as conn:
            # 対象期間のレコードを取得
            rows = conn.execute(
                """
                SELECT event_date, category, usd_impact, confidence, event_text, ai_provider
                FROM geopolitical_log
                WHERE event_date >= date('now', ? || ' days')
                ORDER BY event_date ASC
                """,
                (f"-{days}",),
            ).fetchall()
    except Exception:
        return SentimentReport()

    if not rows:
        return SentimentReport()

    # ── 全体サマリー ──────────────────────────────────────────────────
    summary = SentimentSummary()
    summary.total = len(rows)
    for r in rows:
        impact = r["usd_impact"]
        if impact == "strong_bullish":
            summary.strong_bullish += 1
            summary.bullish += 1
        elif impact == "bullish":
            summary.bullish += 1
        elif impact == "strong_bearish":
            summary.strong_bearish += 1
            summary.bearish += 1
        elif impact == "bearish":
            summary.bearish += 1
        else:
            summary.neutral += 1
    summary.bullish_pct = _pct(summary.bullish, summary.total)
    summary.bearish_pct = _pct(summary.bearish, summary.total)
    summary.neutral_pct = _pct(summary.neutral, summary.total)

    # ── カテゴリー別 ──────────────────────────────────────────────────
    cat_map: dict[str, CategorySentiment] = {}
    for r in rows:
        cat = r["category"]
        if cat not in cat_map:
            cat_map[cat] = CategorySentiment(category=cat)
        cs = cat_map[cat]
        cs.total += 1
        group = _classify(r["usd_impact"])
        if group == "bullish":
            cs.bullish += 1
        elif group == "bearish":
            cs.bearish += 1
        else:
            cs.neutral += 1

    for cs in cat_map.values():
        cs.bullish_pct = _pct(cs.bullish, cs.total)
        cs.bearish_pct = _pct(cs.bearish, cs.total)

    # 件数降順でソート
    categories = sorted(cat_map.values(), key=lambda c: c.total, reverse=True)

    # ── 日別センチメント ──────────────────────────────────────────────
    day_map: dict[str, DailySentiment] = {}
    for r in rows:
        d = r["event_date"][:10]  # "YYYY-MM-DD"
        if d not in day_map:
            day_map[d] = DailySentiment(date=d)
        ds = day_map[d]
        group = _classify(r["usd_impact"])
        if group == "bullish":
            ds.bullish += 1
        elif group == "bearish":
            ds.bearish += 1
        else:
            ds.neutral += 1

    for ds in day_map.values():
        ds.net_score = ds.bullish - ds.bearish

    daily = sorted(day_map.values(), key=lambda d: d.date)

    # ── TOP イベント（strong 系のみ、最大10件、新しい順） ───────────────
    top_events: list[TopEvent] = []
    for r in reversed(rows):  # rows は日付昇順なので reversed で新しい順
        if r["usd_impact"] in ("strong_bullish", "strong_bearish"):
            top_events.append(TopEvent(
                event_date=r["event_date"][:10],
                category=r["category"],
                usd_impact=r["usd_impact"],
                event_text=r["event_text"],
                confidence=r["confidence"],
                ai_provider=r["ai_provider"],
            ))
        if len(top_events) >= 10:
            break

    dates = [r["event_date"][:10] for r in rows]

    return SentimentReport(
        summary=summary,
        categories=categories,
        daily=daily,
        top_events=top_events,
        total_days=len(day_map),
        date_from=min(dates) if dates else "",
        date_to=max(dates) if dates else "",
    )
