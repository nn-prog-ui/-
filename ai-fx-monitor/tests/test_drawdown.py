"""tests/test_drawdown.py — Phase 47: ドローダウン分析テスト"""
from __future__ import annotations

import math

import pytest

from app.scripts.drawdown import (
    DrawdownStats,
    EquityPoint,
    _build_equity_curve,
    _compute_stats,
    equity_curve_to_chart_data,
    get_drawdown_by_symbol,
    get_drawdown_stats,
)


# ── テスト用 DB ヘルパー ──────────────────────────────────────────


def _insert_trade(conn, created_at, symbol, signal, human_action, outcome, pnl_pips):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips,
            score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, signal, human_action, outcome, pnl_pips,
         3, 50.0, "上昇", "上昇", "上昇", 0),
    )


# ── EquityPoint ───────────────────────────────────────────────────


class TestBuildEquityCurve:
    def _make_row(self, created_at, pnl):
        class R(dict):
            def __getitem__(self, k):
                return {"created_at": created_at, "pnl_pips": pnl}[k]
        return R()

    def test_empty_returns_empty(self):
        assert _build_equity_curve([]) == []

    def test_single_win(self):
        class Row:
            def __getitem__(self, k):
                return {"created_at": "2024-01-01 09:00:00", "pnl_pips": 10.0}[k]

        curve = _build_equity_curve([Row()])
        assert len(curve) == 1
        assert curve[0].equity == pytest.approx(10.0)
        assert curve[0].drawdown == 0.0
        assert curve[0].peak == pytest.approx(10.0)

    def test_drawdown_after_loss(self):
        rows = [
            {"created_at": "2024-01-01", "pnl_pips": 10.0},
            {"created_at": "2024-01-02", "pnl_pips": -5.0},
        ]

        class DictRow(dict):
            def __getitem__(self, k):
                return super().__getitem__(k)

        curve = _build_equity_curve([DictRow(r) for r in rows])
        assert curve[0].drawdown == 0.0
        assert curve[1].equity == pytest.approx(5.0)
        assert curve[1].drawdown == pytest.approx(-5.0)

    def test_index_increments(self):
        rows = [{"created_at": f"2024-01-0{i+1}", "pnl_pips": 1.0} for i in range(3)]

        class DictRow(dict):
            def __getitem__(self, k):
                return super().__getitem__(k)

        curve = _build_equity_curve([DictRow(r) for r in rows])
        assert [p.index for p in curve] == [1, 2, 3]

    def test_null_pnl_treated_as_zero(self):
        rows = [{"created_at": "2024-01-01", "pnl_pips": None}]

        class DictRow(dict):
            def __getitem__(self, k):
                return super().__getitem__(k)

        curve = _build_equity_curve([DictRow(r) for r in rows])
        assert curve[0].pnl_pips == 0.0
        assert curve[0].equity == 0.0


# ── _compute_stats ────────────────────────────────────────────────


