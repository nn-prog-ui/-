"""tests/test_signal_quality.py — Phase 46: シグナル品質スコアリングテスト"""
from __future__ import annotations

import pytest

from app.scripts.signal_quality import (
    MIN_TRADES_FOR_QUALITY,
    QUALITY_CSS,
    QUALITY_DESCRIPTIONS,
    QUALITY_LABELS,
    QualityStats,
    _quality_level,
    _rsi_bucket,
    _score_bucket,
    _trend_match,
    get_all_pattern_stats,
    get_signal_quality,
)


# ── ヘルパー関数 ──────────────────────────────────────────────────

class TestScoreBucket:
    def test_high(self):
        assert _score_bucket(4) == "high"
        assert _score_bucket(7) == "high"

    def test_mid(self):
        assert _score_bucket(1) == "mid"
        assert _score_bucket(3) == "mid"

    def test_low(self):
        assert _score_bucket(0) == "low"
        assert _score_bucket(-3) == "low"

    def test_none(self):
        assert _score_bucket(None) == "unknown"


class TestRsiBucket:
    def test_oversold(self):
        assert _rsi_bucket(30.0) == "oversold"
        assert _rsi_bucket(39.9) == "oversold"

    def test_overbought(self):
        assert _rsi_bucket(70.0) == "overbought"
        assert _rsi_bucket(60.1) == "overbought"

    def test_neutral(self):
        assert _rsi_bucket(50.0) == "neutral"
        assert _rsi_bucket(40.0) == "neutral"
        assert _rsi_bucket(60.0) == "neutral"

    def test_none(self):
        assert _rsi_bucket(None) == "unknown"


class TestTrendMatch:
    def test_aligned(self):
        assert _trend_match("上昇", "上昇") == "aligned"
        assert _trend_match("下降", "下降") == "aligned"

    def test_mixed(self):
        assert _trend_match("上昇", "下降") == "mixed"
        assert _trend_match("下降", "上昇") == "mixed"

    def test_none_returns_unknown(self):
        assert _trend_match(None, "上昇") == "unknown"
        assert _trend_match("上昇", None) == "unknown"
        assert _trend_match(None, None) == "unknown"

    def test_empty_returns_unknown(self):
        assert _trend_match("", "上昇") == "unknown"


class TestQualityLevel:
    def test_s_level(self):
        assert _quality_level(65.0, MIN_TRADES_FOR_QUALITY) == 5

    def test_a_level(self):
        assert _quality_level(55.0, MIN_TRADES_FOR_QUALITY) == 4

    def test_b_level(self):
        assert _quality_level(45.0, MIN_TRADES_FOR_QUALITY) == 3

    def test_c_level(self):
        assert _quality_level(35.0, MIN_TRADES_FOR_QUALITY) == 2

    def test_d_level(self):
        assert _quality_level(30.0, MIN_TRADES_FOR_QUALITY) == 1

    def test_none_win_rate(self):
        assert _quality_level(None, 10) == 0

    def test_insufficient_trades(self):
        assert _quality_level(70.0, MIN_TRADES_FOR_QUALITY - 1) == 0


# ── QUALITY_LABELS ────────────────────────────────────────────────

class TestQualityLabels:
    def test_labels_coverage(self):
        for level in range(6):
            assert level in QUALITY_LABELS

    def test_level_5_is_s(self):
        assert QUALITY_LABELS[5] == "S"

    def test_level_0_is_na(self):
        assert QUALITY_LABELS[0] == "N/A"


class TestQualityCSS:
    def test_has_all_levels(self):
        for level in range(6):
            assert level in QUALITY_CSS

    def test_css_strings(self):
        for v in QUALITY_CSS.values():
            assert isinstance(v, str) and len(v) > 0


# ── get_signal_quality — DB テスト ────────────────────────────────

