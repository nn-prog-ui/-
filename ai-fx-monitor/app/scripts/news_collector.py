"""Phase 69: FXニュース自動収集・自動地政学分析

RSS フィードから FX 関連ニュースを自動収集し、地政学リスク分析を実行する。
すべてのネットワーク呼び出しは例外を握りつぶして安全に続行する。
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── RSS ソース一覧 ────────────────────────────────────────────────────────────
RSS_SOURCES: list[dict] = [
    {
        "name": "BBC Business",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
    },
    {
        "name": "MarketWatch",
        "url": "https://feeds.marketwatch.com/marketwatch/topstories/",
    },
    {
        "name": "CNBC Top News",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    },
]

# ── FX 関連キーワード（英語＋日本語） ──────────────────────────────────────
FX_KEYWORDS: list[str] = [
    # 金融政策
    "fed", "federal reserve", "frb", "fomc", "interest rate", "rate hike",
    "rate cut", "quantitative easing", "boj", "bank of japan", "ecb",
    # 通貨・市場
    "usd", "dollar", "yen", "jpy", "forex", "currency", "exchange rate",
    # 経済指標
    "inflation", "cpi", "pce", "nonfarm", "nfp", "payroll", "gdp",
    "unemployment", "recession", "treasury", "yield",
    # 地政学
    "trump", "tariff", "trade war", "sanction", "war", "conflict",
    "election", "geopolit", "oil price", "crude", "opec",
    # 日本語
    "利上げ", "利下げ", "ドル", "円高", "円安", "日銀", "インフレ",
    "雇用統計", "トランプ", "関税", "戦争", "紛争", "景気後退",
]

RSS_FETCH_TIMEOUT = 8  # 秒


# ── データクラス ──────────────────────────────────────────────────────────────

@dataclass
class NewsArticle:
    title: str
    summary: str
    url: str
    published: str
    source: str
    title_hash: str


@dataclass
class NewsRecord:
    id: int
    collected_at: str
    title_hash: str
    title: str
    summary: str
    url: str
    source: str
    published: str
    analyzed: bool
    geopolitical_id: Optional[int]


@dataclass
class CollectionResult:
    fetched: int = 0
    relevant: int = 0
    new: int = 0
    analyzed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


# ── 内部ユーティリティ ────────────────────────────────────────────────────────

def _db_path_or_default(db_path) -> Path:
    from app.database.db import DB_PATH
    return Path(db_path) if db_path is not None else DB_PATH


def _make_hash(title: str) -> str:
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:12]


# ── DB 操作 ───────────────────────────────────────────────────────────────────

def ensure_news_table(db_path=None) -> None:
    path = _db_path_or_default(db_path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_article_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                collected_at    TEXT NOT NULL,
                title_hash      TEXT NOT NULL UNIQUE,
                title           TEXT NOT NULL,
                summary         TEXT NOT NULL DEFAULT '',
                url             TEXT NOT NULL DEFAULT '',
                source          TEXT NOT NULL DEFAULT '',
                published       TEXT NOT NULL DEFAULT '',
                analyzed        INTEGER NOT NULL DEFAULT 0,
                geopolitical_id INTEGER
            )
        """)
        conn.commit()
    finally:
        conn.close()


