"""Phase 74: バックテスト結果グラフ化 テスト"""
from __future__ import annotations

from pathlib import Path


# ── テンプレート確認 ──────────────────────────────────────────────────────

def _tpl() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "backtest.html").read_text(encoding="utf-8")


class TestBacktestChartTemplate:
    def test_equity_svg_present(self):
        """累積損益グラフ用 SVG コンテナが存在する"""
        assert 'id="equity-svg"' in _tpl()

    def test_monthly_svg_present(self):
        """月次損益グラフ用 SVG コンテナが存在する"""
        assert 'id="monthly-svg"' in _tpl()

    def test_equity_curve_title(self):
        """累積損益グラフのタイトルが含まれる"""
        assert "累積損益グラフ" in _tpl()

    def test_monthly_chart_title(self):
        """月次損益グラフのタイトルが含まれる"""
        assert "月次損益" in _tpl()

    def test_bt_trades_js_var(self):
        """BT_TRADES JS変数が trades_json をセットする"""
        content = _tpl()
        assert "BT_TRADES" in content
        assert "trades_json" in content

    def test_equity_curve_js(self):
        """エクイティカーブ描画 JS が含まれる"""
        content = _tpl()
        assert "drawEquity" in content or "equity-svg" in content

    def test_monthly_chart_js(self):
        """月次棒グラフ描画 JS が含まれる"""
        content = _tpl()
        assert "drawMonthly" in content or "monthly-svg" in content

    def test_pnl_pips_used_in_cumulative(self):
        """pnl_pips が累積計算に使われている"""
        content = _tpl()
        assert "pnl_pips" in content

    def test_win_color_green(self):
        """勝ちトレードが緑で表示される"""
        content = _tpl()
        # 4ade80 はシステム内の緑色
        assert "#4ade80" in content

    def test_loss_color_red(self):
        """負けトレードが赤で表示される"""
        content = _tpl()
        assert "#f87171" in content

    def test_zero_line_drawn(self):
        """ゼロライン（基準線）が描画される"""
        content = _tpl()
        assert "zeroY" in content or "ゼロ" in content

    def test_phase74_comment(self):
        """Phase 74 のコメントが含まれる"""
        assert "Phase 74" in _tpl()

    def test_chart_inside_trades_conditional(self):
        """グラフは trades が存在する場合のみ描画される"""
        content = _tpl()
        # BT_TRADES の前に if result.trades がある
        bt_idx = content.find("BT_TRADES")
        # その前に {% if result.trades %} があるはず
        before = content[:bt_idx]
        assert "result.trades" in before

    def test_outcome_dot_coloring(self):
        """各取引ドットが outcome に応じて色付けされる"""
        content = _tpl()
        assert "outcome" in content

    def test_grid_lines_drawn(self):
        """グリッドラインが描画される"""
        content = _tpl()
        assert "グリッドライン" in content or "stroke=\"#1e2040\"" in content


# ── routes.py 確認（ソース直読み） ────────────────────────────────────────

def _routes_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "routes.py").read_text(encoding="utf-8")


def _backtest_route_src() -> str:
    src = _routes_src()
    start = src.find("async def backtest_page(")
    if start == -1:
        return ""
    end = src.find("\n@router", start + 1)
    return src[start:end] if end != -1 else src[start:]


class TestBacktestRoute:
    def test_trades_json_in_context(self):
        """trades_json がテンプレートコンテキストに渡される"""
        assert "trades_json" in _backtest_route_src()

    def test_dc_asdict_used(self):
        """dataclasses.asdict でシリアライズされる"""
        src = _backtest_route_src()
        assert "asdict" in src

    def test_json_dumps_used(self):
        """json.dumps でJSON化される"""
        src = _backtest_route_src()
        assert "json.dumps" in src

    def test_empty_fallback(self):
        """トレードなし時は [] にフォールバック"""
        assert '"[]"' in _backtest_route_src()

    def test_phase74_comment_in_route(self):
        """Phase 74 のコメントが routes.py に含まれる"""
        assert "Phase 74" in _backtest_route_src()