class TestComputeStats:
    def test_empty_returns_zero_stats(self):
        stats = _compute_stats(None, [], [])
        assert stats.trades == 0
        assert stats.max_drawdown == 0.0
        assert stats.total_pips == 0.0

    def test_all_wins(self):
        curve = [
            EquityPoint(i + 1, f"2024-01-0{i+1}", 10.0, float((i + 1) * 10), float((i + 1) * 10), 0.0, 0.0)
            for i in range(5)
        ]
        stats = _compute_stats("EUR/USD", curve, [10.0] * 5)
        assert stats.trades == 5
        assert stats.total_pips == pytest.approx(50.0)
        assert stats.max_drawdown == 0.0
        assert stats.win_rate == pytest.approx(100.0)

    def test_profit_factor(self):
        # 3 wins × 10, 1 loss × -5 → PF = 30/5 = 6
        curve = [
            EquityPoint(1, "2024-01-01", 10.0, 10.0, 10.0, 0.0, 0.0),
            EquityPoint(2, "2024-01-02", 10.0, 20.0, 20.0, 0.0, 0.0),
            EquityPoint(3, "2024-01-03", 10.0, 30.0, 30.0, 0.0, 0.0),
            EquityPoint(4, "2024-01-04", -5.0, 25.0, 30.0, -5.0, -16.67),
        ]
        stats = _compute_stats("EUR/USD", curve, [10.0, 10.0, 10.0, -5.0])
        assert stats.profit_factor == pytest.approx(6.0)

    def test_risk_reward(self):
        stats = _compute_stats(
            "EUR/USD",
            [EquityPoint(i + 1, "2024", 0.0, 0.0, 0.0, 0.0, 0.0) for i in range(4)],
            [20.0, 20.0, -10.0, -10.0],
        )
        assert stats.avg_win_pips == pytest.approx(20.0)
        assert stats.avg_loss_pips == pytest.approx(10.0)
        assert stats.risk_reward == pytest.approx(2.0)

    def test_recovery_factor_no_drawdown(self):
        curve = [EquityPoint(1, "2024", 10.0, 10.0, 10.0, 0.0, 0.0)]
        stats = _compute_stats(None, curve, [10.0])
        assert math.isinf(stats.recovery_factor)

    def test_recovery_factor_with_drawdown(self):
        curve = [
            EquityPoint(1, "2024", 20.0, 20.0, 20.0, 0.0, 0.0),
            EquityPoint(2, "2024", -10.0, 10.0, 20.0, -10.0, -50.0),
            EquityPoint(3, "2024", 10.0, 20.0, 20.0, 0.0, 0.0),
        ]
        stats = _compute_stats(None, curve, [20.0, -10.0, 10.0])
        assert stats.recovery_factor == pytest.approx(2.0)

    def test_longest_drawdown_bars(self):
        curve = [
            EquityPoint(1, "2024", 10.0, 10.0, 10.0, 0.0, 0.0),
            EquityPoint(2, "2024", -3.0, 7.0, 10.0, -3.0, -30.0),
            EquityPoint(3, "2024", -2.0, 5.0, 10.0, -5.0, -50.0),
            EquityPoint(4, "2024", 5.0, 10.0, 10.0, 0.0, 0.0),
            EquityPoint(5, "2024", -1.0, 9.0, 10.0, -1.0, -10.0),
        ]
        stats = _compute_stats(None, curve, [10.0, -3.0, -2.0, 5.0, -1.0])
        assert stats.longest_drawdown_bars == 2

    def test_no_losses_profit_factor(self):
        curve = [EquityPoint(1, "2024", 5.0, 5.0, 5.0, 0.0, 0.0)]
        stats = _compute_stats(None, curve, [5.0])
        assert math.isinf(stats.profit_factor)


# ── equity_curve_to_chart_data ────────────────────────────────────


class TestEquityCurveToChartData:
    def test_empty_curve(self):
        result = equity_curve_to_chart_data([])
        assert result["labels"] == []
        assert result["equity"] == []
        assert result["drawdown"] == []

    def test_structure(self):
        curve = [
            EquityPoint(1, "2024-01-01 09:00:00", 10.0, 10.0, 10.0, 0.0, 0.0),
            EquityPoint(2, "2024-01-02 09:00:00", -5.0, 5.0, 10.0, -5.0, -50.0),
        ]
        result = equity_curve_to_chart_data(curve)
        assert result["labels"] == ["2024-01-01", "2024-01-02"]
        assert result["equity"] == [10.0, 5.0]
        assert result["drawdown"] == [0.0, -5.0]


# ── get_drawdown_stats — DB テスト ────────────────────────────────


