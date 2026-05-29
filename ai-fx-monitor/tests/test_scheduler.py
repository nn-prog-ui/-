"""定期スキャンスケジューラーのテスト（Phase 16）

外部API・メール送信・実DB接続はすべてモックで置き換える。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import app.services.scheduler as scheduler_module
from app.services.scheduler import start_scheduler, stop_scheduler


# ---------------------------------------------------------------------------
# 各テストの前後でグローバルな _scheduler をリセットする
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_scheduler():
    """各テスト前後でシングルトン _scheduler を初期化する。"""
    # テスト前にリセット
    scheduler_module._scheduler = None
    yield
    # テスト後: 起動中なら停止してリセット
    if scheduler_module._scheduler is not None:
        try:
            scheduler_module._scheduler.shutdown(wait=False)
        except Exception:
            pass
        scheduler_module._scheduler = None


# ---------------------------------------------------------------------------
# start_scheduler のテスト
# ---------------------------------------------------------------------------

class TestStartScheduler:
    def test_does_nothing_when_scan_disabled(self, monkeypatch):
        """SCAN_ENABLED=false のときスケジューラーを起動しない。"""
        monkeypatch.setenv("SCAN_ENABLED", "false")

        start_scheduler()

        assert scheduler_module._scheduler is None

    def test_starts_scheduler_when_scan_enabled(self, monkeypatch):
        """SCAN_ENABLED=true のときスケジューラーが起動する。"""
        monkeypatch.setenv("SCAN_ENABLED", "true")
        monkeypatch.setenv("SCAN_INTERVAL_MINUTES", "60")

        start_scheduler()

        assert scheduler_module._scheduler is not None
        assert scheduler_module._scheduler.running is True

    def test_default_scan_enabled_is_true(self, monkeypatch):
        """SCAN_ENABLED が未設定のときデフォルトで起動する。"""
        monkeypatch.delenv("SCAN_ENABLED", raising=False)
        monkeypatch.setenv("SCAN_INTERVAL_MINUTES", "60")

        start_scheduler()

        assert scheduler_module._scheduler is not None
        assert scheduler_module._scheduler.running is True

    def test_does_not_restart_already_running_scheduler(self, monkeypatch):
        """すでに起動済みのスケジューラーを二重起動しない。"""
        monkeypatch.setenv("SCAN_ENABLED", "true")
        monkeypatch.setenv("SCAN_INTERVAL_MINUTES", "60")

        start_scheduler()
        first_scheduler = scheduler_module._scheduler

        # 2回目の呼び出し
        start_scheduler()

        # 同じインスタンスのまま（再生成されていない）
        assert scheduler_module._scheduler is first_scheduler

    def test_job_is_registered(self, monkeypatch):
        """スキャンジョブが登録されていることを確認する。"""
        monkeypatch.setenv("SCAN_ENABLED", "true")
        monkeypatch.setenv("SCAN_INTERVAL_MINUTES", "30")

        start_scheduler()

        jobs = scheduler_module._scheduler.get_jobs()
        job_ids = {j.id for j in jobs}
        # fx_scan / news_collection / weekly_report_auto の3ジョブが登録される
        assert len(jobs) == 3
        assert "fx_scan" in job_ids
        assert "news_collection" in job_ids
        assert "weekly_report_auto" in job_ids


# ---------------------------------------------------------------------------
# stop_scheduler のテスト
# ---------------------------------------------------------------------------

class TestStopScheduler:
    def test_idempotent_when_not_started(self):
        """スケジューラー未起動でも stop_scheduler() がエラーにならない。"""
        assert scheduler_module._scheduler is None
        stop_scheduler()  # エラーが起きなければOK
        assert scheduler_module._scheduler is None

    def test_stops_running_scheduler(self, monkeypatch):
        """起動中のスケジューラーを正常停止できる。"""
        monkeypatch.setenv("SCAN_ENABLED", "true")
        monkeypatch.setenv("SCAN_INTERVAL_MINUTES", "60")

        start_scheduler()
        assert scheduler_module._scheduler is not None

        stop_scheduler()

        assert scheduler_module._scheduler is None

    def test_double_stop_does_not_raise(self, monkeypatch):
        """二重停止（冪等）でエラーにならない。"""
        monkeypatch.setenv("SCAN_ENABLED", "true")
        monkeypatch.setenv("SCAN_INTERVAL_MINUTES", "60")

        start_scheduler()
        stop_scheduler()
        stop_scheduler()  # 2回目もエラーにならない

        assert scheduler_module._scheduler is None


# ---------------------------------------------------------------------------
# _run_scan のテスト
# ---------------------------------------------------------------------------

class TestRunScan:
    def test_run_analysis_called_for_each_symbol(self, monkeypatch):
        """スキャン実行時に各通貨ペアで run_analysis が呼ばれる。"""
        symbols = ["USD/JPY", "EUR/USD"]
        monkeypatch.setattr("app.config.SUPPORTED_SYMBOLS", symbols)

        mock_result = MagicMock()
        mock_result.signal = "SKIP"
        mock_result.current_price = 150.0
        mock_result.symbol = "USD/JPY"

        with (
            patch("app.services.market_analyzer.run_analysis", return_value=mock_result) as mock_analyze,
            patch("app.services.notification.notify_analysis_result"),
            patch("app.database.repository.check_and_close_open_trades", return_value=[]),
        ):
            scheduler_module._run_scan()

        assert mock_analyze.call_count == len(symbols)
        called_symbols = [c.kwargs.get("symbol") for c in mock_analyze.call_args_list]
        assert set(called_symbols) == set(symbols)

    def test_other_symbols_continue_when_one_fails(self, monkeypatch):
        """1ペアのスキャンでエラーが起きても、他ペアのスキャンが継続される。"""
        symbols = ["USD/JPY", "EUR/USD", "GBP/USD"]
        monkeypatch.setattr("app.config.SUPPORTED_SYMBOLS", symbols)

        call_log: list[str] = []

        def fake_run_analysis(symbol: str):
            call_log.append(symbol)
            if symbol == "EUR/USD":
                raise RuntimeError("テスト用の強制エラー")
            mock_result = MagicMock()
            mock_result.signal = "SKIP"
            mock_result.current_price = 150.0
            mock_result.symbol = symbol
            return mock_result

        with (
            patch("app.services.market_analyzer.run_analysis", side_effect=fake_run_analysis),
            patch("app.services.notification.notify_analysis_result"),
            patch("app.database.repository.check_and_close_open_trades", return_value=[]),
        ):
            # 例外を上位に伝播させない（_run_scan 内で catch される）
            scheduler_module._run_scan()

        # 3ペアすべてで run_analysis が呼ばれていること
        assert set(call_log) == set(symbols)

    def test_notify_called_for_each_symbol(self, monkeypatch):
        """各ペアの分析後に notify_analysis_result が呼ばれる。"""
        symbols = ["USD/JPY", "EUR/USD"]
        monkeypatch.setattr("app.config.SUPPORTED_SYMBOLS", symbols)

        mock_result = MagicMock()
        mock_result.signal = "BUY"
        mock_result.current_price = 150.0
        mock_result.symbol = "USD/JPY"

        with (
            patch("app.services.market_analyzer.run_analysis", return_value=mock_result),
            patch("app.services.notification.notify_analysis_result") as mock_notify,
            patch("app.database.repository.check_and_close_open_trades", return_value=[]),
        ):
            scheduler_module._run_scan()

        assert mock_notify.call_count == len(symbols)

    def test_check_and_close_called_when_price_available(self, monkeypatch):
        """current_price がある場合に check_and_close_open_trades が呼ばれる。"""
        symbols = ["USD/JPY"]
        monkeypatch.setattr("app.config.SUPPORTED_SYMBOLS", symbols)

        mock_result = MagicMock()
        mock_result.signal = "SKIP"
        mock_result.current_price = 150.123
        mock_result.symbol = "USD/JPY"

        with (
            patch("app.services.market_analyzer.run_analysis", return_value=mock_result),
            patch("app.services.notification.notify_analysis_result"),
            patch("app.database.repository.check_and_close_open_trades", return_value=[]) as mock_close,
        ):
            scheduler_module._run_scan()

        mock_close.assert_called_once_with(150.123, "USD/JPY")

    def test_check_and_close_skipped_when_no_price(self, monkeypatch):
        """current_price が None の場合に check_and_close_open_trades が呼ばれない。"""
        symbols = ["USD/JPY"]
        monkeypatch.setattr("app.config.SUPPORTED_SYMBOLS", symbols)

        mock_result = MagicMock()
        mock_result.signal = "SKIP"
        mock_result.current_price = None
        mock_result.symbol = "USD/JPY"

        with (
            patch("app.services.market_analyzer.run_analysis", return_value=mock_result),
            patch("app.services.notification.notify_analysis_result"),
            patch("app.database.repository.check_and_close_open_trades") as mock_close,
        ):
            scheduler_module._run_scan()

        mock_close.assert_not_called()
