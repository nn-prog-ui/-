"""Phase 69: FXニュース自動収集 テスト"""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.scripts.news_collector import (
    RSS_SOURCES,
    FX_KEYWORDS,
    NewsArticle,
    NewsRecord,
    CollectionResult,
    _make_hash,
    ensure_news_table,
    get_fetched_hashes,
    save_news_article,
    mark_analyzed,
    get_news_articles,
    get_collection_stats,
    fetch_rss,
    is_fx_relevant,
    collect_and_analyze,
)


# ── フィクスチャ ──────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    db = tmp_path / "test_news.db"
    ensure_news_table(db)
    return db


def _make_article(
    title: str = "Fed raises interest rates by 0.25%",
    source: str = "BBC Business",
    summary: str = "The Federal Reserve raised rates.",
) -> NewsArticle:
    return NewsArticle(
        title=title,
        summary=summary,
        url="https://example.com/article",
        published="Thu, 22 May 2026 10:00:00 GMT",
        source=source,
        title_hash=_make_hash(title),
    )


# ── 定数テスト ────────────────────────────────────────────────────────────

class TestConstants:
    def test_rss_sources_not_empty(self):
        assert len(RSS_SOURCES) >= 2

    def test_rss_sources_have_name_and_url(self):
        for src in RSS_SOURCES:
            assert "name" in src
            assert "url" in src
            assert src["url"].startswith("http")

    def test_fx_keywords_not_empty(self):
        assert len(FX_KEYWORDS) >= 10

    def test_fx_keywords_contain_key_terms(self):
        kws_lower = [k.lower() for k in FX_KEYWORDS]
        assert "fed" in kws_lower or "federal reserve" in kws_lower
        assert "usd" in kws_lower or "dollar" in kws_lower


# ── _make_hash テスト ─────────────────────────────────────────────────────

class TestMakeHash:
    def test_returns_12_chars(self):
        assert len(_make_hash("hello")) == 12

    def test_same_input_same_output(self):
        assert _make_hash("FRB利上げ") == _make_hash("FRB利上げ")

    def test_different_input_different_output(self):
        assert _make_hash("FRB利上げ") != _make_hash("日銀利上げ")

    def test_empty_string_ok(self):
        assert len(_make_hash("")) == 12


# ── is_fx_relevant テスト ─────────────────────────────────────────────────

class TestIsFxRelevant:
    def test_fed_keyword_matches(self):
        art = _make_article(title="Fed raises interest rates")
        assert is_fx_relevant(art) is True

    def test_yen_keyword_matches(self):
        art = _make_article(title="Japanese yen weakens against dollar")
        assert is_fx_relevant(art) is True

    def test_trump_tariff_matches(self):
        art = _make_article(title="Trump announces new tariffs on imports")
        assert is_fx_relevant(art) is True

    def test_japanese_keyword_matches(self):
        art = _make_article(title="日銀が利上げを決定")
        assert is_fx_relevant(art) is True

    def test_unrelated_article_no_match(self):
        art = _make_article(
            title="Local sports team wins championship",
            summary="The home team scored three goals in the final.",
        )
        assert is_fx_relevant(art) is False

    def test_summary_also_checked(self):
        art = _make_article(
            title="Breaking news today",
            summary="The Federal Reserve announced a policy change.",
        )
        assert is_fx_relevant(art) is True

    def test_case_insensitive(self):
        art = _make_article(title="USD STRENGTHENS AGAINST JPY")
        assert is_fx_relevant(art) is True

    def test_recession_keyword(self):
        art = _make_article(title="US recession fears grow amid weak GDP data")
        assert is_fx_relevant(art) is True


# ── DB 操作テスト ─────────────────────────────────────────────────────────

class TestDBOperations:
    def test_save_and_retrieve(self, tmp_db):
        article = _make_article()
        article_id = save_news_article(article, tmp_db)
        assert article_id > 0
        records = get_news_articles(db_path=tmp_db)
        assert len(records) == 1
        r = records[0]
        assert r.title == article.title
        assert r.source == article.source
        assert r.analyzed is False

    def test_duplicate_insert_ignored(self, tmp_db):
        article = _make_article()
        save_news_article(article, tmp_db)
        save_news_article(article, tmp_db)  # duplicate
        records = get_news_articles(db_path=tmp_db)
        assert len(records) == 1

    def test_get_fetched_hashes_empty(self, tmp_db):
        assert get_fetched_hashes(tmp_db) == set()

    def test_get_fetched_hashes_after_save(self, tmp_db):
        article = _make_article()
        save_news_article(article, tmp_db)
        hashes = get_fetched_hashes(tmp_db)
        assert article.title_hash in hashes

    def test_mark_analyzed(self, tmp_db):
        article = _make_article()
        article_id = save_news_article(article, tmp_db)
        mark_analyzed(article_id, geo_id=42, db_path=tmp_db)
        records = get_news_articles(db_path=tmp_db)
        assert records[0].analyzed is True
        assert records[0].geopolitical_id == 42

    def test_limit_respected(self, tmp_db):
        for i in range(5):
            art = _make_article(title=f"Article number {i}")
            save_news_article(art, tmp_db)
        records = get_news_articles(limit=3, db_path=tmp_db)
        assert len(records) == 3

    def test_collection_stats_empty(self, tmp_db):
        stats = get_collection_stats(tmp_db)
        assert stats["total"] == 0
        assert stats["analyzed"] == 0
        assert stats["last_collected"] is None

    def test_collection_stats_after_save(self, tmp_db):
        article = _make_article()
        article_id = save_news_article(article, tmp_db)
        mark_analyzed(article_id, 1, tmp_db)
        stats = get_collection_stats(tmp_db)
        assert stats["total"] == 1
        assert stats["analyzed"] == 1
        assert stats["last_collected"] is not None


