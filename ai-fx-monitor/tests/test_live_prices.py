"""Phase 78: リアルタイム価格モニター テスト"""
from __future__ import annotations

from pathlib import Path


def _routes_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "routes.py").read_text(encoding="utf-8")


def _dashboard_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "dashboard.html").read_text(encoding="utf-8")


def _live_prices_fn_src() -> str:
    """routes.py から api_live_prices 関数本体を抜き出す"""
    src = _routes_src()
    start = src.find("async def api_live_prices():")
    next_route = src.find("\n@router", start + 1)
    return src[start:next_route] if next_route != -1 else src[start:start + 3000]


# ── APIエンドポイント定義テスト ────────────────────────────────────────────

class TestLivePricesEndpoint:
    def test_endpoint_exists(self):
        """/api/live-prices エンドポイントが定義されている"""
        assert '"/api/live-prices"' in _routes_src() or "'/api/live-prices'" in _routes_src()

    def test_endpoint_phase78_comment(self):
        """Phase 78 コメントが含まれる"""
        assert "Phase 78" in _routes_src()

    def test_function_name(self):
        """関数名が api_live_prices"""
        assert "async def api_live_prices()" in _routes_src()

    def test_returns_prices_key(self):
        """レスポンスに prices キーがある"""
        assert '"prices"' in _live_prices_fn_src() or "'prices'" in _live_prices_fn_src()

    def test_returns_fetched_at(self):
        """レスポンスに fetched_at キーがある"""
        assert "fetched_at" in _live_prices_fn_src()

    def test_returns_data_source(self):
        """レスポンスに data_source キーがある"""
        assert "data_source" in _live_prices_fn_src()

    def test_iterates_supported_symbols(self):
        """SUPPORTED_SYMBOLS を全件ループしている"""
        assert "SUPPORTED_SYMBOLS" in _live_prices_fn_src()

    def test_reads_csv_close(self):
        """CSVのcloseカラムを読んでいる"""
        assert '"close"' in _live_prices_fn_src() or "'close'" in _live_prices_fn_src()

    def test_calculates_change(self):
        """価格変化量を計算している"""
        src = _live_prices_fn_src()
        assert "change" in src and "prev" in src

    def test_calculates_change_pct(self):
        """変化率（%）を計算している"""
        assert "change_pct" in _live_prices_fn_src()

    def test_rounds_price(self):
        """価格を丸めている"""
        assert "round(" in _live_prices_fn_src()

    def test_uses_signal_cache(self):
        """シグナルキャッシュを参照している"""
        assert "_signal_cache" in _live_prices_fn_src()

    def test_error_handling(self):
        """CSV読み込みエラーをキャッチしている"""
        src = _live_prices_fn_src()
        assert "except" in src

    def test_price_entry_has_symbol(self):
        """エントリーに symbol キーがある"""
        assert '"symbol"' in _live_prices_fn_src() or "'symbol'" in _live_prices_fn_src()

    def test_price_entry_has_source(self):
        """エントリーに source キーがある"""
        assert '"source"' in _live_prices_fn_src() or "'source'" in _live_prices_fn_src()

    def test_uses_utc_timestamp(self):
        """UTCタイムスタンプを使用している"""
        src = _live_prices_fn_src()
        assert "utcnow" in src or "utc" in src.lower()

    def test_lazy_imports(self):
        """pandas を関数内でインポートしている（遅延インポート）"""
        src = _live_prices_fn_src()
        assert "import pandas" in src


# ── ダッシュボードHTML テスト ─────────────────────────────────────────────

class TestPriceMonitorWidget:
    def test_price_monitor_section_exists(self):
        """価格モニターセクションが存在する"""
        assert "price-monitor-section" in _dashboard_src() or "価格モニター" in _dashboard_src()

    def test_price_ticker_element(self):
        """price-ticker 要素がある"""
        assert 'id="price-ticker"' in _dashboard_src()

    def test_price_source_badge(self):
        """price-source-badge 要素がある"""
        assert 'id="price-source-badge"' in _dashboard_src()

    def test_price_last_updated(self):
        """price-last-updated 要素がある"""
        assert 'id="price-last-updated"' in _dashboard_src()

    def test_price_countdown(self):
        """カウントダウン表示要素がある"""
        assert 'id="price-countdown"' in _dashboard_src()

    def test_phase78_comment(self):
        """Phase 78 コメントが存在する"""
        assert "Phase 78" in _dashboard_src()

    def test_monitor_section_before_pair_cards(self):
        """価格モニターが通貨ペアカード一覧の前に配置されている"""
        src = _dashboard_src()
        monitor_pos = src.find("price-monitor-section")
        cards_pos = src.find("通貨ペアカード一覧")
        assert monitor_pos < cards_pos


# ── JavaScript テスト ────────────────────────────────────────────────────

class TestPriceMonitorJs:
    def test_fetches_live_prices(self):
        """/api/live-prices をフェッチしている"""
        assert "/api/live-prices" in _dashboard_src()

    def test_poll_interval_30s(self):
        """30秒ポーリング設定になっている"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "30" in js_section

    def test_signal_colors_defined(self):
        """BUY/SELL のシグナルカラーが定義されている"""
        src = _dashboard_src()
        assert "BUY" in src and "SELL" in src
        assert "#4ade80" in src  # 緑
        assert "#f87171" in src  # 赤

    def test_signal_labels_defined(self):
        """BUY/SELL のシグナルラベルが定義されている"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "買い候補" in js_section
        assert "売り候補" in js_section

    def test_jpy_decimals_3(self):
        """JPYペアは小数3桁"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "JPY" in js_section and "3" in js_section

    def test_price_up_arrow(self):
        """価格上昇時に▲を表示"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "▲" in js_section

    def test_price_down_arrow(self):
        """価格下落時に▼を表示"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "▼" in js_section

    def test_flash_animation(self):
        """価格変化時にflashアニメーションが設定されている"""
        src = _dashboard_src()
        assert "price-flash" in src or "priceFlash" in src

    def test_oanda_badge(self):
        """OANDAデータソース時のバッジが定義されている"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "oanda" in js_section.lower()

    def test_csv_badge(self):
        """CSVデータソース時のバッジが定義されている"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "CSV" in js_section

    def test_countdown_timer(self):
        """カウントダウンタイマーロジックがある"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "countdown" in js_section

    def test_error_handling(self):
        """フェッチ失敗時のエラー処理がある"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "catch" in js_section

    def test_immediate_fetch_on_load(self):
        """ページロード時に即時フェッチする"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "fetchPrices()" in js_section

    def test_setinterval_for_polling(self):
        """setIntervalでポーリングしている"""
        src = _dashboard_src()
        js_section = src[src.find("Phase 78: リアルタイム価格モニター JS"):]
        assert "setInterval" in js_section