class TestGetDrawdownStats:
    def test_empty_db_returns_zero(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        stats = get_drawdown_stats(db_path=db)
        assert stats.trades == 0
        assert stats.total_pips == 0.0

    def test_win_rate_50(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(3):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00",
                              "EUR/USD", "BUY", "buy", "win", 10.0)
            for i in range(3):
                _insert_trade(conn, f"2024-01-1{i} 09:00:00",
                              "EUR/USD", "BUY", "buy", "loss", -5.0)
        stats = get_drawdown_stats(db_path=db)
        assert stats.win_rate == pytest.approx(50.0)
        assert stats.trades == 6

    def test_filters_by_symbol(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(3):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00",
                              "EUR/USD", "BUY", "buy", "win", 10.0)
            for i in range(2):
                _insert_trade(conn, f"2024-02-0{i+1} 09:00:00",
                              "USD/JPY", "SELL", "sell", "win", 5.0)
        stats = get_drawdown_stats(symbol="EUR/USD", db_path=db)
        assert stats.trades == 3
        assert stats.symbol == "EUR/USD"

    def test_max_drawdown_correct(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00",
                          "EUR/USD", "BUY", "buy", "win", 20.0)
            _insert_trade(conn, "2024-01-02 09:00:00",
                          "EUR/USD", "BUY", "buy", "loss", -15.0)
            _insert_trade(conn, "2024-01-03 09:00:00",
                          "EUR/USD", "BUY", "buy", "win", 10.0)
        stats = get_drawdown_stats(db_path=db)
        # peak=20, then equity=5 → drawdown=-15
        assert stats.max_drawdown == pytest.approx(-15.0)

    def test_excludes_open_trades(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00",
                          "EUR/USD", "BUY", "buy", "win", 10.0)
            # open trade (outcome=NULL)
            conn.execute(
                """INSERT INTO approval_history
                   (created_at, symbol, signal, human_action, pnl_pips,
                    score, rsi, daily_trend, h4_trend, h1_status, is_dummy_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("2024-01-02 09:00:00", "EUR/USD", "BUY", "buy", None,
                 3, 50.0, "上昇", "上昇", "上昇", 0),
            )
        stats = get_drawdown_stats(db_path=db)
        assert stats.trades == 1

    def test_symbol_none_aggregates_all(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00",
                          "EUR/USD", "BUY", "buy", "win", 10.0)
            _insert_trade(conn, "2024-01-02 09:00:00",
                          "USD/JPY", "SELL", "sell", "loss", -5.0)
        stats = get_drawdown_stats(db_path=db)
        assert stats.trades == 2


class TestGetDrawdownBySymbol:
    def test_empty_db(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        result = get_drawdown_by_symbol(db_path=db)
        assert result == []

    def test_two_symbols(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00",
                          "EUR/USD", "BUY", "buy", "win", 10.0)
            _insert_trade(conn, "2024-01-02 09:00:00",
                          "USD/JPY", "SELL", "sell", "win", 5.0)
        result = get_drawdown_by_symbol(db_path=db)
        assert len(result) == 2
        symbols = {s.symbol for s in result}
        assert symbols == {"EUR/USD", "USD/JPY"}

    def test_each_entry_is_drawdown_stats(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00",
                          "EUR/USD", "BUY", "buy", "win", 10.0)
        result = get_drawdown_by_symbol(db_path=db)
        assert len(result) == 1
        assert isinstance(result[0], DrawdownStats)


# ── API エンドポイント ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_drawdown_no_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/drawdown")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "trades" in data
    assert "max_drawdown" in data
    assert "chart_data" in data


@pytest.mark.asyncio
async def test_api_drawdown_valid_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/drawdown?symbol=EUR/USD")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["symbol"] == "EUR/USD"


@pytest.mark.asyncio
async def test_api_drawdown_invalid_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/drawdown?symbol=INVALID")
    data = res.json()
    # invalid symbol treated as None (all symbols)
    assert data["ok"] is True
    assert data["symbol"] is None


@pytest.mark.asyncio
async def test_drawdown_page_renders():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/drawdown")
    assert res.status_code == 200
    assert "ドローダウン分析" in res.text


@pytest.mark.asyncio
async def test_drawdown_page_with_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/drawdown?symbol=EUR/USD")
    assert res.status_code == 200
    assert "EUR/USD" in res.text


@pytest.mark.asyncio
async def test_api_drawdown_response_fields():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/drawdown")
    data = res.json()
    for field in [
        "trades", "total_pips", "max_drawdown", "max_drawdown_pct",
        "avg_drawdown", "longest_drawdown_bars", "recovery_factor",
        "profit_factor", "avg_win_pips", "avg_loss_pips",
        "risk_reward", "win_rate", "chart_data",
    ]:
        assert field in data, f"Missing field: {field}"
