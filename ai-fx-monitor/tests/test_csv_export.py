"""Phase 80: CSVエクスポート機能 テスト"""
from __future__ import annotations

from pathlib import Path


def _routes_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "routes.py").read_text(encoding="utf-8")


def _repo_src() -> str:
    return (Path(__file__).parent.parent / "app" / "database" / "repository.py").read_text(encoding="utf-8")


def _history_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "history.html").read_text(encoding="utf-8")


def _performance_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "performance.html").read_text(encoding="utf-8")


def _closed_trades_route() -> str:
    src = _routes_src()
    start = src.find("async def export_closed_trades(")
    next_route = src.find("\n@router", start + 1)
    return src[start:next_route] if next_route != -1 else src[start:start + 1500]


def _monthly_stats_route() -> str:
    src = _routes_src()
    start = src.find("async def export_monthly_stats(")
    next_route = src.find("\n@router", start + 1)
    return src[start:next_route] if next_route != -1 else src[start:start + 1000]


# ── リポジトリ関数テスト ────────────────────────────────────────────────────

class TestClosedTradesForExport:
    def test_function_exists(self):
        """get_closed_trades_for_export 関数が存在する"""
        assert "def get_closed_trades_for_export" in _repo_src()

    def test_filters_outcome_not_null(self):
        """outcome IS NOT NULL でフィルターしている"""
        src = _repo_src()
        fn = src[src.find("def get_closed_trades_for_export"):]
        assert "outcome IS NOT NULL" in fn

    def test_filters_approved_actions(self):
        """buy_approved / sell_approved に限定している"""
        src = _repo_src()
        fn = src[src.find("def get_closed_trades_for_export"):]
        assert "buy_approved" in fn and "sell_approved" in fn

    def test_symbol_filter(self):
        """symbol フィルターをサポートしている"""
        src = _repo_src()
        fn = src[src.find("def get_closed_trades_for_export"):]
        assert "symbol" in fn

    def test_date_from_filter(self):
        """date_from フィルターをサポートしている"""
        src = _repo_src()
        fn = src[src.find("def get_closed_trades_for_export"):]
        assert "date_from" in fn

    def test_date_to_filter(self):
        """date_to フィルターをサポートしている"""
        src = _repo_src()
        fn = src[src.find("def get_closed_trades_for_export"):]
        assert "date_to" in fn

    def test_includes_pnl_pips(self):
        """pnl_pips カラムを含んでいる"""
        src = _repo_src()
        fn = src[src.find("def get_closed_trades_for_export"):]
        assert "pnl_pips" in fn

    def test_includes_outcome(self):
        """outcome カラムを含んでいる"""
        src = _repo_src()
        fn = src[src.find("def get_closed_trades_for_export"):]
        assert "outcome" in fn

    def test_phase80_comment(self):
        """Phase 80 コメントがある"""
        assert "Phase 80" in _repo_src()


class TestMonthlyStatsForExport:
    def test_function_exists(self):
        """get_monthly_stats_for_export 関数が存在する"""
        assert "def get_monthly_stats_for_export" in _repo_src()

    def test_groups_by_month(self):
        """月次グルーピングしている"""
        src = _repo_src()
        fn = src[src.find("def get_monthly_stats_for_export"):]
        assert "GROUP BY" in fn and "month" in fn.lower()

    def test_includes_win_rate(self):
        """勝率カラムを含んでいる"""
        src = _repo_src()
        fn = src[src.find("def get_monthly_stats_for_export"):]
        assert "win_rate" in fn

    def test_includes_total_pips(self):
        """total_pips カラムを含んでいる"""
        src = _repo_src()
        fn = src[src.find("def get_monthly_stats_for_export"):]
        assert "total_pips" in fn

    def test_includes_symbol(self):
        """symbol 別に集計している"""
        src = _repo_src()
        fn = src[src.find("def get_monthly_stats_for_export"):]
        assert "symbol" in fn

    def test_orders_by_month_desc(self):
        """月降順でソートしている"""
        src = _repo_src()
        fn = src[src.find("def get_monthly_stats_for_export"):]
        assert "ORDER BY" in fn and "DESC" in fn


# ── ルートエンドポイントテスト ───────────────────────────────────────────────

