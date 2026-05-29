"""Phase 72: TradingView チャート埋め込み テスト"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ── テンプレート内容チェック ──────────────────────────────────────────────

def _get_template_content() -> str:
    from pathlib import Path
    tpl = Path(__file__).parent.parent / "app" / "web" / "templates" / "index.html"
    return tpl.read_text(encoding="utf-8")


class TestTradingViewTemplate:
    def test_tradingview_script_present(self):
        """tv.js スクリプトタグが含まれる"""
        content = _get_template_content()
        assert "https://s3.tradingview.com/tv.js" in content

    def test_tradingview_widget_init(self):
        """TradingView.widget() 初期化コードが含まれる"""
        content = _get_template_content()
        assert "new TradingView.widget(" in content

    def test_tradingview_container_id(self):
        """container_id が tradingview_main に設定されている"""
        content = _get_template_content()
        assert '"container_id": "tradingview_main"' in content

    def test_tradingview_div_present(self):
        """マウント先の div#tradingview_main が存在する"""
        content = _get_template_content()
        assert 'id="tradingview_main"' in content

    def test_dark_theme(self):
        """ダークテーマが設定されている"""
        content = _get_template_content()
        assert '"theme": "dark"' in content

    def test_japanese_locale(self):
        """日本語ロケールが設定されている"""
        content = _get_template_content()
        assert '"locale": "ja"' in content

    def test_tokyo_timezone(self):
        """東京タイムゾーンが設定されている"""
        content = _get_template_content()
        assert '"timezone": "Asia/Tokyo"' in content

    def test_autosize_true(self):
        """autosize が true に設定されている"""
        content = _get_template_content()
        assert '"autosize": true' in content

    def test_enable_publishing_false(self):
        """enable_publishing が false（パブリッシュボタン非表示）"""
        content = _get_template_content()
        assert '"enable_publishing": false' in content

    def test_allow_symbol_change_false(self):
        """allow_symbol_change が false（シンボル変更不可）"""
        content = _get_template_content()
        assert '"allow_symbol_change": false' in content

    def test_interval_60_minutes(self):
        """デフォルト時間足が60分（1時間足）"""
        content = _get_template_content()
        assert '"interval": "60"' in content

    def test_tv_symbols_mapping(self):
        """Jinja2 シンボルマッピングが含まれる"""
        content = _get_template_content()
        assert "FX:USDJPY" in content
        assert "FX:EURUSD" in content
        assert "FX:GBPUSD" in content
        assert "FX:EURJPY" in content

    def test_usdjpy_default_symbol(self):
        """デフォルトシンボルが FX:USDJPY"""
        content = _get_template_content()
        assert "FX:USDJPY" in content

    def test_powered_by_label(self):
        """'powered by TradingView' ラベルが表示される"""
        content = _get_template_content()
        assert "powered by TradingView" in content

    def test_chart_height_set(self):
        """チャートの高さが設定されている"""
        content = _get_template_content()
        assert "420" in content

    def test_old_svg_chart_removed(self):
        """旧SVGチャートのコードが削除されている"""
        content = _get_template_content()
        assert "candle-svg" not in content
        assert "drawCandles" not in content
        assert "loadChart" not in content

    def test_old_tf_tabs_removed(self):
        """旧時間足タブのコードが削除されている"""
        content = _get_template_content()
        assert 'id="tf-tabs"' not in content
        assert 'class="tf-btn"' not in content

    def test_old_candle_api_call_removed(self):
        """旧 /api/candles フェッチコードが削除されている"""
        content = _get_template_content()
        assert "/api/candles" not in content

    def test_chart_section_has_card_class(self):
        """チャートセクションに card クラスがある"""
        content = _get_template_content()
        # TradingView セクションの周辺に card がある
        tv_idx = content.find("tradingview_main")
        section_area = content[max(0, tv_idx - 300): tv_idx]
        assert 'class="card"' in section_area

    def test_phase72_comment_present(self):
        """Phase 72 のコメントが含まれる"""
        content = _get_template_content()
        assert "Phase 72" in content
