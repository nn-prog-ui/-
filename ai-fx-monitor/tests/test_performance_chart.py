"""Phase 77: 成績ページ 月次損益グラフ テスト"""
from __future__ import annotations

from pathlib import Path


def _perf_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "performance.html").read_text(encoding="utf-8")


def _routes_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "routes.py").read_text(encoding="utf-8")


# ── HTML 構造テスト ─────────────────────────────────────────────────────────

class TestMonthlyChartHtml:
    def test_monthly_chart_section_exists(self):
        """月次損益セクションが存在する"""
        assert "月次損益（直近12ヶ月）" in _perf_src()

    def test_monthly_chart_svg_exists(self):
        """monthly-chart SVGが存在する"""
        assert 'id="monthly-chart"' in _perf_src()

    def test_monthly_chart_status_element(self):
        """monthly-status 要素が存在する"""
        assert 'id="monthly-status"' in _perf_src()

    def test_monthly_chart_phase77_comment(self):
        """Phase 77 コメントが含まれる"""
        assert "Phase 77" in _perf_src()

    def test_monthly_chart_width(self):
        """月次チャートの幅が760px"""
        src = _perf_src()
        monthly_section = src[src.find('id="monthly-chart"'):]
        assert 'width="760"' in monthly_section[:200]

    def test_monthly_chart_height(self):
        """月次チャートの高さが240px"""
        src = _perf_src()
        monthly_section = src[src.find('id="monthly-chart"'):]
        assert 'height="240"' in monthly_section[:200]


class TestSignalChartHtml:
    def test_signal_chart_section_exists(self):
        """シグナル別成績セクションが存在する"""
        assert "シグナル別成績" in _perf_src()

    def test_signal_chart_svg_exists(self):
        """signal-chart SVGが存在する"""
        assert 'id="signal-chart"' in _perf_src()

    def test_signal_chart_status_element(self):
        """signal-status 要素が存在する"""
        assert 'id="signal-status"' in _perf_src()

    def test_signal_chart_buy_sell_label(self):
        """BUY / SELL ラベルがある"""
        assert "BUY" in _perf_src()
        assert "SELL" in _perf_src()

    def test_signal_chart_width(self):
        """シグナルチャートの幅が760px"""
        src = _perf_src()
        signal_section = src[src.find('id="signal-chart"'):]
        assert 'width="760"' in signal_section[:200]


# ── JavaScript テスト ───────────────────────────────────────────────────────

class TestMonthlyChartJs:
    def test_drawMonthly_function_exists(self):
        """drawMonthly 関数が定義されている"""
        assert "function drawMonthly" in _perf_src()

    def test_drawMonthly_uses_total_pips(self):
        """月次チャートが total_pips を使用している"""
        assert "total_pips" in _perf_src()

    def test_drawMonthly_green_positive(self):
        """正の値に緑色を使用"""
        src = _perf_src()
        monthly_js = src[src.find("function drawMonthly"):]
        assert "#4ade80" in monthly_js

    def test_drawMonthly_red_negative(self):
        """負の値に赤色を使用"""
        src = _perf_src()
        monthly_js = src[src.find("function drawMonthly"):]
        assert "#f87171" in monthly_js

    def test_drawMonthly_reverses_order(self):
        """月次データを逆順（古い→新しい）で表示"""
        src = _perf_src()
        monthly_js = src[src.find("function drawMonthly"):]
        assert "reverse" in monthly_js

    def test_drawMonthly_tooltip(self):
        """バーにtooltip（title要素）がある"""
        src = _perf_src()
        monthly_js = src[src.find("function drawMonthly"):]
        assert "title" in monthly_js.lower() and "pips" in monthly_js

    def test_drawMonthly_empty_state(self):
        """データなし時のメッセージがある"""
        src = _perf_src()
        monthly_js = src[src.find("function drawMonthly"):]
        assert "クローズ済み取引がまだありません" in monthly_js

    def test_drawMonthly_y_axis_label(self):
        """Y軸に 'pips' ラベルがある"""
        src = _perf_src()
        monthly_js = src[src.find("function drawMonthly"):]
        assert "'pips'" in monthly_js or '"pips"' in monthly_js

    def test_drawMonthly_win_rate_tooltip(self):
        """tooltipに勝率が含まれる"""
        src = _perf_src()
        monthly_js = src[src.find("function drawMonthly"):]
        assert "win_rate" in monthly_js