# ── fetch_rss テスト（ネットワーク不要・エラーハンドリング） ──────────────

class TestFetchRss:
    def test_invalid_url_returns_empty(self):
        articles = fetch_rss("Test", "http://invalid.localhost.local/rss.xml", timeout=2)
        assert isinstance(articles, list)
        assert len(articles) == 0

    def test_xml_parse_with_mock(self):
        rss_xml = b"""<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <title>Test Feed</title>
            <item>
              <title>Fed raises rates</title>
              <description>The Fed raised rates by 0.25%</description>
              <link>https://example.com/1</link>
              <pubDate>Thu, 22 May 2026 10:00:00 GMT</pubDate>
            </item>
            <item>
              <title>Market update</title>
              <description>Stocks rose today</description>
              <link>https://example.com/2</link>
              <pubDate>Thu, 22 May 2026 11:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""

        mock_resp = MagicMock()
        mock_resp.read.return_value = rss_xml
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            articles = fetch_rss("TestSource", "http://example.com/rss")

        assert len(articles) == 2
        assert articles[0].title == "Fed raises rates"
        assert articles[0].source == "TestSource"
        assert articles[1].title == "Market update"

    def test_empty_feed_returns_empty(self):
        rss_xml = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Empty</title></channel></rss>"""

        mock_resp = MagicMock()
        mock_resp.read.return_value = rss_xml
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            articles = fetch_rss("Empty", "http://example.com/rss")

        assert articles == []


# ── collect_and_analyze テスト ────────────────────────────────────────────

class TestCollectAndAnalyze:
    def _mock_rss_fetch(self, source_name, url, timeout=8):
        if source_name == "BBC Business":
            return [
                _make_article("Fed raises rates by 0.25%", source=source_name),
                NewsArticle(  # 非FX関連記事（タイトルもサマリーも関係なし）
                    title="Local sports team wins cup final",
                    summary="The home team scored three goals to win the trophy.",
                    url="https://example.com/sports",
                    published="Thu, 22 May 2026 10:00:00 GMT",
                    source=source_name,
                    title_hash=_make_hash("Local sports team wins cup final"),
                ),
            ]
        return []

    def test_returns_collection_result(self, tmp_db):
        with patch("app.scripts.news_collector.fetch_rss", side_effect=self._mock_rss_fetch), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            result = collect_and_analyze(tmp_db)
        assert isinstance(result, CollectionResult)

    def test_fetched_count(self, tmp_db):
        with patch("app.scripts.news_collector.fetch_rss", side_effect=self._mock_rss_fetch), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            result = collect_and_analyze(tmp_db)
        # BBC返す2件 + 他ソース0件
        assert result.fetched >= 2

    def test_relevant_filters_nonrelated(self, tmp_db):
        with patch("app.scripts.news_collector.fetch_rss", side_effect=self._mock_rss_fetch), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            result = collect_and_analyze(tmp_db)
        # 「Local sports」は FX 関連でないのでフィルタされる
        assert result.relevant < result.fetched

    def test_new_articles_saved_to_db(self, tmp_db):
        with patch("app.scripts.news_collector.fetch_rss", side_effect=self._mock_rss_fetch), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            collect_and_analyze(tmp_db)
        records = get_news_articles(db_path=tmp_db)
        assert len(records) >= 1

    def test_duplicate_skipped(self, tmp_db):
        with patch("app.scripts.news_collector.fetch_rss", side_effect=self._mock_rss_fetch), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            collect_and_analyze(tmp_db)
            result2 = collect_and_analyze(tmp_db)
        assert result2.skipped >= 1
        assert result2.new == 0

    def test_analyzed_count_matches_geopolitical(self, tmp_db):
        with patch("app.scripts.news_collector.fetch_rss", side_effect=self._mock_rss_fetch), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            result = collect_and_analyze(tmp_db)
        assert result.analyzed == result.new

    def test_no_sources_available_graceful(self, tmp_db):
        with patch("app.scripts.news_collector.fetch_rss", return_value=[]):
            result = collect_and_analyze(tmp_db)
        assert result.fetched == 0
        assert result.new == 0
        assert result.errors == []
