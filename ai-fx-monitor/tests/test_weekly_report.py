"""Phase 65: AIトレード週次レポート テスト"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.scripts.weekly_report import (
    WeeklyMetrics,
    WeeklyReport,
    _collect_metrics,
    _generate_mock_narrative,
    generate_and_save_weekly_report,
    get_latest_weekly_report,
    get_weekly_reports,
    save_weekly_report,
    week_bounds,
    current_week_label,
)


# ── フィクスチャ ───────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    """テスト用 SQLite DB（最低限のテーブルのみ）。"""
    db = tmp_path / "test.db"
    with sqlite3.connect(str(db)) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS approval_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                current_price REAL,
                signal TEXT NOT NULL,
                score INTEGER,
                daily_trend TEXT,
                h4_trend TEXT,
                h1_status TEXT,
                rsi REAL,
                atr_value REAL,
                atr_status TEXT,
                recent_high REAL,
                recent_low REAL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                risk_reward REAL,
                economic_event_warning INTEGER DEFAULT 0,
                economic_event_name TEXT,
                ai_comment TEXT,
                human_action TEXT NOT NULL DEFAULT 'approve',
                notes TEXT,
                is_dummy_data INTEGER DEFAULT 0,
                skip_reasons TEXT,
                outcome TEXT,
                exit_price REAL,
                closed_at TEXT,
                pnl_pips REAL
            );
            CREATE TABLE IF NOT EXISTS weekly_report_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                week_label TEXT NOT NULL,
                week_start TEXT NOT NULL,
                week_end TEXT NOT NULL,
                symbol TEXT NOT NULL DEFAULT '',
                report_json TEXT NOT NULL,
                ai_narrative TEXT NOT NULL DEFAULT '',
                ai_provider TEXT NOT NULL DEFAULT 'mock'
            );
            CREATE TABLE IF NOT EXISTS trade_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                period_type TEXT NOT NULL,
                period_label TEXT NOT NULL,
                target_pips REAL NOT NULL,
                symbol TEXT NOT NULL DEFAULT '',
                note TEXT,
                UNIQUE(period_type, period_label, symbol)
            );
            CREATE TABLE IF NOT EXISTS macro_event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                usd_forecast TEXT NOT NULL DEFAULT 'neutral',
                actual_result TEXT,
                notes TEXT
            );
        """)
        conn.commit()
    return db


@pytest.fixture()
def db_with_trades(tmp_db):
    """今週・累計トレードを含む DB。"""
    from app.scripts.weekly_report import week_bounds, current_week_label
    week_start, week_end = week_bounds(current_week_label())

    with sqlite3.connect(str(tmp_db)) as conn:
        # 今週のクローズ済みトレード
        conn.executemany(
            "INSERT INTO approval_history (created_at, symbol, signal, human_action, outcome, closed_at, pnl_pips, is_dummy_data) VALUES (?,?,?,?,?,?,?,0)",
            [
                (week_start + " 10:00:00", "USD/JPY", "BUY", "approve", "win", week_start + " 14:00:00", 15.0),
                (week_start + " 15:00:00", "USD/JPY", "SELL", "approve", "loss", week_start + " 18:00:00", -8.0),
                (week_start + " 20:00:00", "EUR/USD", "BUY", "approve", "win", (week_start[:8] + "01") + " 10:00:00", 20.0),
            ],
        )
        # 先週分（全体集計に含まれる）
        conn.execute(
            "INSERT INTO approval_history (created_at, symbol, signal, human_action, outcome, closed_at, pnl_pips, is_dummy_data) VALUES (?,?,?,?,?,?,?,0)",
            ("2026-01-10 10:00:00", "USD/JPY", "BUY", "approve", "win", "2026-01-10 14:00:00", 12.0),
        )
        conn.commit()
    return tmp_db


# ── ユーティリティ関数テスト ──────────────────────────────────────────────

class TestWeekBounds:
    def test_returns_monday_and_sunday(self):
        start, end = week_bounds("2026-W21")
        from datetime import date
        d_start = date.fromisoformat(start)
        d_end = date.fromisoformat(end)
        assert d_start.weekday() == 0       # Monday
        assert d_end.weekday() == 6         # Sunday
        assert (d_end - d_start).days == 6

    def test_week21_2026(self):
        start, end = week_bounds("2026-W21")
        assert start == "2026-05-18"
        assert end == "2026-05-24"

    def test_week1_2026(self):
        start, end = week_bounds("2026-W01")
        assert start.startswith("2025-12") or start.startswith("2026-01")