def get_fetched_hashes(db_path=None) -> set[str]:
    path = _db_path_or_default(db_path)
    ensure_news_table(db_path)
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT title_hash FROM news_article_log").fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def save_news_article(article: NewsArticle, db_path=None) -> int:
    path = _db_path_or_default(db_path)
    ensure_news_table(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO news_article_log
                (collected_at, title_hash, title, summary, url, source, published)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                article.title_hash,
                article.title,
                article.summary,
                article.url,
                article.source,
                article.published,
            ),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def mark_analyzed(article_id: int, geo_id: int, db_path=None) -> None:
    path = _db_path_or_default(db_path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "UPDATE news_article_log SET analyzed=1, geopolitical_id=? WHERE id=?",
            (geo_id, article_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_news_articles(limit: int = 30, db_path=None) -> list[NewsRecord]:
    path = _db_path_or_default(db_path)
    ensure_news_table(db_path)
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            """
            SELECT id, collected_at, title_hash, title, summary, url,
                   source, published, analyzed, geopolitical_id
            FROM news_article_log
            ORDER BY collected_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            NewsRecord(
                id=r[0],
                collected_at=r[1],
                title_hash=r[2],
                title=r[3],
                summary=r[4],
                url=r[5],
                source=r[6],
                published=r[7],
                analyzed=bool(r[8]),
                geopolitical_id=r[9],
            )
            for r in rows
        ]
    finally:
        conn.close()


def get_collection_stats(db_path=None) -> dict:
    path = _db_path_or_default(db_path)
    ensure_news_table(db_path)
    conn = sqlite3.connect(path)
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM news_article_log"
        ).fetchone()[0]
        analyzed = conn.execute(
            "SELECT COUNT(*) FROM news_article_log WHERE analyzed=1"
        ).fetchone()[0]
        last_row = conn.execute(
            "SELECT collected_at FROM news_article_log ORDER BY collected_at DESC LIMIT 1"
        ).fetchone()
        last_collected = last_row[0] if last_row else None
        return {
            "total": total,
            "analyzed": analyzed,
            "last_collected": last_collected,
        }
    finally:
        conn.close()


# ── RSS フェッチ ──────────────────────────────────────────────────────────────

def fetch_rss(source_name: str, url: str, timeout: int = RSS_FETCH_TIMEOUT) -> list[NewsArticle]:
    articles: list[NewsArticle] = []
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ai-fx-monitor/1.0 news-collector"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()

        root = ET.fromstring(content)

        for item in root.iter("item"):
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            pub_el = item.find("pubDate")

            title = (title_el.text or "").strip() if title_el is not None else ""
            if not title:
                continue

            articles.append(
                NewsArticle(
                    title=title,
                    summary=(desc_el.text or "").strip()[:400] if desc_el is not None else "",
                    url=(link_el.text or "").strip() if link_el is not None else "",
                    published=(pub_el.text or "").strip() if pub_el is not None else "",
                    source=source_name,
                    title_hash=_make_hash(title),
                )
            )
    except Exception as exc:
        logger.warning("RSS取得エラー (%s): %s", source_name, exc)
    return articles


def is_fx_relevant(article: NewsArticle) -> bool:
    text_lower = f"{article.title} {article.summary}".lower()
    return any(kw.lower() in text_lower for kw in FX_KEYWORDS)


# ── メイン収集・分析 ──────────────────────────────────────────────────────────

def collect_and_analyze(db_path=None) -> CollectionResult:
    """全 RSS ソースから FX 関連ニュースを収集し地政学分析を自動実行する。"""
    from app.scripts.geopolitical import analyze_and_save

    result = CollectionResult()
    existing_hashes = get_fetched_hashes(db_path)

    for source in RSS_SOURCES:
        articles = fetch_rss(source["name"], source["url"])
        result.fetched += len(articles)

        relevant = [a for a in articles if is_fx_relevant(a)]
        result.relevant += len(relevant)

        for article in relevant:
            if article.title_hash in existing_hashes:
                result.skipped += 1
                continue

            article_id = save_news_article(article, db_path)
            existing_hashes.add(article.title_hash)
            result.new += 1

            try:
                event_text = article.title
                if article.summary:
                    event_text += " " + article.summary[:200]

                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                _, geo_id = analyze_and_save(event_text, today, db_path)

                if article_id:
                    mark_analyzed(article_id, geo_id, db_path)
                result.analyzed += 1
            except Exception as exc:
                logger.warning(
                    "地政学分析エラー (title=%s): %s", article.title[:50], exc
                )
                result.errors.append(str(exc)[:100])

    logger.info(
        "ニュース収集完了: 取得=%d 関連=%d 新規=%d 分析=%d スキップ=%d",
        result.fetched, result.relevant, result.new, result.analyzed, result.skipped,
    )
    return result
