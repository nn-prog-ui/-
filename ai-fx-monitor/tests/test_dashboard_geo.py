"""Phase 73: 複数通貨ペア一覧ダッシュボード 地政学強化 テスト"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── テンプレート内容チェック ──────────────────────────────────────────────

def _tpl() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "dashboard.html").read_text(encoding="utf-8")


class TestDashboardTemplateGeo:
    def test_geo_banner_section_exists(self):
        """strong_bullish/bearish の場合のバナーセクションが存在する"""
        content = _tpl()
        assert "地政学リスク警戒中" in content

    def test_geo_banner_conditional(self):
        """バナーは strong_bullish/strong_bearish のみ表示（条件チェック）"""
        content = _tpl()
        assert "geo_risk_global in ('strong_bullish', 'strong_bearish')" in content

    def test_geo_bias_summary_card(self):
        """地政学バイアスのサマリーカードが概要バーに含まれる"""
        content = _tpl()
        assert "地政学バイアス" in content

    def test_manual_refresh_button(self):
        """手動更新ボタンが存在する"""
        content = _tpl()
        assert "btn-refresh" in content or "今すぐ更新" in content

    def test_geo_risk_badge_per_pair(self):
        """ペアカードに地政学リスクバッジが含まれる"""
        content = _tpl()
        assert "地政学:" in content or "地政学: " in content

    def test_geo_badge_conditional_neutral(self):
        """中立の場合はバッジを表示しない条件がある"""
        content = _tpl()
        assert "geo_risk_level != 'neutral'" in content

    def test_geo_score_breakdown_shown(self):
        """地政学補正がある場合にスコア内訳が表示される条件がある"""
        content = _tpl()
        assert "geo_score_adjustment" in content
        assert "技術" in content

    def test_geo_colors_used_in_badge(self):
        """geo_colors がバッジの色に使われている"""
        content = _tpl()
        assert "geo_colors.get(r.geo_risk_level" in content

    def test_geo_labels_used_in_badge(self):
        """geo_labels がバッジのラベルに使われている"""
        content = _tpl()
        assert "geo_labels.get(r.geo_risk_level" in content

    def test_geo_link_to_detail(self):
        """地政学バナーから詳細ページへのリンクがある"""
        content = _tpl()
        # バナー内に /geopolitical リンクがある
        banner_idx = content.find("地政学リスク警戒中")
        section_around = content[banner_idx: banner_idx + 500]
        assert "/geopolitical" in section_around

    def test_geo_latest_event_text_shown(self):
        """最新地政学イベントのテキストがバナーに表示される"""
        content = _tpl()
        assert "geo_latest.event_text" in content

    def test_geo_latest_event_date_shown(self):
        """最新地政学イベントの日付がバナーに表示される"""
        content = _tpl()
        assert "geo_latest.event_date" in content

    def test_geo_latest_category_shown(self):
        """最新地政学イベントのカテゴリーがバナーに表示される"""
        content = _tpl()
        assert "geo_latest.category" in content


# ── routes.py の dashboard 関数チェック（ソース直読みで Python 3.9 回避）──

def _routes_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "routes.py").read_text(encoding="utf-8")


def _dashboard_src() -> str:
    """dashboard 関数のソースを抽出（def dashboard から次の @router まで）"""
    src = _routes_src()
    start = src.find("async def dashboard(request: Request):")
    if start == -1:
        return src
    # 次の @router または # == まで
    next_route = src.find("\n@router", start + 1)
    return src[start:next_route] if next_route != -1 else src[start:]


class TestDashboardRoute:
    def test_route_passes_geo_latest(self):
        """dashboard ルートが geo_latest をテンプレートに渡す"""
        assert "geo_latest" in _dashboard_src()

    def test_route_passes_geo_risk_global(self):
        """dashboard ルートが geo_risk_global をテンプレートに渡す"""
        assert "geo_risk_global" in _dashboard_src()

    def test_route_passes_geo_labels(self):
        """dashboard ルートが geo_labels をテンプレートに渡す"""
        assert "geo_labels" in _dashboard_src()

    def test_route_passes_geo_colors(self):
        """dashboard ルートが geo_colors をテンプレートに渡す"""
        assert "geo_colors" in _dashboard_src()

    def test_route_geo_default_neutral(self):
        """geo フェッチ失敗時のデフォルトが neutral"""
        assert '"neutral"' in _dashboard_src()

    def test_route_geo_exception_safe(self):
        """geo フェッチ失敗時は例外を握りつぶす（except ブロックがある）"""
        assert "except Exception" in _dashboard_src()

    def test_phase73_comment(self):
        """Phase 73 のコメントが含まれる"""
        assert "Phase 73" in _dashboard_src()
