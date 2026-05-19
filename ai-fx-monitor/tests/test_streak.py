"""tests/test_streak.py — Phase 48: 連勝/連敗ストリーク分析テスト"""
from __future__ import annotations

import pytest

from app.scripts.streak import (
    StreakEvent,
    StreakStats,
    _compute_streaks_v2,
    get_streak_stats,
    get_streak_stats_by_symbol,
)


# ── テスト用 DB ヘルパー ──────────────────────────────────────────


def _insert_trade(conn, created_at, symbol, human_action, outcome):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, "BUY" if human_action == "buy" else "SELL",
         human_action, outcome, 10.0 if outcome == "win" else -5.0,
         3, 50.0, "上昇", "上昇", "上昇", 0),
    )


# ── _compute_streaks_v2 ───────────────────────────────────────────


class TestComputeStreaks:
    def _row(self, created_at, outcome):
        class R(dict):
            def __getitem__(s, k):
                return {"created_at": created_at, "outcome": outcome}[k]
        return R()

    def test_empty_returns_empty(self):
        assert _compute_streaks_v2([]) == []

    def test_single_win(self):
        rows = [self._row("2024-01-01", "win")]
        events = _compute_streaks_v2(rows)
        assert len(events) == 1
        assert events[0].type == "win"
        assert events[0].length == 1

    def test_three_wins_one_streak(self):
        rows = [self._row(f"2024-01-0{i+1}", "win") for i in range(3)]
        events = _compute_streaks_v2(rows)
        assert len(events) == 1
        assert events[0].length == 3

    def test_win_loss_alternating(self):
        rows = [
            self._row("2024-01-01", "win"),
            self._row("2024-01-02", "loss"),
            self._row("2024-01-03", "win"),
            self._row("2024-01-04", "loss"),
        ]
        events = _compute_streaks_v2(rows)
        assert len(events) == 4
        assert all(e.length == 1 for e in events)

    def test_streak_types(self):
        rows = [
            self._row("2024-01-01", "win"),
            self._row("2024-01-02", "win"),
            self._row("2024-01-03", "loss"),
            self._row("2024-01-04", "loss"),
            self._row("2024-01-05", "loss"),
            self._row("2024-01-06", "win"),
        ]
        events = _compute_streaks_v2(rows)
        assert len(events) == 3
        assert events[0].type == "win" and events[0].length == 2
        assert events[1].type == "loss" and events[1].length == 3
        assert events[2].type == "win" and events[2].length == 1

    def test_start_and_end_dates(self):
        rows = [
            self._row("2024-01-01", "win"),
            self._row("2024-01-02", "win"),
            self._row("2024-01-03", "loss"),
        ]
        events = _compute_streaks_v2(rows)
        assert events[0].start_at == "2024-01-01"
        assert events[0].end_at == "2024-01-02"
        assert events[1].start_at == "2024-01-03"
        assert events[1].end_at == "2024-01-03"


# ── get_streak_stats ──────────────────────────────────────────────


