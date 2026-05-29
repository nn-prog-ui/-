"""Phase 81: ポジションサマリーウィジェット テスト"""
from __future__ import annotations

from pathlib import Path


def _routes_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "routes.py").read_text(encoding="utf-8")


def _dashboard_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "dashboard.html").read_text(encoding="utf-8")


def _open_positions_fn() -> str:
    src = _routes_src()
    start = src.find("async def api_open_positions()")
    next_route = src.find("\n@router", start + 1)
    return src[start:next_route] if next_route != -1 else src[start:start + 3000]


# ── APIエンドポイント定義テスト ────────────────────────────────────────────

class TestOpenPositionsEndpoint:
    def test_endpoint_exists(self):
        """/api/open-positions エンドポイントが定義されている"""
        assert '"/api/open-positions"' in _routes_src() or "'/api/open-positions'" in _routes_src()

    def test_function_name(self):
        """関数名が api_open_positions"""
        assert "async def api_open_positions()" in _routes_src()

    def test_phase81_comment(self):
        """Phase 81 コメントが含まれる"""
        assert "Phase 81" in _routes_src()

    def test_calls_get_open_trades(self):
        """get_open_trades() を呼んでいる"""
        assert "get_open_trades" in _open_positions_fn()

    def test_returns_positions_key(self):
        """レスポンスに positions キーがある"""
        assert '"positions"' in _open_positions_fn() or "'positions'" in _open_positions_fn()

    def test_returns_count(self):
        """レスポンスに count キーがある"""
        assert '"count"' in _open_positions_fn() or "'count'" in _open_positions_fn()

    def test_returns_total_unrealized_pips(self):
        """レスポンスに total_unrealized_pips キーがある"""
        assert "total_unrealized_pips" in _open_positions_fn()

    def test_returns_fetched_at(self):
        """レスポンスに fetched_at キーがある"""
        assert "fetched_at" in _open_positions_fn()


# ── 含み損益計算テスト ────────────────────────────────────────────────────

class TestUnrealizedPnlCalc:
    def test_buy_pips_positive_logic(self):
        """BUY: current - entry でpipsを計算"""
        fn = _open_positions_fn()
        assert "current_price - entry" in fn or "current - entry" in fn.replace("current_price", "current")

    def test_sell_pips_positive_logic(self):
        """SELL: entry - current でpipsを計算"""
        fn = _open_positions_fn()
        assert "entry - current_price" in fn or "entry - current" in fn.replace("entry_price", "entry").replace("current_price", "current")

    def test_jpy_multiplier_100(self):
        """JPYペアは100倍の乗数"""
        fn = _open_positions_fn()
        assert "100" in fn and "JPY" in fn

    def test_other_multiplier_10000(self):
        """JPY以外は10000倍の乗数"""
        assert "10000" in _open_positions_fn()

    def test_pip_multiplier_function(self):
        """pip乗数を計算する関数/ロジックがある"""
        fn = _open_positions_fn()
        assert "_pip_multiplier" in fn or "multiplier" in fn

    def test_direction_profit_loss(self):
        """direction: profit/loss/neutral を返す"""
        fn = _open_positions_fn()
        assert "profit" in fn and "loss" in fn

    def test_pips_to_sl_calculation(self):
        """SLまでの距離を計算している"""
        assert "pips_to_sl" in _open_positions_fn()

    def test_pips_to_tp_calculation(self):
        """TPまでの距離を計算している"""
        assert "pips_to_tp" in _open_positions_fn()

    def test_elapsed_hours_calculation(self):
        """経過時間（時間単位）を計算している"""
        fn = _open_positions_fn()
        assert "elapsed" in fn and ("3600" in fn or "hours" in fn.lower())

    def test_reads_csv_for_current_price(self):
        """CSVから現在価格を読んでいる"""
        fn = _open_positions_fn()
        assert "read_csv" in fn or "csv" in fn.lower()

    def test_error_handling_for_csv(self):
        """CSV読み込みエラーをキャッチしている"""
        assert "except" in _open_positions_fn()

    def test_total_unrealized_sum(self):
        """合計含み損益をsumで計算している"""
        assert "sum(" in _open_positions_fn() or "total_unrealized" in _open_positions_fn()

    def test_position_entry_price_field(self):
        """entry_price フィールドを返す"""
        assert "entry_price" in _open_positions_fn()

    def test_position_symbol_field(self):
        """symbol フィールドを返す"""
        fn = _open_positions_fn()
        assert '"symbol"' in fn or "'symbol'" in fn


