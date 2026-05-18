"""Phase 34: トレードジャーナル CRUD のテスト"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.database.db import init_db
from app.database.repository import (
    JOURNAL_EMOTION_LABELS,
    JOURNAL_ENTRY_TYPES,
    get_journal_count,
    get_journal_entries,
    get_journal_entry,
    upsert_journal,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """テスト用一時DBパスを返す。"""
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _seed_approval(db: Path) -> int:
    """テスト用の approval_history レコードを1件作成して ID を返す。"""
    from app.database.db import get_db
    with get_db(db) as conn:
        cur = conn.execute(
            """INSERT INTO approval_history
               (created_at, symbol, signal, human_action)
               VALUES ('2026-01-01 00:00:00', 'USD/JPY', 'BUY', 'buy_approved')"""
        )
        return cur.lastrowid


class TestUpsertJournal:
    def test_create_new_entry(self, tmp_db):
        aid = _seed_approval(tmp_db)
        jid = upsert_journal(aid, notes="テストメモ", tags="押し目", entry_type="押し目買い", emotion_score=4, db_path=tmp_db)
        assert jid is not None and jid > 0

    def test_get_entry_after_create(self, tmp_db):
        aid = _seed_approval(tmp_db)
        upsert_journal(aid, notes="初回メモ", tags="反省", entry_type="ダマシ", db_path=tmp_db)
        entry = get_journal_entry(aid, db_path=tmp_db)
        assert entry is not None
        assert entry["notes"] == "初回メモ"
        assert entry["tags"] == "反省"
        assert entry["entry_type"] == "ダマシ"

    def test_update_existing_entry(self, tmp_db):
        aid = _seed_approval(tmp_db)
        upsert_journal(aid, notes="最初のメモ", db_path=tmp_db)
        upsert_journal(aid, notes="更新後のメモ", tags="要検証", db_path=tmp_db)
        entry = get_journal_entry(aid, db_path=tmp_db)
        assert entry["notes"] == "更新後のメモ"
        assert entry["tags"] == "要検証"

    def test_emotion_score_default(self, tmp_db):
        aid = _seed_approval(tmp_db)
        upsert_journal(aid, db_path=tmp_db)
        entry = get_journal_entry(aid, db_path=tmp_db)
        assert entry["emotion_score"] == 3

    def test_emotion_score_set(self, tmp_db):
        aid = _seed_approval(tmp_db)
        upsert_journal(aid, emotion_score=5, db_path=tmp_db)
        entry = get_journal_entry(aid, db_path=tmp_db)
        assert entry["emotion_score"] == 5


class TestGetJournalEntry:
    def test_returns_none_if_not_exists(self, tmp_db):
        aid = _seed_approval(tmp_db)
        result = get_journal_entry(aid, db_path=tmp_db)
        assert result is None

    def test_returns_dict(self, tmp_db):
        aid = _seed_approval(tmp_db)
        upsert_journal(aid, notes="チェック", db_path=tmp_db)
        entry = get_journal_entry(aid, db_path=tmp_db)
        assert isinstance(entry, dict)
        assert "approval_id" in entry


class TestGetJournalEntries:
    def test_empty_when_no_journals(self, tmp_db):
        _seed_approval(tmp_db)
        entries = get_journal_entries(db_path=tmp_db)
        assert entries == []

    def test_returns_entries_with_approval_data(self, tmp_db):
        aid = _seed_approval(tmp_db)
        upsert_journal(aid, notes="テスト", tags="ブレイクアウト", db_path=tmp_db)
        entries = get_journal_entries(db_path=tmp_db)
        assert len(entries) == 1
        assert entries[0]["notes"] == "テスト"
        assert entries[0]["symbol"] == "USD/JPY"

    def test_tag_filter(self, tmp_db):
        aid1 = _seed_approval(tmp_db)
        aid2 = _seed_approval(tmp_db)
        upsert_journal(aid1, notes="メモA", tags="押し目,反省", db_path=tmp_db)
        upsert_journal(aid2, notes="メモB", tags="ブレイクアウト", db_path=tmp_db)
        filtered = get_journal_entries(tag_filter="押し目", db_path=tmp_db)
        assert len(filtered) == 1
        assert filtered[0]["notes"] == "メモA"

    def test_entry_type_filter(self, tmp_db):
        aid1 = _seed_approval(tmp_db)
        aid2 = _seed_approval(tmp_db)
        upsert_journal(aid1, notes="A", entry_type="反省", db_path=tmp_db)
        upsert_journal(aid2, notes="B", entry_type="ブレイクアウト", db_path=tmp_db)
        filtered = get_journal_entries(entry_type_filter="反省", db_path=tmp_db)
        assert len(filtered) == 1
        assert filtered[0]["notes"] == "A"

    def test_limit_offset(self, tmp_db):
        for _ in range(5):
            aid = _seed_approval(tmp_db)
            upsert_journal(aid, notes="x", db_path=tmp_db)
        page1 = get_journal_entries(limit=3, offset=0, db_path=tmp_db)
        page2 = get_journal_entries(limit=3, offset=3, db_path=tmp_db)
        assert len(page1) == 3
        assert len(page2) == 2


class TestGetJournalCount:
    def test_count_zero(self, tmp_db):
        _seed_approval(tmp_db)
        assert get_journal_count(db_path=tmp_db) == 0

    def test_count_after_inserts(self, tmp_db):
        for _ in range(3):
            aid = _seed_approval(tmp_db)
            upsert_journal(aid, notes="test", db_path=tmp_db)
        assert get_journal_count(db_path=tmp_db) == 3


class TestConstants:
    def test_entry_types_is_list(self):
        assert isinstance(JOURNAL_ENTRY_TYPES, list)
        assert len(JOURNAL_ENTRY_TYPES) >= 5

    def test_emotion_labels_keys_1_to_5(self):
        assert set(JOURNAL_EMOTION_LABELS.keys()) == {1, 2, 3, 4, 5}