class TestSignalChartJs:
    def test_drawBySignal_function_exists(self):
        """drawBySignal 関数が定義されている"""
        assert "function drawBySignal" in _perf_src()

    def test_drawBySignal_uses_wins_losses(self):
        """wins/losses を使用している"""
        src = _perf_src()
        signal_js = src[src.find("function drawBySignal"):]
        assert "wins" in signal_js and "losses" in signal_js

    def test_drawBySignal_win_bar_green(self):
        """勝ちバーが緑"""
        src = _perf_src()
        signal_js = src[src.find("function drawBySignal"):]
        assert "#4ade80" in signal_js

    def test_drawBySignal_loss_bar_red(self):
        """負けバーが赤"""
        src = _perf_src()
        signal_js = src[src.find("function drawBySignal"):]
        assert "#f87171" in signal_js

    def test_drawBySignal_avg_pips(self):
        """平均pipsが表示される"""
        src = _perf_src()
        signal_js = src[src.find("function drawBySignal"):]
        assert "avg_pips" in signal_js

    def test_drawBySignal_legend(self):
        """凡例（勝ち/負け）がある"""
        src = _perf_src()
        signal_js = src[src.find("function drawBySignal"):]
        assert "凡例" in signal_js or ("勝ち" in signal_js and "負け" in signal_js)

    def test_drawBySignal_empty_state(self):
        """データなし時のメッセージがある"""
        src = _perf_src()
        signal_js = src[src.find("function drawBySignal"):]
        assert "データがありません" in signal_js


# ── APIフェッチ テスト ──────────────────────────────────────────────────────

class TestChartStatsApiFetch:
    def test_fetches_chart_stats(self):
        """/api/chart-stats をフェッチしている"""
        assert "/api/chart-stats" in _perf_src()

    def test_fetch_calls_both_draw_functions(self):
        """フェッチ後に drawMonthly と drawBySignal を呼ぶ"""
        src = _perf_src()
        fetch_block = src[src.rfind("fetch('/api/chart-stats')"):]
        assert "drawMonthly" in fetch_block
        assert "drawBySignal" in fetch_block

    def test_fetch_error_handling(self):
        """フェッチエラー時にエラーメッセージを表示"""
        src = _perf_src()
        fetch_block = src[src.rfind("fetch('/api/chart-stats')"):]
        assert "catch" in fetch_block
        assert "失敗しました" in fetch_block

    def test_phase77_js_iife(self):
        """Phase 77 JSがIIFE（即時実行関数）でラップされている"""
        assert "(function() {" in _perf_src() or "(function(){" in _perf_src()


# ── APIエンドポイント テスト ─────────────────────────────────────────────────

class TestChartStatsApiEndpoint:
    def test_chart_stats_endpoint_exists(self):
        """/api/chart-stats エンドポイントが存在する"""
        assert '"/api/chart-stats"' in _routes_src() or "'/api/chart-stats'" in _routes_src() or "/api/chart-stats" in _routes_src()

    def test_chart_stats_returns_monthly(self):
        """chart-stats が monthly キーを返す"""
        src = _routes_src()
        stats_fn = src[src.find("async def api_chart_stats"):]
        next_fn = stats_fn.find("\n@router", 1)
        fn_body = stats_fn[:next_fn] if next_fn != -1 else stats_fn[:2000]
        assert '"monthly"' in fn_body or "'monthly'" in fn_body

    def test_chart_stats_returns_by_signal(self):
        """chart-stats が by_signal キーを返す"""
        src = _routes_src()
        stats_fn = src[src.find("async def api_chart_stats"):]
        next_fn = stats_fn.find("\n@router", 1)
        fn_body = stats_fn[:next_fn] if next_fn != -1 else stats_fn[:2000]
        assert '"by_signal"' in fn_body or "'by_signal'" in fn_body

    def test_chart_stats_monthly_has_total_pips(self):
        """monthly データに total_pips が含まれる"""
        src = _routes_src()
        stats_fn = src[src.find("async def api_chart_stats"):]
        next_fn = stats_fn.find("\n@router", 1)
        fn_body = stats_fn[:next_fn] if next_fn != -1 else stats_fn[:2000]
        assert "total_pips" in fn_body

    def test_chart_stats_monthly_has_win_rate(self):
        """monthly データに win_rate が含まれる"""
        src = _routes_src()
        stats_fn = src[src.find("async def api_chart_stats"):]
        next_fn = stats_fn.find("\n@router", 1)
        fn_body = stats_fn[:next_fn] if next_fn != -1 else stats_fn[:2000]
        assert "win_rate" in fn_body


# ── 既存チャートの共存テスト ─────────────────────────────────────────────────

class TestExistingChartCoexistence:
    def test_phase26_chart_still_exists(self):
        """Phase 26 の累積pipsチャートが引き続き存在する"""
        assert 'id="pips-chart"' in _perf_src()

    def test_phase26_chart_data_api_still_used(self):
        """/api/chart-data APIが引き続き使われている"""
        assert "/api/chart-data" in _perf_src()

    def test_all_three_svgs_present(self):
        """pips・monthly・signal の3つのSVGが存在する"""
        src = _perf_src()
        assert 'id="pips-chart"' in src
        assert 'id="monthly-chart"' in src
        assert 'id="signal-chart"' in src

    def test_section_ordering(self):
        """累積pips → 月次 → シグナル別 の順序"""
        src = _perf_src()
        pips_pos = src.find('id="pips-chart"')
        monthly_pos = src.find('id="monthly-chart"')
        signal_pos = src.find('id="signal-chart"')
        assert pips_pos < monthly_pos < signal_pos