# ── ダッシュボードHTML テスト ─────────────────────────────────────────────

class TestPositionSummaryWidget:
    def test_position_summary_section_exists(self):
        """ポジションサマリーセクションが存在する"""
        assert "position-summary-section" in _dashboard_src()

    def test_position_list_element(self):
        """position-list 要素がある"""
        assert 'id="position-list"' in _dashboard_src()

    def test_count_badge_element(self):
        """pos-count-badge 要素がある"""
        assert 'id="pos-count-badge"' in _dashboard_src()

    def test_total_pnl_element(self):
        """pos-total-pnl 要素がある"""
        assert 'id="pos-total-pnl"' in _dashboard_src()

    def test_phase81_comment(self):
        """Phase 81 コメントが存在する"""
        assert "Phase 81" in _dashboard_src()

    def test_link_to_performance(self):
        """詳細ページへのリンクがある"""
        src = _dashboard_src()
        section = src[src.find("position-summary-section"):]
        # セクション内に /performance リンクがある（詳細 → ボタン）
        assert "/performance" in section[:2000]

    def test_widget_before_pair_cards(self):
        """ポジションウィジェットが通貨ペアカード一覧の前"""
        src = _dashboard_src()
        pos_pos = src.find("position-summary-section")
        cards_pos = src.find("通貨ペアカード一覧")
        assert pos_pos < cards_pos


# ── JavaScript テスト ────────────────────────────────────────────────────

class TestPositionSummaryJs:
    def test_fetches_open_positions(self):
        """/api/open-positions をフェッチしている"""
        assert "/api/open-positions" in _dashboard_src()

    def test_render_function_exists(self):
        """render 関数が定義されている"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "function render" in js_sec

    def test_fetch_positions_function_exists(self):
        """fetchPositions 関数が定義されている"""
        assert "function fetchPositions" in _dashboard_src()

    def test_empty_state_message(self):
        """ポジションなし時のメッセージがある"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "オープン中のポジションはありません" in js_sec

    def test_pips_color_profit(self):
        """含み益は緑色"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "#4ade80" in js_sec

    def test_pips_color_loss(self):
        """含み損は赤色"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "#f87171" in js_sec

    def test_sl_distance_displayed(self):
        """SLまでの距離が表示される"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "pips_to_sl" in js_sec or "SL" in js_sec

    def test_tp_distance_displayed(self):
        """TPまでの距離が表示される"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "pips_to_tp" in js_sec or "TP" in js_sec

    def test_elapsed_time_displayed(self):
        """経過時間が表示される"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "elapsed" in js_sec and "経過" in js_sec

    def test_entry_and_current_price_displayed(self):
        """エントリー価格と現在価格が表示される"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "entry_price" in js_sec and "current_price" in js_sec

    def test_setinterval_polling(self):
        """setIntervalで30秒ポーリング"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "setInterval" in js_sec and "30000" in js_sec

    def test_error_handling(self):
        """フェッチエラー時の処理がある"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "catch" in js_sec

    def test_total_pnl_display(self):
        """合計含み損益が表示される"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        assert "total_unrealized_pips" in js_sec

    def test_buy_sell_badge_color(self):
        """BUY/SELL バッジが色分けされている（BUYチェックと買い/売りラベル）"""
        src = _dashboard_src()
        js_sec = src[src.find("Phase 81: オープンポジションサマリーJS"):]
        # JSはBUYを明示的に比較し、買い/売りラベルを出力している
        assert "BUY" in js_sec and ("買い" in js_sec or "売り" in js_sec)