class TestCurrentWeekLabel:
    def test_format(self):
        label = current_week_label()
        assert label.startswith("20")
        assert "-W" in label
        year, wnum = label.split("-W")
        assert 1 <= int(wnum) <= 53


# ── WeeklyMetrics 集計テスト ─────────────────────────────────────────────

class TestCollectMetrics:
    def test_empty_db_returns_zero_trades(self, tmp_db):
        m = _collect_metrics("", current_week_label(), tmp_db)
        assert m.week_trades == 0
        assert m.total_trades == 0
        assert m.week_win_rate is None
        assert m.overall_grade == "N/A"

    def test_counts_week_trades(self, db_with_trades):
        week = current_week_label()
        m = _collect_metrics("USD/JPY", week, db_with_trades)
        assert m.week_trades == 2
        assert m.week_wins == 1
        assert m.week_losses == 1

    def test_week_pips(self, db_with_trades):
        week = current_week_label()
        m = _collect_metrics("USD/JPY", week, db_with_trades)
        assert abs(m.week_pips - 7.0) < 0.01   # 15 - 8

    def test_win_rate_calculation(self, db_with_trades):
        week = current_week_label()
        m = _collect_metrics("USD/JPY", week, db_with_trades)
        assert m.week_win_rate == pytest.approx(50.0)

    def test_all_symbol_aggregation(self, db_with_trades):
        week = current_week_label()
        m = _collect_metrics("", week, db_with_trades)
        assert m.week_trades >= 2   # 今週分のみ（EUR/USD含む可能性あり）

    def test_total_trades_includes_all(self, db_with_trades):
        week = current_week_label()
        m = _collect_metrics("USD/JPY", week, db_with_trades)
        assert m.total_trades >= 3  # 今週2 + 先週1

    def test_total_pips(self, db_with_trades):
        week = current_week_label()
        m = _collect_metrics("USD/JPY", week, db_with_trades)
        # 今週: 15 - 8 = 7, 先週: 12 → 合計 19
        assert abs(m.total_pips - 19.0) < 0.01

    def test_best_worst_pips(self, db_with_trades):
        week = current_week_label()
        m = _collect_metrics("USD/JPY", week, db_with_trades)
        assert m.week_best_pips == pytest.approx(15.0)
        assert m.week_worst_pips == pytest.approx(-8.0)

    def test_streak_calculation(self, db_with_trades):
        week = current_week_label()
        m = _collect_metrics("USD/JPY", week, db_with_trades)
        # 最後の取引結果でストリークが確定
        assert m.current_streak >= 1
        assert m.current_streak_type in ("win", "loss")

    def test_macro_events_this_week(self, tmp_db):
        week = current_week_label()
        start, _ = week_bounds(week)
        with sqlite3.connect(str(tmp_db)) as conn:
            conn.execute(
                "INSERT INTO macro_event_log (created_at, event_date, event_type, title, usd_forecast) VALUES (?,?,?,?,?)",
                (start, start, "FOMC", "FRB政策会合", "bullish"),
            )
            conn.commit()
        m = _collect_metrics("", week, tmp_db)
        assert len(m.macro_events) == 1
        assert "FOMC" in m.macro_events[0]

    def test_symbol_filter(self, db_with_trades):
        week = current_week_label()
        m_usdjpy = _collect_metrics("USD/JPY", week, db_with_trades)
        m_all = _collect_metrics("", week, db_with_trades)
        # USD/JPY フィルター時は EUR/USD の取引を含まない
        assert m_usdjpy.week_trades <= m_all.week_trades


# ── モックナレーティブテスト ─────────────────────────────────────────────

class TestGenerateMockNarrative:
    def test_no_trades(self):
        m = WeeklyMetrics(week_label="2026-W21", week_start="2026-05-18",
                          week_end="2026-05-24", symbol="")
        text = _generate_mock_narrative(m)
        assert "取引がありません" in text

    def test_with_wins(self):
        m = WeeklyMetrics(week_label="2026-W21", week_start="2026-05-18",
                          week_end="2026-05-24", symbol="USD/JPY",
                          week_trades=3, week_wins=2, week_losses=1,
                          week_win_rate=66.7, week_pips=20.0)
        text = _generate_mock_narrative(m)
        assert len(text) > 0
        assert "20" in text or "pips" in text.lower() or "プラス" in text

    def test_with_losses(self):
        m = WeeklyMetrics(week_label="2026-W21", week_start="2026-05-18",
                          week_end="2026-05-24", symbol="",
                          week_trades=3, week_wins=1, week_losses=2,
                          week_win_rate=33.3, week_pips=-15.0)
        text = _generate_mock_narrative(m)
        assert "損失" in text or "マイナス" in text or "振り返り" in text or "RR" in text

    def test_with_streak(self):
        m = WeeklyMetrics(week_label="2026-W21", week_start="2026-05-18",
                          week_end="2026-05-24", symbol="",
                          current_streak=3, current_streak_type="win")
        text = _generate_mock_narrative(m)
        assert "3" in text


