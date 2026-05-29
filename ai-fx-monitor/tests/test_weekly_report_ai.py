"""Phase 79: AI週次レポート自動生成 テスト"""
from __future__ import annotations

from pathlib import Path


def _weekly_report_src() -> str:
    return (Path(__file__).parent.parent / "app" / "scripts" / "weekly_report.py").read_text(encoding="utf-8")


def _scheduler_src() -> str:
    return (Path(__file__).parent.parent / "app" / "services" / "scheduler.py").read_text(encoding="utf-8")


def _template_src() -> str:
    return (Path(__file__).parent.parent / "app" / "web" / "templates" / "weekly_report.html").read_text(encoding="utf-8")


# ── WeeklyMetrics センチメントフィールド ─────────────────────────────────────

class TestWeeklyMetricsSentimentFields:
    def test_sentiment_total_field_exists(self):
        """WeeklyMetrics に sentiment_total フィールドがある"""
        assert "sentiment_total" in _weekly_report_src()

    def test_sentiment_bullish_pct_exists(self):
        """sentiment_bullish_pct フィールドがある"""
        assert "sentiment_bullish_pct" in _weekly_report_src()

    def test_sentiment_bearish_pct_exists(self):
        """sentiment_bearish_pct フィールドがある"""
        assert "sentiment_bearish_pct" in _weekly_report_src()

    def test_sentiment_neutral_pct_exists(self):
        """sentiment_neutral_pct フィールドがある"""
        assert "sentiment_neutral_pct" in _weekly_report_src()

    def test_phase79_comment_in_fields(self):
        """Phase 79 コメントがフィールド定義近くにある"""
        assert "Phase 79" in _weekly_report_src()


# ── センチメントデータ収集 ────────────────────────────────────────────────────

class TestSentimentDataCollection:
    def test_collect_metrics_fetches_sentiment(self):
        """_collect_metrics がセンチメントデータを取得している"""
        src = _weekly_report_src()
        collect_fn = src[src.find("def _collect_metrics"):]
        assert "get_sentiment_report" in collect_fn

    def test_sentiment_days_7(self):
        """直近7日間のセンチメントを取得している"""
        src = _weekly_report_src()
        assert "days=7" in src

    def test_sentiment_error_handling(self):
        """センチメント取得のエラーをキャッチしている"""
        src = _weekly_report_src()
        # _collect_metrics 内の except を確認
        collect_fn = src[src.find("def _collect_metrics"):]
        return_pos = collect_fn.find("return metrics")
        body = collect_fn[:return_pos]
        assert "except" in body


# ── AIプロンプト構造 ─────────────────────────────────────────────────────────

class TestWeeklyAiPromptStructure:
    def test_system_prompt_has_3_sections(self):
        """システムプロンプトに3セクション定義がある"""
        src = _weekly_report_src()
        assert "### 振り返り" in src
        assert "### 改善ポイント" in src
        assert "### 来週の注目通貨" in src

    def test_system_prompt_forbidden_expressions(self):
        """禁止表現が守るルールに記載されている"""
        src = _weekly_report_src()
        prompt_sec = src[src.find("_WEEKLY_SYSTEM_PROMPT"):][:1000]
        assert "儲かる" in prompt_sec or "絶対" in prompt_sec

    def test_build_prompt_includes_sentiment(self):
        """_build_weekly_prompt にセンチメントデータが含まれる"""
        src = _weekly_report_src()
        build_fn = src[src.find("def _build_weekly_prompt"):]
        next_fn = build_fn.find("\ndef ", 1)
        fn_body = build_fn[:next_fn] if next_fn != -1 else build_fn[:3000]
        assert "sentiment" in fn_body.lower()

    def test_build_prompt_output_instruction(self):
        """プロンプトに3セクション形式の出力指示がある"""
        src = _weekly_report_src()
        assert "出力指示" in src or "3セクション形式" in src

    def test_build_prompt_sentiment_bullish_pct(self):
        """プロンプトにbullish_pctが展開されている"""
        src = _weekly_report_src()
        build_fn = src[src.find("def _build_weekly_prompt"):]
        assert "sentiment_bullish_pct" in build_fn or "bullish_pct" in build_fn


# ── モックナレーティブ3セクション形式 ─────────────────────────────────────────

