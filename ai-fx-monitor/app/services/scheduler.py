"""定期スキャンスケジューラー（Phase 16）

APScheduler の BackgroundScheduler を使って、設定した間隔で全通貨ペアの
市場分析・通知・SL/TP確認を自動実行する。

環境変数:
    SCAN_ENABLED          : "true"（デフォルト）でスケジューラーを有効化
    SCAN_INTERVAL_MINUTES : スキャン間隔（分、デフォルト: 60）

重要な制約:
    - スキャン結果は分析・通知・SL/TP確認のみ。自動注文は絶対に行わない
    - 1ペアのエラーで他ペアのスキャンが止まらないようにエラーを必ずcatch
    - SCAN_ENABLED=false で完全に無効化できる（オプション設計）
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# シングルトン管理
_scheduler = None


def _get_scan_enabled() -> bool:
    """SCAN_ENABLED 環境変数を読み取る（デフォルト: true）。"""
    return os.getenv("SCAN_ENABLED", "true").lower() == "true"


def _get_scan_interval_minutes() -> int:
    """SCAN_INTERVAL_MINUTES 環境変数を読み取る（デフォルト: 60）。"""
    try:
        return int(os.getenv("SCAN_INTERVAL_MINUTES", "60"))
    except ValueError:
        logger.warning("SCAN_INTERVAL_MINUTES の値が不正です。デフォルト値 60 を使用します。")
        return 60


def _run_scan() -> None:
    """全サポート通貨ペアを順にスキャンする。

    各ペアで分析→通知→SL/TP確認を実行する。
    1ペアのエラーは必ずcatchしてログに記録し、残りのペアの処理を継続する。
    """
    from app.config import SUPPORTED_SYMBOLS
    from app.services.market_analyzer import run_analysis
    from app.services.notification import notify_analysis_result
    from app.database.repository import check_and_close_open_trades

    logger.info("定期スキャン開始: 対象=%s", SUPPORTED_SYMBOLS)

    for symbol in SUPPORTED_SYMBOLS:
        try:
            logger.debug("スキャン中: %s", symbol)

            # 1. 分析実行
            result = run_analysis(symbol=symbol)

            # 2. 通知
            notify_analysis_result(result)

            # 3. SL/TP確認（current_priceがNoneの場合はスキップ）
            if result.current_price is not None:
                closed = check_and_close_open_trades(result.current_price, result.symbol)
                if closed:
                    logger.info(
                        "SL/TP発動でクローズ: %s %d件", symbol, len(closed)
                    )
            else:
                logger.debug("current_price が取得できないため SL/TP確認をスキップ: %s", symbol)

            logger.debug("スキャン完了: %s signal=%s", symbol, result.signal)

        except Exception as exc:
            # 1ペアのエラーで他ペアのスキャンを止めない
            logger.error("スキャンエラー（%s）: %s", symbol, exc, exc_info=True)

    logger.info("定期スキャン完了")


def start_scheduler() -> None:
    """バックグラウンドスケジューラーを起動する。

    SCAN_ENABLED=false の場合は何もしない。
    すでに起動済みの場合は再起動しない（冪等）。
    """
    global _scheduler

    if not _get_scan_enabled():
        logger.info("SCAN_ENABLED=false のためスケジューラーを起動しません。")
        return

    if _scheduler is not None and _scheduler.running:
        logger.info("スケジューラーはすでに起動済みです。")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        interval_minutes = _get_scan_interval_minutes()
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            _run_scan,
            trigger="interval",
            minutes=interval_minutes,
            id="fx_scan",
            name="FX定期スキャン",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info(
            "スケジューラー起動: スキャン間隔=%d分", interval_minutes
        )
    except Exception as exc:
        logger.error("スケジューラー起動エラー: %s", exc, exc_info=True)


def stop_scheduler() -> None:
    """バックグラウンドスケジューラーを停止する。

    未起動・停止済みの場合は何もしない（冪等）。
    """
    global _scheduler

    if _scheduler is None:
        logger.debug("スケジューラーは起動していません（停止不要）。")
        return

    if not _scheduler.running:
        logger.debug("スケジューラーはすでに停止済みです。")
        _scheduler = None
        return

    try:
        _scheduler.shutdown(wait=False)
        logger.info("スケジューラーを停止しました。")
    except Exception as exc:
        logger.error("スケジューラー停止エラー: %s", exc, exc_info=True)
    finally:
        _scheduler = None
