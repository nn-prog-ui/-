"""tests/test_heatmap_calendar.py — Phase 45: ヒートマップカレンダーテスト"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.scripts.heatmap_calendar import (
    WEEKDAY_LABELS,
    VALID_METRICS,
    HeatmapCell,
    HeatmapResult,
    _assess,
    _parse_created_at,
    build_heatmap,
    get_heatmap_rows,
)


# ── _parse_created_at ────────────────────────────────────────────

class TestParseCreatedAt:
    def test_standard_format(self):
        dt = _parse_created_at("2024-03-15 09:30:00")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 3
        assert dt.day == 15
        assert dt.hour == 9

    def test_iso_format(self):
        dt = _parse_created_at("2024-03-15T09:30:00")
        assert dt is not None
        assert dt.hour == 9

    def test_invalid_returns_none(self):
        assert _parse_created_at("not-a-date") is None

    def test_empty_returns_none(self):
        assert _parse_created_at("") is None

    def test_weekday_extraction(self):
        # 2024-01-01 は月曜日
        dt = _parse_created_at("2024-01-01 00:00:00")
        assert dt is not None
        assert dt.weekday() == 0  # 月曜


# ── WEEKDAY_LABELS ────────────────────────────────────────────────

class TestWeekdayLabels:
    def test_has_seven_labels(self):
        assert len(WEEKDAY_LABELS) == 7

    def test_monday_first(self):
        assert WEEKDAY_LABELS[0] == "月"

    def test_sunday_last(self):
        assert WEEKDAY_LABELS[6] == "日"

    def test_all_strings(self):
        for lbl in WEEKDAY_LABELS:
            assert isinstance(lbl, str) and len(lbl) > 0


# ── VALID_METRICS ─────────────────────────────────────────────────

class TestValidMetrics:
    def test_has_win_rate(self):
        assert "win_rate" in VALID_METRICS

    def test_has_total_pips(self):
        assert "total_pips" in VALID_METRICS


# ── build_heatmap — バリデーション ──────────────────────────────

def test_invalid_metric_raises():
    with pytest.raises(ValueError, match="未対応"):
        build_heatmap([], metric="unknown_metric")


# ── build_heatmap — 正常系 ───────────────────────────────────────

def _make_rows(entries: list[tuple[str, str, float]]) -> list[dict]:
    """(created_at, outcome, pnl_pips) のリストから行データを生成。"""
    return [
        {"created_at": ca, "outcome": oc, "pnl_pips": pnl}
        for ca, oc, pnl in entries
    ]


class TestBuildHeatmap:
    def test_returns_heatmap_result(self):
        r = build_heatmap([])
        assert isinstance(r, HeatmapResult)

    def test_empty_rows_zero_trades(self):
        r = build_heatmap([])
        assert r.total_trades == 0

    def test_cells_dimensions_7x24(self):
        r = build_heatmap([])
        assert len(r.cells) == 7
        for row in r.cells:
            assert len(row) == 24

    def test_cells_are_heatmap_cell(self):
        r = build_heatmap([])
        for wd_row in r.cells:
            for c in wd_row:
                assert isinstance(c, HeatmapCell)

    def test_symbol_stored(self):
        r = build_heatmap([], symbol="EUR/USD")
        assert r.symbol == "EUR/USD"

    def test_metric_stored(self):
        r = build_heatmap([], metric="total_pips")
        assert r.metric == "total_pips"

    def test_single_win_row(self):
        rows = _make_rows([("2024-01-01 09:00:00", "win", 10.0)])
        r = build_heatmap(rows)
        assert r.total_trades == 1
        # 2024-01-01 は月曜日(weekday=0)、9時
        cell = r.cells[0][9]
        assert cell.trades == 1
        assert cell.wins == 1
        assert cell.win_rate == pytest.approx(100.0)

    def test_single_loss_row(self):
        rows = _make_rows([("2024-01-01 09:00:00", "loss", -5.0)])
        r = build_heatmap(rows)
        cell = r.cells[0][9]
        assert cell.losses == 1
        assert cell.win_rate == pytest.approx(0.0)

    def test_overall_win_rate_calculation(self):
        rows = _make_rows([
            ("2024-01-01 09:00:00", "win", 10.0),
            ("2024-01-01 10:00:00", "win", 8.0),
            ("2024-01-01 11:00:00", "loss", -5.0),
            ("2024-01-01 12:00:00", "loss", -4.0),
        ])
        r = build_heatmap(rows)
        assert r.overall_win_rate == pytest.approx(50.0)

    def test_total_pips_accumulated(self):
        rows = _make_rows([
            ("2024-01-01 09:00:00", "win", 10.0),
            ("2024-01-01 09:00:00", "win", 5.0),  # 同じセル
        ])
        r = build_heatmap(rows)
        cell = r.cells[0][9]
        assert cell.total_pips == pytest.approx(15.0)

    def test_avg_pips_computed(self):
        rows = _make_rows([
            ("2024-01-01 09:00:00", "win", 10.0),
            ("2024-01-01 09:00:00", "loss", -4.0),
        ])
        r = build_heatmap(rows)
        cell = r.cells[0][9]
        assert cell.avg_pips == pytest.approx(3.0)

    def test_invalid_date_skipped(self):
        rows = _make_rows([
            ("not-a-date", "win", 10.0),
            ("2024-01-01 09:00:00", "win", 5.0),
        ])
        r = build_heatmap(rows)
        assert r.total_trades == 1

    def test_empty_created_at_skipped(self):
        rows = [{"created_at": "", "outcome": "win", "pnl_pips": 10.0}]
        r = build_heatmap(rows)
        assert r.total_trades == 0

    def test_no_trades_win_rate_none(self):
        r = build_heatmap([])
        assert r.overall_win_rate is None

    def test_win_rate_per_cell_none_when_no_trades(self):
        r = build_heatmap([])
        # 全セルがゼロ取引 → win_rate は None
        for wd_row in r.cells:
            for c in wd_row:
                assert c.win_rate is None

    def test_multiple_weekdays(self):
        rows = _make_rows([
            ("2024-01-01 09:00:00", "win", 10.0),   # 月曜
            ("2024-01-02 09:00:00", "loss", -5.0),  # 火曜
            ("2024-01-06 09:00:00", "win", 8.0),    # 土曜
        ])
        r = build_heatmap(rows)
        assert r.total_trades == 3
        assert r.cells[0][9].trades == 1  # 月曜9時
        assert r.cells[1][9].trades == 1  # 火曜9時
        assert r.cells[5][9].trades == 1  # 土曜9時

    def test_total_pips_metric(self):
        rows = _make_rows([
            ("2024-01-01 09:00:00", "win", 20.0),
            ("2024-01-01 09:00:00", "loss", -5.0),
        ])
        r = build_heatmap(rows, metric="total_pips")
        assert r.metric == "total_pips"
        assert r.cells[0][9].total_pips == pytest.approx(15.0)

    def test_assessment_not_empty_with_data(self):
        rows = _make_rows([("2024-01-01 09:00:00", "win", 10.0)])
        r = build_heatmap(rows)
        assert r.assessment != ""

    def test_assessment_no_data(self):
        r = build_heatmap([])
        assert "データ" in r.assessment


# ── _assess ───────────────────────────────────────────────────────

class TestAssess:
    def _cells_with_one_active(self, wd: int, hour: int, wr: float, pips: float):
        cells = [
            [HeatmapCell(weekday=w, hour=h) for h in range(24)]
            for w in range(7)
        ]
        c = cells[wd][hour]
        c.trades = 5
        c.wins = int(wr * 5 / 100)
        c.losses = 5 - c.wins
        c.win_rate = wr
        c.total_pips = pips
        c.avg_pips = pips / 5
        return cells

    def test_no_data_message(self):
        cells = [[HeatmapCell(weekday=w, hour=h) for h in range(24)] for w in range(7)]
        text = _assess(cells, "win_rate", 0)
        assert "データ" in text

    def test_win_rate_metric_shows_best(self):
        cells = self._cells_with_one_active(0, 9, 70.0, 30.0)
        text = _assess(cells, "win_rate", 5)
        assert "最高勝率" in text

    def test_total_pips_metric_shows_best(self):
        cells = self._cells_with_one_active(2, 14, 60.0, 50.0)
        text = _assess(cells, "total_pips", 5)
        assert "最高損益" in text

    def test_trade_count_in_assessment(self):
        cells = self._cells_with_one_active(0, 9, 60.0, 20.0)
        text = _assess(cells, "win_rate", 5)
        assert "5" in text

    def test_parts_joined_by_slash(self):
        cells = self._cells_with_one_active(0, 9, 60.0, 20.0)
        text = _assess(cells, "win_rate", 5)
        assert "/" in text


# ── get_heatmap_rows — DBモック ───────────────────────────────────

class TestGetHeatmapRows:
    def test_returns_list(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        rows = get_heatmap_rows(db_path=db)
        assert isinstance(rows, list)

    def test_empty_db_returns_empty(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        rows = get_heatmap_rows(db_path=db)
        assert len(rows) == 0

    def test_filters_by_symbol(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, outcome, pnl_pips, is_dummy_data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2024-01-01 09:00:00", "EUR/USD", "BUY", "buy", "win", 10.0, 0),
            )
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, outcome, pnl_pips, is_dummy_data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2024-01-01 09:00:00", "USD/JPY", "SELL", "sell", "loss", -5.0, 0),
            )
        eur_rows = get_heatmap_rows(symbol="EUR/USD", db_path=db)
        assert len(eur_rows) == 1
        assert eur_rows[0]["outcome"] == "win"

    def test_filters_by_simulation(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, outcome, pnl_pips, is_dummy_data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2024-01-01 09:00:00", "EUR/USD", "BUY", "buy", "win", 10.0, 1),
            )
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, outcome, pnl_pips, is_dummy_data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("2024-01-01 10:00:00", "EUR/USD", "BUY", "buy", "loss", -5.0, 0),
            )
        sim_rows = get_heatmap_rows(is_simulation=True, db_path=db)
        assert len(sim_rows) == 1
        real_rows = get_heatmap_rows(is_simulation=False, db_path=db)
        assert len(real_rows) == 1
        all_rows = get_heatmap_rows(db_path=db)
        assert len(all_rows) == 2

    def test_excludes_null_outcome(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            conn.execute(
                "INSERT INTO approval_history (created_at, symbol, signal, human_action, is_dummy_data) "
                "VALUES (?, ?, ?, ?, ?)",
                ("2024-01-01 09:00:00", "EUR/USD", "BUY", "buy", 0),
            )
        rows = get_heatmap_rows(db_path=db)
        assert len(rows) == 0


# ── API エンドポイント ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heatmap_api_no_metric():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/heatmap-calendar?metric=invalid_metric")
    data = res.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_heatmap_api_invalid_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/heatmap-calendar?symbol=INVALID")
    data = res.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_heatmap_api_valid_empty_db():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    with patch("app.web.routes.get_heatmap_rows", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/heatmap-calendar")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["total_trades"] == 0
    assert "cells" in data
    assert "assessment" in data


@pytest.mark.asyncio
async def test_heatmap_api_with_data():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    mock_rows = [
        {"created_at": "2024-01-01 09:00:00", "outcome": "win", "pnl_pips": 10.0},
        {"created_at": "2024-01-01 10:00:00", "outcome": "loss", "pnl_pips": -5.0},
        {"created_at": "2024-01-02 09:00:00", "outcome": "win", "pnl_pips": 8.0},
    ]
    with patch("app.web.routes.get_heatmap_rows", return_value=mock_rows):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/heatmap-calendar?symbol=EUR/USD&metric=win_rate")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["total_trades"] == 3
    assert data["symbol"] == "EUR/USD"
    assert data["metric"] == "win_rate"


@pytest.mark.asyncio
async def test_heatmap_api_response_structure():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    with patch("app.web.routes.get_heatmap_rows", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/heatmap-calendar")
    data = res.json()
    assert isinstance(data["cells"], list)
    assert len(data["cells"]) == 7
    for row in data["cells"]:
        assert len(row) == 24
    assert isinstance(data["weekday_labels"], list)
    assert len(data["weekday_labels"]) == 7


@pytest.mark.asyncio
async def test_heatmap_api_total_pips_metric():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    with patch("app.web.routes.get_heatmap_rows", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/heatmap-calendar?metric=total_pips")
    data = res.json()
    assert data["ok"] is True
    assert data["metric"] == "total_pips"


@pytest.mark.asyncio
async def test_backtest_page_has_heatmap_section():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/backtest")
    assert res.status_code == 200
    assert "ヒートマップカレンダー" in res.text
    assert "hm-run-btn" in res.text
    assert "hm-table" in res.text
