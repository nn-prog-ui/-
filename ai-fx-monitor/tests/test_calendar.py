"""tests/test_calendar.py — Phase 39: 経済指標カレンダーテスト"""
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from app.database.db import init_db
from app.database.repository import (
    IMPORTANCE_LEVELS,
    IMPORTANCE_LABELS,
    WARNING_WINDOW_HOURS,
    create_economic_event,
    delete_economic_event,
    get_economic_events,
    count_economic_events,
    get_upcoming_warning_events,
    has_upcoming_warning,
)


# ── フィクスチャ ─────────────────────────────────────────────
@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_calendar.db"
    init_db(db)
    return db


def _dt(delta_hours: float = 0) -> str:
    """現在時刻 + delta_hours の ISO 文字列を返す。"""
    dt = datetime.utcnow() + timedelta(hours=delta_hours)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ── 定数テスト ────────────────────────────────────────────────
class TestConstants:
    def test_importance_levels(self):
        assert "HIGH" in IMPORTANCE_LEVELS
        assert "MEDIUM" in IMPORTANCE_LEVELS
        assert "LOW" in IMPORTANCE_LEVELS

    def test_importance_labels_keys(self):
        for level in IMPORTANCE_LEVELS:
            assert level in IMPORTANCE_LABELS

    def test_warning_window_is_positive(self):
        assert WARNING_WINDOW_HOURS > 0


# ── create_economic_event ────────────────────────────────────
class TestCreateEconomicEvent:
    def test_create_returns_id(self, tmp_db):
        eid = create_economic_event(
            event_dt=_dt(2), currency="USD", importance="HIGH",
            event_name="米雇用統計", db_path=tmp_db,
        )
        assert isinstance(eid, int)
        assert eid > 0

    def test_create_stores_fields(self, tmp_db):
        create_economic_event(
            event_dt="2026-06-01 12:30:00", currency="usd",
            importance="MEDIUM", event_name="FOMC議事録", note="重要",
            db_path=tmp_db,
        )
        events = get_economic_events(db_path=tmp_db)
        assert len(events) == 1
        ev = events[0]
        assert ev["currency"] == "USD"  # 大文字に正規化
        assert ev["importance"] == "MEDIUM"
        assert ev["event_name"] == "FOMC議事録"
        assert ev["note"] == "重要"

    def test_invalid_importance_raises(self, tmp_db):
        with pytest.raises(ValueError):
            create_economic_event(
                event_dt=_dt(1), currency="JPY", importance="ULTRA",
                event_name="テスト", db_path=tmp_db,
            )

    def test_currency_normalized_uppercase(self, tmp_db):
        create_economic_event(
            event_dt=_dt(1), currency="jpy", importance="LOW",
            event_name="日銀発表", db_path=tmp_db,
        )
        events = get_economic_events(db_path=tmp_db)
        assert events[0]["currency"] == "JPY"


# ── get_economic_events ──────────────────────────────────────
class TestGetEconomicEvents:
    def test_empty_returns_empty_list(self, tmp_db):
        assert get_economic_events(db_path=tmp_db) == []

    def test_returns_multiple_events(self, tmp_db):
        for i in range(3):
            create_economic_event(
                event_dt=_dt(i + 1), currency="USD", importance="MEDIUM",
                event_name=f"Event {i}", db_path=tmp_db,
            )
        events = get_economic_events(db_path=tmp_db)
        assert len(events) == 3

    def test_filter_by_currency(self, tmp_db):
        create_economic_event(_dt(1), "USD", "HIGH", "A", db_path=tmp_db)
        create_economic_event(_dt(2), "JPY", "HIGH", "B", db_path=tmp_db)
        events = get_economic_events(currency="USD", db_path=tmp_db)
        assert len(events) == 1
        assert events[0]["currency"] == "USD"

    def test_filter_by_importance(self, tmp_db):
        create_economic_event(_dt(1), "USD", "HIGH", "A", db_path=tmp_db)
        create_economic_event(_dt(2), "USD", "LOW", "B", db_path=tmp_db)
        events = get_economic_events(importance="HIGH", db_path=tmp_db)
        assert len(events) == 1
        assert events[0]["importance"] == "HIGH"

    def test_limit_and_offset(self, tmp_db):
        for i in range(5):
            create_economic_event(_dt(i + 1), "USD", "MEDIUM", f"E{i}", db_path=tmp_db)
        page1 = get_economic_events(limit=3, offset=0, db_path=tmp_db)
        page2 = get_economic_events(limit=3, offset=3, db_path=tmp_db)
        assert len(page1) == 3
        assert len(page2) == 2

    def test_sorted_by_event_dt_asc(self, tmp_db):
        create_economic_event("2026-06-03 10:00:00", "USD", "HIGH", "Later", db_path=tmp_db)
        create_economic_event("2026-06-01 10:00:00", "USD", "HIGH", "Earlier", db_path=tmp_db)
        events = get_economic_events(db_path=tmp_db)
        assert events[0]["event_name"] == "Earlier"
        assert events[1]["event_name"] == "Later"