class TestClosedTradesEndpoint:
    def test_endpoint_exists(self):
        """/export/closed-trades.csv エンドポイントが存在する"""
        assert "/export/closed-trades.csv" in _routes_src()

    def test_endpoint_phase80_comment(self):
        """Phase 80 コメントが含まれる"""
        assert "Phase 80" in _routes_src()

    def test_calls_get_closed_trades(self):
        """get_closed_trades_for_export を呼んでいる"""
        assert "get_closed_trades_for_export" in _closed_trades_route()

    def test_symbol_param(self):
        """symbol クエリパラメータをサポート"""
        assert "symbol" in _closed_trades_route()

    def test_date_from_param(self):
        """date_from クエリパラメータをサポート"""
        assert "date_from" in _closed_trades_route()

    def test_date_to_param(self):
        """date_to クエリパラメータをサポート"""
        assert "date_to" in _closed_trades_route()

    def test_filename_has_today(self):
        """ファイル名に今日の日付が含まれる"""
        assert "today" in _closed_trades_route() or "_date" in _closed_trades_route()

    def test_returns_csv(self):
        """_rows_to_csv を使っている"""
        assert "_rows_to_csv" in _closed_trades_route()


class TestMonthlyStatsEndpoint:
    def test_endpoint_exists(self):
        """/export/monthly-stats.csv エンドポイントが存在する"""
        assert "/export/monthly-stats.csv" in _routes_src()

    def test_calls_get_monthly_stats(self):
        """get_monthly_stats_for_export を呼んでいる"""
        assert "get_monthly_stats_for_export" in _monthly_stats_route()

    def test_returns_csv(self):
        """_rows_to_csv を使っている"""
        assert "_rows_to_csv" in _monthly_stats_route()

    def test_imports_in_routes(self):
        """routes.py のインポートに追加されている"""
        src = _routes_src()
        imports = src[:src.find("@router.get")]
        assert "get_closed_trades_for_export" in imports
        assert "get_monthly_stats_for_export" in imports


# ── history.html テスト ──────────────────────────────────────────────────────

class TestHistoryExportUI:
    def test_phase80_comment_in_history(self):
        """history.html に Phase 80 コメントがある"""
        assert "Phase 80" in _history_src()

    def test_date_from_input(self):
        """日付From入力フィールドがある"""
        assert "exportDateFrom" in _history_src()

    def test_date_to_input(self):
        """日付To入力フィールドがある"""
        assert "exportDateTo" in _history_src()

    def test_symbol_select(self):
        """シンボルセレクトがある"""
        assert "exportSymbol" in _history_src()

    def test_export_with_filter_function(self):
        """exportWithFilter JS関数が定義されている"""
        assert "function exportWithFilter" in _history_src()

    def test_closed_trades_export_button(self):
        """勝敗確定のみエクスポートボタンがある"""
        assert "closed-trades.csv" in _history_src() or "勝敗確定" in _history_src()

    def test_filter_button_calls_function(self):
        """絞込CSVボタンがexportWithFilterを呼ぶ"""
        src = _history_src()
        assert "exportWithFilter('history')" in src or 'exportWithFilter("history")' in src

    def test_closed_filter_button(self):
        """勝敗+絞込ボタンがexportWithFilterを呼ぶ"""
        src = _history_src()
        assert "exportWithFilter('closed')" in src or 'exportWithFilter("closed")' in src

    def test_js_builds_query_string(self):
        """JSがURLSearchParamsでクエリ文字列を組み立てる"""
        assert "URLSearchParams" in _history_src()

    def test_date_input_type(self):
        """日付入力がdate型"""
        assert 'type="date"' in _history_src()


# ── performance.html テスト ──────────────────────────────────────────────────

class TestPerformanceExportUI:
    def test_phase80_comment_in_performance(self):
        """performance.html に Phase 80 コメントがある"""
        assert "Phase 80" in _performance_src()

    def test_closed_trades_export_button(self):
        """クローズ済み取引CSVボタンがある"""
        assert "closed-trades.csv" in _performance_src()

    def test_monthly_stats_export_button(self):
        """月次統計CSVボタンがある"""
        assert "monthly-stats.csv" in _performance_src()

    def test_export_bar_exists(self):
        """export-bar クラスが存在する"""
        assert "export-bar" in _performance_src()

    def test_demo_orders_export_still_present(self):
        """既存のデモ注文CSVボタンが残っている"""
        assert "demo-orders.csv" in _performance_src()
