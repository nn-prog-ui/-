"""Phase 82: 履歴ページリアルタイム検索 テスト"""
from __future__ import annotations

from pathlib import Path


def _history_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "history.html").read_text(encoding="utf-8")


def _js_section() -> str:
    src = _history_src()
    marker = "Phase 82: リアルタイム検索JS"
    idx = src.find(marker)
    return src[idx:idx + 5000] if idx != -1 else ""


# ── HTML構造テスト ──────────────────────────────────────────────────────────


class TestHistorySearchUI:
    def test_phase82_comment(self):
        """Phase 82 コメントが存在する"""
        assert "Phase 82" in _history_src()

    def test_search_section_exists(self):
        """history-search-section が存在する"""
        assert 'id="history-search-section"' in _history_src()

    def test_search_input_exists(self):
        """history-search-input が存在する"""
        assert 'id="history-search-input"' in _history_src()

    def test_search_clear_button_exists(self):
        """history-search-clear ボタンが存在する"""
        assert 'id="history-search-clear"' in _history_src()

    def test_search_count_element_exists(self):
        """history-search-count 要素が存在する"""
        assert 'id="history-search-count"' in _history_src()

    def test_no_results_element_exists(self):
        """history-no-results 要素が存在する"""
        assert 'id="history-no-results"' in _history_src()

    def test_quick_filters_section_exists(self):
        """history-quick-filters 要素が存在する"""
        assert 'id="history-quick-filters"' in _history_src()

    def test_search_input_has_oninput(self):
        """検索入力に oninput イベントが設定されている"""
        src = _history_src()
        inp_idx = src.find('id="history-search-input"')
        # 前後の文脈から oninput を確認
        ctx = src[max(0, inp_idx - 200):inp_idx + 500]
        assert "oninput" in ctx and "filterHistory" in ctx

    def test_search_section_before_history_list(self):
        """検索セクションが履歴リストの前にある"""
        src = _history_src()
        search_pos = src.find("history-search-section")
        list_pos   = src.find("history-list")
        assert search_pos < list_pos

    def test_no_results_message_text(self):
        """検索結果なしメッセージのテキスト"""
        assert "検索条件に一致する履歴はありません" in _history_src()

    def test_search_placeholder_text(self):
        """プレースホルダーが検索対象を案内している"""
        src = _history_src()
        assert "placeholder" in src and "絞り込み" in src


# ── クイックフィルターボタンテスト ──────────────────────────────────────────


class TestHistoryQuickFilters:
    def test_h_filter_btn_class_used(self):
        """h-filter-btn クラスが使われている"""
        assert "h-filter-btn" in _history_src()

    def test_all_filter_exists(self):
        """全て フィルターボタンがある"""
        src = _history_src()
        assert "data-filter=\"all\"" in src or "data-filter='all'" in src

    def test_buy_filter_exists(self):
        """BUY フィルターボタンがある"""
        src = _history_src()
        assert "data-filter=\"BUY\"" in src or "data-filter='BUY'" in src

    def test_sell_filter_exists(self):
        """SELL フィルターボタンがある"""
        src = _history_src()
        assert "data-filter=\"SELL\"" in src or "data-filter='SELL'" in src

    def test_skip_filter_exists(self):
        """SKIP フィルターボタンがある"""
        src = _history_src()
        assert "data-filter=\"SKIP\"" in src or "data-filter='SKIP'" in src

    def test_buy_approved_filter_exists(self):
        """buy_approved フィルターボタンがある"""
        src = _history_src()
        assert "buy_approved" in src and "h-filter-btn" in src

    def test_sell_approved_filter_exists(self):
        """sell_approved フィルターボタンがある"""
        assert "sell_approved" in _history_src()

    def test_win_filter_exists(self):
        """勝ち (win) フィルターボタンがある"""
        src = _history_src()
        assert "data-filter=\"win\"" in src or "data-filter='win'" in src

    def test_loss_filter_exists(self):
        """負け (loss) フィルターボタンがある"""
        src = _history_src()
        assert "data-filter=\"loss\"" in src or "data-filter='loss'" in src

    def test_all_filter_is_active_by_default(self):
        """全て ボタンがデフォルトで active クラスを持つ"""
        src = _history_src()
        # "全て" ボタンの近くに active クラスがある
        all_btn_idx = src.find("data-filter=\"all\"")
        ctx = src[max(0, all_btn_idx - 50):all_btn_idx + 100]
        assert "active" in ctx

    def test_apply_quick_filter_on_click(self):
        """ボタンの onclick に applyQuickFilter が設定されている"""
        assert "applyQuickFilter" in _history_src()

    def test_filter_css_hover_style(self):
        """h-filter-btn に hover スタイルが定義されている"""
        src = _history_src()
        assert ".h-filter-btn:hover" in src


