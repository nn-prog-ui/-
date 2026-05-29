"""Phase 75: ニュースセンチメント集計 テスト"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch


# ── sentiment.py 単体テスト ───────────────────────────────────────────────

class TestClassify:
    def test_strong_bullish_to_bullish(self):
        from app.scripts.sentiment import _classify
        assert _classify("strong_bullish") == "bullish"

    def test_bullish_to_bullish(self):
        from app.scripts.sentiment import _classify
        assert _classify("bullish") == "bullish"

    def test_strong_bearish_to_bearish(self):
        from app.scripts.sentiment import _classify
        assert _classify("strong_bearish") == "bearish"

    def test_bearish_to_bearish(self):
        from app.scripts.sentiment import _classify
        assert _classify("bearish") == "bearish"

    def test_neutral_to_neutral(self):
        from app.scripts.sentiment import _classify
        assert _classify("neutral") == "neutral"

    def test_unknown_to_neutral(self):
        from app.scripts.sentiment import _classify
        assert _classify("unknown") == "neutral"


class TestPct:
    def test_half(self):
        from app.scripts.sentiment import _pct
        assert _pct(1, 2) == 50.0

    def test_zero_denominator(self):
        from app.scripts.sentiment import _pct
        assert _pct(5, 0) == 0.0

    def test_full(self):
        from app.scripts.sentiment import _pct
        assert _pct(3, 3) == 100.0


class TestGetSentimentReport:
    def _make_db(self, tmp_path, rows: list[tuple]) -> Path:
        """テスト用 DB を作成して geopolitical_log にレコードを挿入する。"""
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE geopolitical_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_date TEXT NOT NULL,
                event_text TEXT NOT NULL,
                category TEXT NOT NULL,
                usd_impact TEXT NOT NULL,
                confidence TEXT NOT NULL,
                reasoning TEXT DEFAULT '',
                similar_events TEXT DEFAULT '[]',
                short_term_outlook TEXT DEFAULT '',
                risk_factors TEXT DEFAULT '',
                ai_provider TEXT DEFAULT 'mock',
                actual_result TEXT
            )
        """)
        for row in rows:
            conn.execute(
                "INSERT INTO geopolitical_log (created_at, event_date, event_text, category, usd_impact, confidence, ai_provider) VALUES (?,?,?,?,?,?,?)",
                row,
            )
        conn.commit()
        conn.close()
        return db

    def test_empty_db_returns_empty_report(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        db = self._make_db(tmp_path, [])
        report = get_sentiment_report(db_path=db, days=90)
        assert report.summary.total == 0

    def test_bullish_count(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-20 10:00:00", "2026-05-20", "FRBが利上げ", "FRB金融政策", "strong_bullish", "high", "mock"),
            ("2026-05-21 10:00:00", "2026-05-21", "ドル買い継続", "FRB金融政策", "bullish", "medium", "mock"),
            ("2026-05-22 10:00:00", "2026-05-22", "様子見", "政治リスク", "neutral", "low", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        assert report.summary.total == 3
        assert report.summary.bullish == 2
        assert report.summary.neutral == 1
        assert report.summary.bearish == 0

    def test_bearish_count(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-20 10:00:00", "2026-05-20", "ドル安圧力", "貿易摩擦", "strong_bearish", "high", "mock"),
            ("2026-05-21 10:00:00", "2026-05-21", "リスクオフ", "戦争・地政学", "bearish", "medium", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        assert report.summary.bearish == 2
        assert report.summary.strong_bearish == 1

    def test_bullish_pct_calculation(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-20 10:00:00", "2026-05-20", "A", "Cat1", "bullish", "high", "mock"),
            ("2026-05-21 10:00:00", "2026-05-21", "B", "Cat1", "bullish", "high", "mock"),
            ("2026-05-22 10:00:00", "2026-05-22", "C", "Cat1", "bearish", "high", "mock"),
            ("2026-05-23 10:00:00", "2026-05-23", "D", "Cat1", "neutral", "high", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        assert report.summary.bullish_pct == 50.0
        assert report.summary.bearish_pct == 25.0
        assert report.summary.neutral_pct == 25.0

    def test_category_grouping(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-20 10:00:00", "2026-05-20", "A", "FRB金融政策", "bullish", "high", "mock"),
            ("2026-05-21 10:00:00", "2026-05-21", "B", "FRB金融政策", "bullish", "high", "mock"),
            ("2026-05-22 10:00:00", "2026-05-22", "C", "日銀金融政策", "bearish", "high", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        cats = {c.category: c for c in report.categories}
        assert "FRB金融政策" in cats
        assert cats["FRB金融政策"].total == 2
        assert cats["FRB金融政策"].bullish == 2
        assert "日銀金融政策" in cats
        assert cats["日銀金融政策"].bearish == 1

    def test_category_sorted_by_total_desc(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-20 10:00:00", "2026-05-20", "A", "Cat1", "bullish", "high", "mock"),
            ("2026-05-21 10:00:00", "2026-05-21", "B", "Cat2", "bullish", "high", "mock"),
            ("2026-05-22 10:00:00", "2026-05-22", "C", "Cat2", "bearish", "high", "mock"),
            ("2026-05-23 10:00:00", "2026-05-23", "D", "Cat2", "neutral", "high", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        assert report.categories[0].category == "Cat2"

    def test_daily_grouping(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-20 10:00:00", "2026-05-20", "A", "Cat1", "bullish", "high", "mock"),
            ("2026-05-20 11:00:00", "2026-05-20", "B", "Cat1", "bearish", "high", "mock"),
            ("2026-05-21 10:00:00", "2026-05-21", "C", "Cat1", "bullish", "high", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        days = {d.date: d for d in report.daily}
        assert "2026-05-20" in days
        assert days["2026-05-20"].bullish == 1
        assert days["2026-05-20"].bearish == 1
        assert days["2026-05-20"].net_score == 0
        assert "2026-05-21" in days
        assert days["2026-05-21"].net_score == 1

    def test_daily_sorted_by_date(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-22 10:00:00", "2026-05-22", "A", "Cat1", "bullish", "high", "mock"),
            ("2026-05-20 10:00:00", "2026-05-20", "B", "Cat1", "bullish", "high", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        dates = [d.date for d in report.daily]
        assert dates == sorted(dates)

    def test_top_events_only_strong(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-20 10:00:00", "2026-05-20", "強シグナル", "Cat1", "strong_bullish", "high", "mock"),
            ("2026-05-21 10:00:00", "2026-05-21", "普通", "Cat1", "bullish", "medium", "mock"),
            ("2026-05-22 10:00:00", "2026-05-22", "強下げ", "Cat1", "strong_bearish", "high", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        impacts = [e.usd_impact for e in report.top_events]
        for imp in impacts:
            assert imp in ("strong_bullish", "strong_bearish")
        assert len(report.top_events) == 2

    def test_top_events_max_10(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-01 10:00:00", f"2026-05-{i:02d}", f"Event {i}", "Cat1", "strong_bullish", "high", "mock")
            for i in range(1, 16)
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        assert len(report.top_events) <= 10

    def test_date_from_to_populated(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-10 10:00:00", "2026-05-10", "A", "Cat1", "bullish", "high", "mock"),
            ("2026-05-22 10:00:00", "2026-05-22", "B", "Cat1", "bearish", "high", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        assert report.date_from == "2026-05-10"
        assert report.date_to == "2026-05-22"

    def test_total_days_correct(self, tmp_path):
        from app.scripts.sentiment import get_sentiment_report
        rows = [
            ("2026-05-10 10:00:00", "2026-05-10", "A", "Cat1", "bullish", "high", "mock"),
            ("2026-05-10 11:00:00", "2026-05-10", "B", "Cat1", "bearish", "high", "mock"),
            ("2026-05-22 10:00:00", "2026-05-22", "C", "Cat1", "neutral", "high", "mock"),
        ]
        db = self._make_db(tmp_path, rows)
        report = get_sentiment_report(db_path=db, days=90)
        assert report.total_days == 2

    def test_exception_returns_empty_report(self, tmp_path):
        """DB接続失敗時は空レポートを返す（例外を伝播しない）。"""
        from app.scripts.sentiment import get_sentiment_report
        report = get_sentiment_report(db_path=tmp_path / "nonexistent.db", days=90)
        assert report.summary.total == 0


# ── テンプレート確認 ──────────────────────────────────────────────────────

def _tpl() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "sentiment.html").read_text(encoding="utf-8")


class TestSentimentTemplate:
    def test_sentiment_nav_active(self):
        """センチメントページのナビリンクが active になっている"""
        assert 'href="/sentiment" class="nav-link active"' in _tpl()

    def test_overall_summary_section(self):
        """全体センチメントサマリーセクションが存在する"""
        assert "全体センチメント" in _tpl()

    def test_category_chart_section(self):
        """カテゴリー別グラフセクションが存在する"""
        assert "カテゴリー別センチメント" in _tpl()

    def test_trend_chart_section(self):
        """時系列グラフセクションが存在する"""
        assert "センチメント時系列" in _tpl()

    def test_top_events_section(self):
        """強シグナルイベントTOPセクションが存在する"""
        assert "強シグナルイベント" in _tpl()

    def test_cat_svg_present(self):
        """カテゴリーグラフ用 SVG が存在する"""
        assert 'id="cat-svg"' in _tpl()

    def test_trend_svg_present(self):
        """時系列グラフ用 SVG が存在する"""
        assert 'id="trend-svg"' in _tpl()

    def test_ratio_bar_present(self):
        """割合バーが存在する（CSS background:#4ade80）"""
        content = _tpl()
        assert "bullish_pct" in content

    def test_period_filter_buttons(self):
        """期間フィルタボタン（30日/60日/90日/180日）が存在する"""
        content = _tpl()
        assert "30日" in content
        assert "90日" in content
        assert "180日" in content

    def test_empty_state_message(self):
        """データなし時のメッセージが存在する"""
        assert "センチメントデータがありません" in _tpl()

    def test_news_collector_link(self):
        """データ追加誘導リンク（ニュース収集）が存在する"""
        assert "/news-collector" in _tpl()

    def test_net_score_label(self):
        """ネットスコアの説明が存在する"""
        assert "ネットスコア" in _tpl()

    def test_js_cat_data_variable(self):
        """JS CAT_DATA 変数がテンプレートにある"""
        assert "CAT_DATA" in _tpl()

    def test_js_daily_data_variable(self):
        """JS DAILY_DATA 変数がテンプレートにある"""
        assert "DAILY_DATA" in _tpl()


# ── routes.py 確認（ソース直読み） ────────────────────────────────────────

def _routes_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "routes.py").read_text(encoding="utf-8")


class TestSentimentRoute:
    def test_sentiment_route_exists(self):
        """GET /sentiment ルートが存在する"""
        assert '"/sentiment"' in _routes_src() or "'/sentiment'" in _routes_src()

    def test_api_sentiment_route_exists(self):
        """GET /api/sentiment ルートが存在する"""
        assert '"/api/sentiment"' in _routes_src()

    def test_daily_json_in_route(self):
        """daily_json がテンプレートコンテキストに渡される"""
        assert "daily_json" in _routes_src()

    def test_cat_json_in_route(self):
        """cat_json がテンプレートコンテキストに渡される"""
        assert "cat_json" in _routes_src()

    def test_phase75_comment(self):
        """Phase 75 のコメントが含まれる"""
        assert "Phase 75" in _routes_src()

    def test_sentiment_nav_in_all_templates(self):
        """全テンプレートに /sentiment ナビリンクが追加されている"""
        tpl_dir = Path(__file__).parent.parent / "app" / "web" / "templates"
        # demo_trade は nav がないので除外
        skip = {"demo_trade.html"}
        missing = []
        for f in tpl_dir.glob("*.html"):
            if f.name in skip:
                continue
            if "/sentiment" not in f.read_text(encoding="utf-8"):
                missing.append(f.name)
        assert missing == [], f"センチメントナビリンクなし: {missing}"