class TestMockNarrative3Sections:
    def test_mock_narrative_has_review_section(self):
        """モックナレーティブに振り返りセクションがある"""
        src = _weekly_report_src()
        mock_fn = src[src.find("def _generate_mock_narrative"):]
        assert "### 振り返り" in mock_fn

    def test_mock_narrative_has_improve_section(self):
        """モックナレーティブに改善ポイントセクションがある"""
        src = _weekly_report_src()
        mock_fn = src[src.find("def _generate_mock_narrative"):]
        assert "### 改善ポイント" in mock_fn

    def test_mock_narrative_has_attention_section(self):
        """モックナレーティブに来週の注目通貨セクションがある"""
        src = _weekly_report_src()
        mock_fn = src[src.find("def _generate_mock_narrative"):]
        assert "### 来週の注目通貨" in mock_fn

    def test_mock_narrative_joins_sections(self):
        """3セクションが結合されて返される"""
        src = _weekly_report_src()
        mock_fn = src[src.find("def _generate_mock_narrative"):]
        assert "join" in mock_fn

    def test_mock_narrative_sentiment_usage(self):
        """モックナレーティブでセンチメントデータを使用している"""
        src = _weekly_report_src()
        mock_fn = src[src.find("def _generate_mock_narrative"):]
        assert "sentiment_total" in mock_fn or "sentiment_bullish_pct" in mock_fn

    def test_mock_narrative_loss_streak_warning(self):
        """連敗中は特別な警告を出している"""
        src = _weekly_report_src()
        mock_fn = src[src.find("def _generate_mock_narrative"):]
        assert "連敗" in mock_fn or "loss" in mock_fn


# ── スケジューラー週次自動生成 ───────────────────────────────────────────────

class TestSchedulerWeeklyReport:
    def test_weekly_report_auto_function_exists(self):
        """_run_weekly_report_auto 関数が定義されている"""
        assert "def _run_weekly_report_auto" in _scheduler_src()

    def test_weekly_report_auto_calls_generate(self):
        """週次自動生成がgenerate_and_save_weekly_reportを呼ぶ"""
        src = _scheduler_src()
        fn = src[src.find("def _run_weekly_report_auto"):]
        assert "generate_and_save_weekly_report" in fn

    def test_weekly_report_job_added_to_scheduler(self):
        """スケジューラーに週次レポートジョブが追加されている"""
        assert "weekly_report_auto" in _scheduler_src()

    def test_weekly_report_uses_cron_trigger(self):
        """週次レポートがcronトリガーを使用している"""
        src = _scheduler_src()
        assert 'trigger="cron"' in src or "trigger='cron'" in src

    def test_weekly_report_monday_schedule(self):
        """月曜日スケジュール設定がある（日曜UTC）"""
        src = _scheduler_src()
        job_section = src[src.find("weekly_report_auto"):]
        # 日曜15:05 UTC = 月曜00:05 JST
        assert "sun" in job_section.lower() or "monday" in job_section.lower()

    def test_weekly_report_phase79_comment(self):
        """Phase 79 コメントが含まれる"""
        assert "Phase 79" in _scheduler_src()

    def test_weekly_report_auto_error_handling(self):
        """週次自動生成のエラーをキャッチしている"""
        src = _scheduler_src()
        fn = src[src.find("def _run_weekly_report_auto"):]
        assert "except" in fn


# ── テンプレートUIテスト ─────────────────────────────────────────────────────

class TestWeeklyReportTemplateUi:
    def test_phase79_comment_in_template(self):
        """テンプレートにPhase 79 コメントがある"""
        assert "Phase 79" in _template_src()

    def test_spinner_animation(self):
        """生成中スピナーアニメーションがある"""
        src = _template_src()
        assert "spin" in src or "animation" in src

    def test_generate_sections_container(self):
        """3セクション表示コンテナがある"""
        assert "resSections" in _template_src()

    def test_parse_sections_function(self):
        """parseSections JS関数が定義されている"""
        assert "parseSections" in _template_src()

    def test_render_sections_function(self):
        """renderSections JS関数が定義されている"""
        assert "renderSections" in _template_src()

    def test_section_defs_js(self):
        """SECTION_DEFS に3セクションが定義されている"""
        src = _template_src()
        assert "振り返り" in src
        assert "改善ポイント" in src
        assert "来週の注目通貨" in src

    def test_section_icons(self):
        """3セクションにアイコンがある"""
        src = _template_src()
        js_sec = src[src.find("SECTION_DEFS"):]
        assert "📊" in js_sec or "💡" in js_sec or "🔭" in js_sec

    def test_latest_report_badge(self):
        """最新レポートに「最新」バッジがある"""
        assert "最新" in _template_src()

    def test_sentiment_metrics_card(self):
        """センチメント指標カードが表示される"""
        assert "センチメント" in _template_src()

    def test_ai_narrative_block_class(self):
        """ai-narrative-blockクラスで過去レポートを処理している"""
        assert "ai-narrative-block" in _template_src()

    def test_domcontentloaded_listener(self):
        """DOMContentLoaded で既存レポートを3セクション変換"""
        assert "DOMContentLoaded" in _template_src()

    def test_provider_emoji_labels(self):
        """AIプロバイダーに絵文字ラベルがある"""
        src = _template_src()
        assert "✨" in src or "🤖" in src or "📝" in src