# ── カードデータ属性テスト ───────────────────────────────────────────────────


class TestHistoryCardDataAttributes:
    def test_data_signal_attribute(self):
        """history-card に data-signal 属性がある"""
        assert "data-signal=" in _history_src()

    def test_data_action_attribute(self):
        """history-card に data-action 属性がある"""
        assert "data-action=" in _history_src()

    def test_data_outcome_attribute(self):
        """history-card に data-outcome 属性がある"""
        assert "data-outcome=" in _history_src()

    def test_data_symbol_attribute(self):
        """history-card に data-symbol 属性がある"""
        assert "data-symbol=" in _history_src()

    def test_data_attributes_on_article(self):
        """article.history-card に data 属性がテンプレート変数で設定されている"""
        src = _history_src()
        # Jinja テンプレート変数で設定されていることを確認
        assert 'data-signal="{{ r.signal' in src or "data-signal=\"{{ r.signal" in src


# ── JavaScriptテスト ─────────────────────────────────────────────────────────


class TestHistorySearchJs:
    def test_phase82_js_comment(self):
        """Phase 82 JS コメントが存在する"""
        assert "Phase 82: リアルタイム検索JS" in _history_src()

    def test_filter_history_function_exists(self):
        """filterHistory 関数が定義されている"""
        assert "filterHistory" in _js_section() and "function" in _js_section()

    def test_apply_quick_filter_function_exists(self):
        """applyQuickFilter 関数が定義されている"""
        js = _js_section()
        assert "applyQuickFilter" in js

    def test_clear_history_search_function_exists(self):
        """clearHistorySearch 関数が定義されている"""
        assert "clearHistorySearch" in _js_section()

    def test_uses_text_content_for_search(self):
        """textContent を使ったキーワード検索が実装されている"""
        assert "textContent" in _js_section()

    def test_filters_by_dataset_signal(self):
        """dataset.signal でシグナルフィルタリングしている"""
        assert "dataset.signal" in _js_section()

    def test_filters_by_dataset_action(self):
        """dataset.action でアクションフィルタリングしている"""
        assert "dataset.action" in _js_section()

    def test_filters_by_dataset_outcome(self):
        """dataset.outcome で勝敗フィルタリングしている"""
        assert "dataset.outcome" in _js_section()

    def test_win_loss_filter_logic(self):
        """win/loss の判定ロジックがある"""
        js = _js_section()
        assert "win" in js and "loss" in js

    def test_dom_content_loaded_init(self):
        """DOMContentLoaded で初期化している"""
        assert "DOMContentLoaded" in _js_section()

    def test_active_class_toggle(self):
        """classList.toggle で active クラスを制御"""
        js = _js_section()
        assert "classList.toggle" in js and "active" in js

    def test_clear_button_visibility(self):
        """クリアボタンの表示/非表示を制御している"""
        js = _js_section()
        assert "history-search-clear" in js

    def test_count_display_logic(self):
        """件数表示ロジックがある"""
        js = _js_section()
        assert "countEl" in js and "件" in js

    def test_no_results_display_logic(self):
        """no-results 表示ロジックがある"""
        js = _js_section()
        assert "noResults" in js and "display" in js

    def test_query_cards_selector(self):
        """history-card を querySelectorAll で取得している"""
        js = _js_section()
        assert "querySelectorAll" in js and "history-card" in js

    def test_active_filter_variable(self):
        """_activeFilter 変数が定義されている"""
        assert "_activeFilter" in _js_section()

    def test_filter_all_is_default(self):
        """デフォルトフィルターは 'all'"""
        js = _js_section()
        assert "_activeFilter = 'all'" in js or '_activeFilter = "all"' in js

    def test_iife_wrapping(self):
        """IIFE（即時実行関数）でスコープが保護されている"""
        js = _js_section()
        assert "(function()" in js or "(() =>" in js

    def test_lowercase_search(self):
        """検索は大文字小文字を区別しない（toLowerCase）"""
        assert "toLowerCase" in _js_section()