class TestGetStreakStats:
    def test_empty_db_returns_zero(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        stats = get_streak_stats(db_path=db)
        assert stats.trades == 0
        assert stats.max_win_streak == 0
        assert stats.max_loss_streak == 0
        assert stats.current_streak_type == "none"

    def test_max_win_streak(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(5):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00", "EUR/USD", "buy", "win")
            _insert_trade(conn, "2024-01-06 09:00:00", "EUR/USD", "buy", "loss")
            for i in range(3):
                _insert_trade(conn, f"2024-01-0{i+7} 09:00:00", "EUR/USD", "buy", "win")
        stats = get_streak_stats(db_path=db)
        assert stats.max_win_streak == 5

    def test_max_loss_streak(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00", "EUR/USD", "buy", "win")
            for i in range(4):
                _insert_trade(conn, f"2024-01-0{i+2} 09:00:00", "EUR/USD", "buy", "loss")
        stats = get_streak_stats(db_path=db)
        assert stats.max_loss_streak == 4

    def test_current_streak_win(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00", "EUR/USD", "buy", "loss")
            for i in range(3):
                _insert_trade(conn, f"2024-01-0{i+2} 09:00:00", "EUR/USD", "buy", "win")
        stats = get_streak_stats(db_path=db)
        assert stats.current_streak_type == "win"
        assert stats.current_streak_length == 3

    def test_current_streak_loss(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00", "EUR/USD", "buy", "win")
            for i in range(2):
                _insert_trade(conn, f"2024-01-0{i+2} 09:00:00", "EUR/USD", "buy", "loss")
        stats = get_streak_stats(db_path=db)
        assert stats.current_streak_type == "loss"
        assert stats.current_streak_length == 2

    def test_filters_by_symbol(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(5):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00", "EUR/USD", "buy", "win")
            for i in range(2):
                _insert_trade(conn, f"2024-02-0{i+1} 09:00:00", "USD/JPY", "sell", "loss")
        stats_eur = get_streak_stats(symbol="EUR/USD", db_path=db)
        stats_jpy = get_streak_stats(symbol="USD/JPY", db_path=db)
        assert stats_eur.trades == 5
        assert stats_jpy.trades == 2

    def test_avg_win_streak(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        # Two win streaks: length 2 and length 4 → avg = 3.0
        with get_db(db) as conn:
            for i in range(2):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00", "EUR/USD", "buy", "win")
            _insert_trade(conn, "2024-01-03 09:00:00", "EUR/USD", "buy", "loss")
            for i in range(4):
                _insert_trade(conn, f"2024-01-0{i+4} 09:00:00", "EUR/USD", "buy", "win")
        stats = get_streak_stats(db_path=db)
        assert stats.avg_win_streak == pytest.approx(3.0)

    def test_total_streak_counts(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        # W W L W L L W → 3 win streaks, 2 loss streaks
        outcomes = ["win", "win", "loss", "win", "loss", "loss", "win"]
        with get_db(db) as conn:
            for i, o in enumerate(outcomes):
                _insert_trade(conn, f"2024-01-{i+1:02d} 09:00:00", "EUR/USD", "buy", o)
        stats = get_streak_stats(db_path=db)
        assert stats.total_win_streaks == 3
        assert stats.total_loss_streaks == 2

    def test_excludes_open_trades(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00", "EUR/USD", "buy", "win")
            # open trade
            conn.execute(
                """INSERT INTO approval_history
                   (created_at, symbol, signal, human_action, score, rsi,
                    daily_trend, h4_trend, h1_status, is_dummy_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("2024-01-02 09:00:00", "EUR/USD", "BUY", "buy",
                 3, 50.0, "上昇", "上昇", "上昇", 0),
            )
        stats = get_streak_stats(db_path=db)
        assert stats.trades == 1

    def test_symbol_none_aggregates_all(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(3):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00", "EUR/USD", "buy", "win")
            for i in range(2):
                _insert_trade(conn, f"2024-02-0{i+1} 09:00:00", "USD/JPY", "sell", "loss")
        stats = get_streak_stats(db_path=db)
        assert stats.trades == 5

    def test_longest_win_streak_start_date(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00", "EUR/USD", "buy", "win")
            _insert_trade(conn, "2024-01-02 09:00:00", "EUR/USD", "buy", "loss")
            for i in range(3):
                _insert_trade(conn, f"2024-01-0{i+3} 09:00:00", "EUR/USD", "buy", "win")
        stats = get_streak_stats(db_path=db)
        assert stats.max_win_streak == 3
        assert stats.longest_win_streak_start == "2024-01-03"


# ── get_streak_stats_by_symbol ────────────────────────────────────


class TestGetStreakStatsBySymbol:
    def test_empty_returns_empty(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        result = get_streak_stats_by_symbol(db_path=db)
        assert result == []

    def test_two_symbols(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00", "EUR/USD", "buy", "win")
            _insert_trade(conn, "2024-01-02 09:00:00", "USD/JPY", "sell", "loss")
        result = get_streak_stats_by_symbol(db_path=db)
        assert len(result) == 2
        symbols = {s.symbol for s in result}
        assert symbols == {"EUR/USD", "USD/JPY"}

    def test_returns_streak_stats_instances(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00", "EUR/USD", "buy", "win")
        result = get_streak_stats_by_symbol(db_path=db)
        assert all(isinstance(s, StreakStats) for s in result)


# ── API エンドポイント ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_streaks_no_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/streaks")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "max_win_streak" in data
    assert "max_loss_streak" in data
    assert "current_streak_type" in data


@pytest.mark.asyncio
async def test_api_streaks_valid_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/streaks?symbol=EUR/USD")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["symbol"] == "EUR/USD"


@pytest.mark.asyncio
async def test_api_streaks_invalid_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/streaks?symbol=INVALID")
    data = res.json()
    assert data["ok"] is True
    assert data["symbol"] is None


@pytest.mark.asyncio
async def test_api_streaks_response_fields():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/streaks")
    data = res.json()
    for field in [
        "trades", "max_win_streak", "max_loss_streak",
        "current_streak_type", "current_streak_length",
        "avg_win_streak", "avg_loss_streak",
        "total_win_streaks", "total_loss_streaks",
        "longest_win_streak_start", "longest_loss_streak_start",
        "streaks",
    ]:
        assert field in data, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_api_streaks_streaks_is_list():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/streaks")
    data = res.json()
    assert isinstance(data["streaks"], list)


@pytest.mark.asyncio
async def test_dashboard_page_renders():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/dashboard")
    assert res.status_code == 200
    assert "ダッシュボード" in res.text