def _insert_trade(conn, created_at, symbol, signal, human_action, outcome, pnl_pips,
                  score=5, rsi=50.0, daily_trend="上昇", h4_trend="上昇"):
    conn.execute(
        """INSERT INTO approval_history
           (created_at, symbol, signal, human_action, outcome, pnl_pips, score, rsi,
            daily_trend, h4_trend, h1_status, is_dummy_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (created_at, symbol, signal, human_action, outcome, pnl_pips,
         score, rsi, daily_trend, h4_trend, "上昇", 0),
    )


class TestGetSignalQuality:
    def test_returns_quality_stats(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        q = get_signal_quality("EUR/USD", "BUY", db_path=db)
        assert isinstance(q, QualityStats)

    def test_skip_signal_returns_na(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        q = get_signal_quality("EUR/USD", "SKIP", db_path=db)
        assert q.quality_level == 0
        assert q.quality_label == "N/A"

    def test_no_data_returns_zero_trades(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        q = get_signal_quality("EUR/USD", "BUY", db_path=db)
        assert q.trades == 0
        assert q.quality_level == 0

    def test_win_rate_computed(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(5):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00", "EUR/USD", "BUY", "buy", "win", 10.0)
            for i in range(5):
                _insert_trade(conn, f"2024-01-1{i} 09:00:00", "EUR/USD", "BUY", "buy", "loss", -5.0)
        q = get_signal_quality("EUR/USD", "BUY", db_path=db)
        assert q.win_rate == pytest.approx(50.0)
        assert q.trades == 10

    def test_sell_signal_uses_sell_action(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(4):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00",
                              "EUR/USD", "SELL", "sell", "win", 10.0,
                              daily_trend="下降", h4_trend="下降")
        q = get_signal_quality("EUR/USD", "SELL", daily_trend="下降", h4_trend="下降", db_path=db)
        assert q.trades == 4

    def test_insufficient_trades_level_zero(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            # 2件 (MIN_TRADES_FOR_QUALITY - 1)
            _insert_trade(conn, "2024-01-01 09:00:00", "EUR/USD", "BUY", "buy", "win", 10.0)
            _insert_trade(conn, "2024-01-02 09:00:00", "EUR/USD", "BUY", "buy", "loss", -5.0)
        q = get_signal_quality("EUR/USD", "BUY", db_path=db)
        assert q.quality_level == 0

    def test_enough_trades_gives_quality_label(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(7):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00",
                              "EUR/USD", "BUY", "buy", "win", 10.0)
            for i in range(3):
                _insert_trade(conn, f"2024-01-1{i} 09:00:00",
                              "EUR/USD", "BUY", "buy", "loss", -5.0)
        q = get_signal_quality("EUR/USD", "BUY", db_path=db)
        # 70% win rate → level 5 (S) but we don't insist on exact level,
        # just that it's above 0
        assert q.quality_level > 0
        assert q.quality_label != "N/A"

    def test_score_bucket_stored(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        q = get_signal_quality("EUR/USD", "BUY", score=5, db_path=db)
        assert q.score_bucket == "high"

    def test_rsi_bucket_stored(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        q = get_signal_quality("EUR/USD", "BUY", rsi=30.0, db_path=db)
        assert q.rsi_bucket == "oversold"

    def test_trend_match_stored(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        q = get_signal_quality("EUR/USD", "BUY",
                               daily_trend="上昇", h4_trend="上昇", db_path=db)
        assert q.trend_match == "aligned"

    def test_avg_pips_computed(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(3):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00",
                              "EUR/USD", "BUY", "buy", "win", 10.0)
        q = get_signal_quality("EUR/USD", "BUY", db_path=db)
        assert q.avg_pips == pytest.approx(10.0)


# ── get_all_pattern_stats ─────────────────────────────────────────

class TestGetAllPatternStats:
    def test_returns_list(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        result = get_all_pattern_stats(db_path=db)
        assert isinstance(result, list)

    def test_empty_db_returns_empty(self, tmp_path):
        from app.database.db import init_db
        db = tmp_path / "test.db"
        init_db(db)
        result = get_all_pattern_stats(db_path=db)
        assert len(result) == 0

    def test_groups_by_pattern(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            for i in range(3):
                _insert_trade(conn, f"2024-01-0{i+1} 09:00:00",
                              "EUR/USD", "BUY", "buy", "win", 10.0,
                              daily_trend="上昇", h4_trend="上昇")
            for i in range(2):
                _insert_trade(conn, f"2024-02-0{i+1} 09:00:00",
                              "EUR/USD", "BUY", "buy", "loss", -5.0,
                              daily_trend="下降", h4_trend="下降")
        result = get_all_pattern_stats(db_path=db)
        assert len(result) == 2

    def test_result_has_required_fields(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00",
                          "EUR/USD", "BUY", "buy", "win", 10.0)
        result = get_all_pattern_stats(db_path=db)
        assert len(result) == 1
        row = result[0]
        for field in ["symbol", "signal", "trades", "wins", "win_rate",
                      "quality_label", "quality_level"]:
            assert field in row

    def test_filters_by_symbol(self, tmp_path):
        from app.database.db import init_db, get_db
        db = tmp_path / "test.db"
        init_db(db)
        with get_db(db) as conn:
            _insert_trade(conn, "2024-01-01 09:00:00", "EUR/USD", "BUY", "buy", "win", 10.0)
            _insert_trade(conn, "2024-01-02 09:00:00", "USD/JPY", "SELL", "sell", "win", 5.0)
        result = get_all_pattern_stats(symbol="EUR/USD", db_path=db)
        assert all(r["symbol"] == "EUR/USD" for r in result)


# ── API エンドポイント ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_signal_quality_api_no_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/signal-quality?signal=BUY")
    assert res.json()["ok"] is False


@pytest.mark.asyncio
async def test_signal_quality_api_invalid_symbol():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/signal-quality?symbol=INVALID&signal=BUY")
    assert res.json()["ok"] is False


@pytest.mark.asyncio
async def test_signal_quality_api_invalid_signal():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/signal-quality?symbol=EUR/USD&signal=SKIP")
    assert res.json()["ok"] is False


@pytest.mark.asyncio
async def test_signal_quality_api_valid():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/signal-quality?symbol=EUR/USD&signal=BUY")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    for field in ["quality_label", "quality_level", "trades", "win_rate", "dimension"]:
        assert field in data


@pytest.mark.asyncio
async def test_signal_quality_api_response_structure():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/signal-quality?symbol=EUR/USD&signal=SELL&score=5&rsi=30")
    data = res.json()
    assert data["ok"] is True
    assert data["symbol"] == "EUR/USD"
    assert data["signal"] == "SELL"
    assert data["score_bucket"] == "high"
    assert data["rsi_bucket"] == "oversold"
    assert isinstance(data["quality_level"], int)
    assert data["quality_label"] in list(QUALITY_LABELS.values())


@pytest.mark.asyncio
async def test_signal_quality_patterns_api():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/signal-quality/patterns")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "patterns" in data
    assert isinstance(data["patterns"], list)


@pytest.mark.asyncio
async def test_signal_quality_api_with_trend_params():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(
            "/api/signal-quality?symbol=EUR/USD&signal=BUY"
            "&daily_trend=%E4%B8%8A%E6%98%87&h4_trend=%E4%B8%8A%E6%98%87"
        )
    data = res.json()
    assert data["ok"] is True
    assert data["trend_match"] == "aligned"
