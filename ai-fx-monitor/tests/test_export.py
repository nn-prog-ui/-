"""Phase 35: CSV エクスポート用クエリのテスト"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.database.db import init_db, get_db
from app.database.repository import (
    get_demo_orders_for_export,
    get_history_for_export,
    get_journal_for_export,
    upsert_journal,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _seed_approval(db: Path, symbol="USD/JPY", signal="BUY", action="buy_approved", date="2026-01-10") -> int:
    with get_db(db) as conn:
        cur = conn.execute(
            "INSERT INTO approval_history (created_at, symbol, signal, human_action) VALUES (?, ?, ?, ?)",
            (f"{date} 10:00:00", symbol, signal, action),
        )
        return cur.lastrowid


def _seed_demo_order(db: Path, symbol="USD/JPY") -> int:
    aid = _seed_approval(db, symbol=symbol)
    with get_db(db) as conn:
        cur = conn.execute(
            """INSERT INTO demo_orders (created_at, approval_id, symbol, direction, units)
               VALUES ('2026-01-10 10:00:00', ?, ?, 'BUY', 1000)""",
            (aid, symbol),
        )
        return cur.lastrowid


class TestGetHistoryForExport:
    def test_returns_all_when_no_filter(self, tmp_db):
        _seed_approval(tmp_db)
        _seed_approval(tmp_db)
        rows = get_history_for_export(db_path=tmp_db)
        assert len(rows) == 2

    def test_symbol_filter(self, tmp_db):
        _seed_approval(tmp_db, symbol="USD/JPY")
        _seed_approval(tmp_db, symbol="EUR/USD")
        rows = get_history_for_export(symbol="USD/JPY", db_path=tmp_db)
        assert len(rows) == 1
        assert rows[0]["symbol"] == "USD/JPY"

    def test_signal_filter(self, tmp_db):
        _seed_approval(tmp_db, signal="BUY")
        _seed_approval(tmp_db, signal="SELL")
        _seed_approval(tmp_db, signal="SKIP")
        rows = get_history_for_export(signal="BUY", db_path=tmp_db)
        assert len(rows) == 1
        assert rows[0]["signal"] == "BUY"

    def test_human_action_filter(self, tmp_db):
        _seed_approval(tmp_db, action="buy_approved")
        _seed_approval(tmp_db, action="skipped")
        rows = get_history_for_export(human_action="buy_approved", db_path=tmp_db)
        assert len(rows) == 1

    def test_date_from_filter(self, tmp_db):
        _seed_approval(tmp_db, date="2026-01-05")
        _seed_approval(tmp_db, date="2026-01-15")
        rows = get_history_for_export(date_from="2026-01-10", db_path=tmp_db)
        assert len(rows) == 1

    def test_date_to_filter(self, tmp_db):
        _seed_approval(tmp_db, date="2026-01-05")
        _seed_approval(tmp_db, date="2026-01-15")
        rows = get_history_for_export(date_to="2026-01-10", db_path=tmp_db)
        assert len(rows) == 1

    def test_combined_filters(self, tmp_db):
        _seed_approval(tmp_db, symbol="USD/JPY", signal="BUY", date="2026-01-10")
        _seed_approval(tmp_db, symbol="EUR/USD", signal="BUY", date="2026-01-10")
        _seed_approval(tmp_db, symbol="USD/JPY", signal="SELL", date="2026-01-10")
        rows = get_history_for_export(symbol="USD/JPY", signal="BUY", db_path=tmp_db)
        assert len(rows) == 1

    def test_empty_db(self, tmp_db):
        rows = get_history_for_export(db_path=tmp_db)
        assert rows == []

    def test_returns_list_of_dicts(self, tmp_db):
        _seed_approval(tmp_db)
        rows = get_history_for_export(db_path=tmp_db)
        assert isinstance(rows[0], dict)
        assert "symbol" in rows[0]
        assert "signal" in rows[0]


class TestGetJournalForExport:
    def test_empty_when_no_journals(self, tmp_db):
        _seed_approval(tmp_db)
        rows = get_journal_for_export(db_path=tmp_db)
        assert rows == []

    def test_returns_joined_data(self, tmp_db):
        aid = _seed_approval(tmp_db)
        upsert_journal(aid, notes="エクスポートテスト", tags="押し目", db_path=tmp_db)
        rows = get_journal_for_export(db_path=tmp_db)
        assert len(rows) == 1
        assert rows[0]["notes"] == "エクスポートテスト"
        assert rows[0]["symbol"] == "USD/JPY"

    def test_tag_filter(self, tmp_db):
        aid1 = _seed_approval(tmp_db)
        aid2 = _seed_approval(tmp_db)
        upsert_journal(aid1, notes="A", tags="押し目", db_path=tmp_db)
        upsert_journal(aid2, notes="B", tags="反省", db_path=tmp_db)
        rows = get_journal_for_export(tag_filter="押し目", db_path=tmp_db)
        assert len(rows) == 1
        assert rows[0]["notes"] == "A"

    def test_entry_type_filter(self, tmp_db):
        aid1 = _seed_approval(tmp_db)
        aid2 = _seed_approval(tmp_db)
        upsert_journal(aid1, notes="X", entry_type="ブレイクアウト", db_path=tmp_db)
        upsert_journal(aid2, notes="Y", entry_type="反省", db_path=tmp_db)
        rows = get_journal_for_export(entry_type_filter="ブレイクアウト", db_path=tmp_db)
        assert len(rows) == 1
        assert rows[0]["entry_type"] == "ブレイクアウト"


class TestGetDemoOrdersForExport:
    def test_empty_db(self, tmp_db):
        rows = get_demo_orders_for_export(db_path=tmp_db)
        assert rows == []

    def test_returns_all_orders(self, tmp_db):
        _seed_demo_order(tmp_db, symbol="USD/JPY")
        _seed_demo_order(tmp_db, symbol="EUR/USD")
        rows = get_demo_orders_for_export(db_path=tmp_db)
        assert len(rows) == 2

    def test_returns_dicts(self, tmp_db):
        _seed_demo_order(tmp_db)
        rows = get_demo_orders_for_export(db_path=tmp_db)
        assert isinstance(rows[0], dict)
        assert "symbol" in rows[0]
        assert "direction" in rows[0]