# ── count_economic_events ─────────────────────────────────────
class TestCountEconomicEvents:
    def test_count_zero(self, tmp_db):
        assert count_economic_events(db_path=tmp_db) == 0

    def test_count_matches_created(self, tmp_db):
        for i in range(4):
            create_economic_event(_dt(i + 1), "USD", "MEDIUM", f"E{i}", db_path=tmp_db)
        assert count_economic_events(db_path=tmp_db) == 4

    def test_count_with_filter(self, tmp_db):
        create_economic_event(_dt(1), "USD", "HIGH", "A", db_path=tmp_db)
        create_economic_event(_dt(2), "JPY", "HIGH", "B", db_path=tmp_db)
        assert count_economic_events(currency="USD", db_path=tmp_db) == 1


# ── delete_economic_event ─────────────────────────────────────
class TestDeleteEconomicEvent:
    def test_delete_returns_true(self, tmp_db):
        eid = create_economic_event(_dt(1), "USD", "HIGH", "A", db_path=tmp_db)
        assert delete_economic_event(eid, db_path=tmp_db) is True

    def test_delete_removes_event(self, tmp_db):
        eid = create_economic_event(_dt(1), "USD", "HIGH", "A", db_path=tmp_db)
        delete_economic_event(eid, db_path=tmp_db)
        assert count_economic_events(db_path=tmp_db) == 0

    def test_delete_nonexistent_returns_false(self, tmp_db):
        assert delete_economic_event(9999, db_path=tmp_db) is False


# ── get_upcoming_warning_events ──────────────────────────────
class TestGetUpcomingWarningEvents:
    def test_no_events_returns_empty(self, tmp_db):
        assert get_upcoming_warning_events(db_path=tmp_db) == []

    def test_high_event_within_window_included(self, tmp_db):
        create_economic_event(_dt(2), "USD", "HIGH", "雇用統計", db_path=tmp_db)
        events = get_upcoming_warning_events(window_hours=24, db_path=tmp_db)
        assert len(events) == 1

    def test_medium_event_within_window_included(self, tmp_db):
        create_economic_event(_dt(3), "USD", "MEDIUM", "小売", db_path=tmp_db)
        events = get_upcoming_warning_events(window_hours=24, db_path=tmp_db)
        assert len(events) == 1

    def test_low_event_not_included(self, tmp_db):
        create_economic_event(_dt(2), "USD", "LOW", "低重要指標", db_path=tmp_db)
        events = get_upcoming_warning_events(window_hours=24, db_path=tmp_db)
        assert len(events) == 0

    def test_past_event_not_included(self, tmp_db):
        create_economic_event(_dt(-2), "USD", "HIGH", "過去の指標", db_path=tmp_db)
        events = get_upcoming_warning_events(window_hours=24, db_path=tmp_db)
        assert len(events) == 0

    def test_far_future_event_not_included(self, tmp_db):
        create_economic_event(_dt(48), "USD", "HIGH", "遠い未来", db_path=tmp_db)
        events = get_upcoming_warning_events(window_hours=24, db_path=tmp_db)
        assert len(events) == 0

    def test_custom_window(self, tmp_db):
        create_economic_event(_dt(5), "USD", "HIGH", "5h先", db_path=tmp_db)
        assert len(get_upcoming_warning_events(window_hours=3, db_path=tmp_db)) == 0
        assert len(get_upcoming_warning_events(window_hours=6, db_path=tmp_db)) == 1


# ── has_upcoming_warning ─────────────────────────────────────
class TestHasUpcomingWarning:
    def test_false_when_no_events(self, tmp_db):
        assert has_upcoming_warning(db_path=tmp_db) is False

    def test_true_when_high_event_upcoming(self, tmp_db):
        create_economic_event(_dt(2), "USD", "HIGH", "雇用統計", db_path=tmp_db)
        assert has_upcoming_warning(db_path=tmp_db) is True

    def test_false_when_only_low_event(self, tmp_db):
        create_economic_event(_dt(2), "USD", "LOW", "低重要", db_path=tmp_db)
        assert has_upcoming_warning(db_path=tmp_db) is False

    def test_false_when_event_is_past(self, tmp_db):
        create_economic_event(_dt(-2), "USD", "HIGH", "過去", db_path=tmp_db)
        assert has_upcoming_warning(db_path=tmp_db) is False


# ── HTTP エンドポイント ────────────────────────────────────────
@pytest.mark.asyncio
async def test_calendar_page_ok():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/calendar")
    assert res.status_code == 200
    assert "経済指標" in res.text


@pytest.mark.asyncio
async def test_calendar_page_contains_form():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/calendar")
    assert 'action="/calendar"' in res.text
    assert 'name="event_name"' in res.text


@pytest.mark.asyncio
async def test_api_upcoming_events_ok():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/upcoming-events")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert "has_warning" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_api_upcoming_events_has_warning_is_bool():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/upcoming-events?hours=24")
    data = res.json()
    assert isinstance(data["has_warning"], bool)