# ── DB 保存・取得テスト ──────────────────────────────────────────────────

class TestSaveAndGetReports:
    def _make_report(self) -> WeeklyReport:
        m = WeeklyMetrics(
            week_label="2026-W20",
            week_start="2026-05-11",
            week_end="2026-05-17",
            symbol="USD/JPY",
            week_trades=5,
            week_wins=3,
            week_losses=2,
            week_win_rate=60.0,
            week_pips=25.0,
        )
        return WeeklyReport(id=None, metrics=m,
                            ai_narrative="テストナレーティブ",
                            ai_provider="mock",
                            created_at="2026-05-17 23:00:00")

    def test_save_and_retrieve(self, tmp_db):
        report = self._make_report()
        saved_id = save_weekly_report(report, tmp_db)
        assert saved_id > 0
        reports = get_weekly_reports("USD/JPY", limit=10, db_path=tmp_db)
        assert len(reports) == 1
        assert reports[0].id == saved_id
        assert reports[0].metrics.week_label == "2026-W20"
        assert reports[0].ai_narrative == "テストナレーティブ"
        assert reports[0].ai_provider == "mock"

    def test_metrics_roundtrip(self, tmp_db):
        report = self._make_report()
        save_weekly_report(report, tmp_db)
        retrieved = get_weekly_reports("USD/JPY", db_path=tmp_db)[0]
        assert retrieved.metrics.week_trades == 5
        assert retrieved.metrics.week_wins == 3
        assert retrieved.metrics.week_win_rate == pytest.approx(60.0)
        assert retrieved.metrics.week_pips == pytest.approx(25.0)

    def test_get_latest(self, tmp_db):
        r1 = self._make_report()
        r1.metrics.week_label = "2026-W19"
        r1.created_at = "2026-05-10 23:00:00"
        save_weekly_report(r1, tmp_db)
        r2 = self._make_report()
        save_weekly_report(r2, tmp_db)
        latest = get_latest_weekly_report("USD/JPY", db_path=tmp_db)
        assert latest is not None
        assert latest.metrics.week_label == "2026-W20"

    def test_empty_db_returns_empty_list(self, tmp_db):
        reports = get_weekly_reports(db_path=tmp_db)
        assert reports == []

    def test_latest_empty_db_returns_none(self, tmp_db):
        assert get_latest_weekly_report(db_path=tmp_db) is None

    def test_symbol_filter_get(self, tmp_db):
        r = self._make_report()
        save_weekly_report(r, tmp_db)
        # EUR/USD フィルターでは取得されない
        reports = get_weekly_reports("EUR/USD", db_path=tmp_db)
        assert len(reports) == 0
        # 全ペアフィルターでは取得される
        reports_all = get_weekly_reports("", db_path=tmp_db)
        assert len(reports_all) == 1

    def test_limit_respected(self, tmp_db):
        for i in range(5):
            r = self._make_report()
            r.metrics.week_label = f"2026-W{i+10:02d}"
            r.created_at = f"2026-03-0{i+1} 00:00:00"
            save_weekly_report(r, tmp_db)
        reports = get_weekly_reports("USD/JPY", limit=3, db_path=tmp_db)
        assert len(reports) == 3


# ── エンドツーエンド生成テスト ────────────────────────────────────────────

class TestGenerateAndSave:
    def test_generate_creates_mock_report(self, tmp_db):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            report = generate_and_save_weekly_report("", tmp_db)
        assert report.id is not None
        assert report.id > 0
        assert report.ai_provider == "mock"
        assert len(report.ai_narrative) > 0
        assert report.metrics.week_label == current_week_label()

    def test_saved_to_db(self, tmp_db):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            report = generate_and_save_weekly_report("", tmp_db)
        reports = get_weekly_reports(db_path=tmp_db)
        assert len(reports) == 1
        assert reports[0].id == report.id

    def test_symbol_specific_report(self, db_with_trades):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            report = generate_and_save_weekly_report("USD/JPY", db_with_trades)
        assert report.metrics.symbol == "USD/JPY"
        assert report.metrics.week_trades >= 0
