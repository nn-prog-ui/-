"""tests/test_charts.py — Phase 38: チャート表示テスト

/charts, /api/chart-stats エンドポイントのテスト。
/api/chart-data は既存テストでカバー済みのため、新規エンドポイントに集中。
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


# ── /charts ページ ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_charts_page_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/charts")
    assert res.status_code == 200
    assert "チャート" in res.text


@pytest.mark.asyncio
async def test_charts_page_contains_chart_js():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/charts")
    assert "chart.js" in res.text.lower() or "chart.umd" in res.text.lower()


@pytest.mark.asyncio
async def test_charts_page_contains_canvas_elements():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/charts")
    assert 'id="equity-chart"' in res.text
    assert 'id="monthly-chart"' in res.text
    assert 'id="winrate-chart"' in res.text
    assert 'id="signal-chart"' in res.text


@pytest.mark.asyncio
async def test_charts_page_with_symbol_param():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/charts?symbol=USD/JPY")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_charts_page_with_limit_param():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/charts?limit=50")
    assert res.status_code == 200


# ── /api/chart-stats ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_chart_stats_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-stats")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_chart_stats_has_monthly_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-stats")
    data = res.json()
    assert "monthly" in data
    assert isinstance(data["monthly"], list)


@pytest.mark.asyncio
async def test_chart_stats_has_by_signal_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-stats")
    data = res.json()
    assert "by_signal" in data
    assert isinstance(data["by_signal"], list)


@pytest.mark.asyncio
async def test_chart_stats_monthly_fields():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-stats")
    data = res.json()
    for m in data["monthly"]:
        assert "month" in m
        assert "wins" in m
        assert "losses" in m
        assert "total_pips" in m
        # win_rate は None か float
        assert "win_rate" in m


@pytest.mark.asyncio
async def test_chart_stats_by_signal_fields():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-stats")
    data = res.json()
    for s in data["by_signal"]:
        assert "signal" in s
        assert "wins" in s
        assert "losses" in s
        assert "total_pips" in s
        assert "avg_pips" in s
        assert "win_rate" in s


@pytest.mark.asyncio
async def test_chart_stats_monthly_win_rate_range():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-stats")
    data = res.json()
    for m in data["monthly"]:
        wr = m.get("win_rate")
        if wr is not None:
            assert 0.0 <= wr <= 100.0, f"月次勝率範囲外: {wr}"


@pytest.mark.asyncio
async def test_chart_stats_by_signal_only_valid_signals():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-stats")
    data = res.json()
    for s in data["by_signal"]:
        assert s["signal"] in ("BUY", "SELL", "SKIP", None)


# ── /api/chart-data 既存エンドポイントの追加テスト ─────────────
@pytest.mark.asyncio
async def test_chart_data_default():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-data")
    assert res.status_code == 200
    data = res.json()
    assert "trades" in data
    assert "count" in data
    assert "symbol" in data


@pytest.mark.asyncio
async def test_chart_data_with_symbol():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-data?symbol=USD/JPY&limit=20")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "USD/JPY"
    assert data["count"] <= 20


@pytest.mark.asyncio
async def test_chart_data_cumulative_pips_is_monotone_compatible():
    """累積pipsはトレードの順序と一致していることを確認。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/chart-data?limit=100")
    data = res.json()
    trades = data["trades"]
    if len(trades) < 2:
        return
    for i in range(1, len(trades)):
        prev = trades[i - 1]["cumulative_pips"]
        curr = trades[i]["cumulative_pips"]
        diff = round(curr - prev, 1)
        pnl  = round(trades[i].get("pnl_pips") or 0.0, 1)
        assert abs(diff - pnl) < 0.15, f"累積pips不整合: prev={prev} curr={curr} pnl={pnl}"
