"""FastAPIルーティング"""
from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.database.repository import (
    ALERT_CONDITION_TYPES,
    HUMAN_ACTION_BUY,
    HUMAN_ACTION_SELL,
    HUMAN_ACTION_SKIP,
    check_and_close_open_trades,
    close_demo_order,
    create_alert,
    delete_alert,
    get_alerts,
    get_all_settings,
    get_demo_orders_for_export,
    get_history_for_export,
    get_journal_for_export,
    get_journal_count,
    get_journal_entries,
    get_journal_entry,
    JOURNAL_ENTRY_TYPES,
    JOURNAL_EMOTION_LABELS,
    upsert_journal,
    get_approval_by_id,
    get_chart_data,
    get_demo_order_by_id,
    get_demo_orders,
    get_demo_performance_stats,
    get_history,
    get_history_count,
    get_open_trades,
    get_performance_report,
    get_performance_stats,
    get_setting,
    save_approval,
    save_backtest_results,
    save_demo_order,
    save_settings,
    toggle_alert,
    IMPORTANCE_LEVELS,
    IMPORTANCE_LABELS,
    create_economic_event,
    delete_economic_event,
    get_economic_events,
    count_economic_events,
    get_upcoming_warning_events,
    has_upcoming_warning,
    save_push_subscription,
    delete_push_subscription,
    get_push_subscriptions,
    count_push_subscriptions,
    get_or_create_vapid_keys,
)
from app.services.demo_order import DemoOrderError, DemoOrderAdapter, is_demo_order_available
from app.config import DATA_DIR, DEFAULT_SYMBOL, SUPPORTED_SYMBOLS, SYMBOL_CSV_MAP
from app.data.loader import load_or_generate
from app.data.resampler import to_4h, to_daily
from app.indicators.bollinger_bands import calculate_bollinger_bands
from app.indicators.moving_average import calculate_ma
from app.scripts.backtest import run_backtest
from app.scripts.walk_forward import (
    DEFAULT_IS_RATIO,
    DEFAULT_N_WINDOWS,
    DEFAULT_WINDOW_BARS,
    DEFAULT_STEP,
    DEFAULT_FUTURE_BARS,
    run_walk_forward,
)
from app.scripts.monte_carlo import (
    DEFAULT_N_SIMULATIONS,
    DEFAULT_RUIN_THRESHOLD,
    get_pnl_pips_from_db,
    run_monte_carlo,
)
from app.scripts.sensitivity import (
    SENSITIVITY_PARAMS,
    DEFAULT_STEPS,
    run_sensitivity,
)
from app.scripts.heatmap_calendar import (
    VALID_METRICS as HEATMAP_VALID_METRICS,
    WEEKDAY_LABELS,
    build_heatmap,
    get_heatmap_rows,
)
from app.scripts.streak import (
    StreakStats,
    get_streak_stats,
    get_streak_stats_by_symbol,
)
from app.scripts.drawdown import (
    DrawdownStats,
    equity_curve_to_chart_data,
    get_drawdown_by_symbol,
    get_drawdown_stats,
)
from app.scripts.signal_quality import (
    QUALITY_CSS,
    QUALITY_DESCRIPTIONS,
    get_all_pattern_stats,
    get_signal_quality,
)
from app.scripts.optimizer import VALID_METRICS, optimize
from app.scripts.multi_symbol import get_multi_symbol_report
from app.scripts.pattern_recognition import get_pattern_report
from app.scripts.r_multiple import get_r_multiple_report
from app.scripts.position_sizing import (
    SizingInput, calculate_sizing, get_historical_stats,
)
from app.scripts.period_stats import get_period_report
from app.scripts.scorecard import GRADE_COLORS, get_scorecard
from app.scripts.goal_tracker import (
    create_goal, delete_goal, get_goals,
    current_month_label, current_week_label,
    VALID_PERIOD_TYPES,
)
from app.scripts.rolling_stats import (
    DEFAULT_WINDOW as ROLLING_DEFAULT_WINDOW,
    VALID_WINDOWS as ROLLING_VALID_WINDOWS,
    get_rolling_report,
)
from app.services.correlation import LOOKBACK_OPTIONS, calculate_correlation_matrix, correlation_label
from app.services.market_analyzer import AnalysisResult, run_analysis
from app.services.notification import notify_analysis_result

logger = logging.getLogger(__name__)
router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# 分析結果をリクエスト間で一時保持（本番ではRedisや引数渡しに変更）
_last_result: AnalysisResult | None = None
# 通貨ペアごとの最新シグナルを保持（Phase 29: ブラウザ通知用）
_signal_cache: dict[str, dict] = {}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, symbol: str = DEFAULT_SYMBOL):
    global _last_result, _signal_cache
    if symbol not in SUPPORTED_SYMBOLS:
        symbol = DEFAULT_SYMBOL
    try:
        result = run_analysis(symbol=symbol)
        _last_result = result
        _signal_cache[symbol] = {
            "signal": result.signal,
            "score": result.score,
            "current_price": result.current_price,
            "analyzed_at": result.analyzed_at.isoformat(),
        }
        try:
            notify_analysis_result(result)
        except Exception as exc:
            logger.warning("通知エラー（分析は継続）: %s", exc)
        try:
            if result.current_price:
                check_and_close_open_trades(result.current_price, result.symbol)
        except Exception as exc:
            logger.warning("オープン取引チェックエラー（分析は継続）: %s", exc)
        # Phase 41: BUY/SELL シグナル時に Web Push 送信
        if result.signal in ("BUY", "SELL") and count_push_subscriptions() > 0:
            try:
                import asyncio
                from app.services.push_sender import send_push_to_all
                asyncio.create_task(send_push_to_all())
            except Exception as exc:
                logger.warning("Web Push 送信エラー（分析は継続）: %s", exc)
    except Exception as exc:
        logger.error("分析エラー: %s", exc)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": str(exc),
                "result": None,
                "supported_symbols": SUPPORTED_SYMBOLS,
            },
        )

    # Phase 39: 直近の経済指標警戒情報を渡す
    try:
        warning_events = get_upcoming_warning_events()
    except Exception:
        warning_events = []

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "result": result,
            "error": None,
            "supported_symbols": SUPPORTED_SYMBOLS,
            "warning_events": warning_events,
        },
    )


@router.post("/approve", response_class=HTMLResponse)
async def approve(
    request: Request,
    action: str = Form(...),
    notes: str = Form(""),
):
    """承認ボタン処理。注文は発生しない。SQLiteへの履歴保存のみ。"""
    global _last_result

    if action not in {HUMAN_ACTION_BUY, HUMAN_ACTION_SELL, HUMAN_ACTION_SKIP}:
        raise HTTPException(status_code=400, detail="無効なアクションです")

    if _last_result is None:
        return RedirectResponse(url="/", status_code=303)

    # 安全チェック：買い承認はBUYシグナル時のみ、売り承認はSELLシグナル時のみ
    if action == HUMAN_ACTION_BUY and not _last_result.can_approve_buy:
        raise HTTPException(
            status_code=400,
            detail="現在の判定では買い承認できません。損切り・利確・RRを確認してください。",
        )
    if action == HUMAN_ACTION_SELL and not _last_result.can_approve_sell:
        raise HTTPException(
            status_code=400,
            detail="現在の判定では売り承認できません。損切り・利確・RRを確認してください。",
        )

    try:
        record_id = save_approval(_last_result, action, notes)
        logger.info("承認履歴保存: id=%d action=%s", record_id, action)
    except Exception as exc:
        logger.error("履歴保存エラー: %s", exc)
        raise HTTPException(status_code=500, detail="履歴保存に失敗しました")

    return RedirectResponse(url="/history", status_code=303)


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request, page: int = 1, per_page: int = 20):
    offset = (page - 1) * per_page
    records = get_history(limit=per_page, offset=offset)
    total = get_history_count()
    total_pages = (total + per_page - 1) // per_page

    # skip_reasonsをJSON文字列からリストに変換
    for r in records:
        try:
            r["skip_reasons_list"] = json.loads(r.get("skip_reasons") or "[]")
        except (json.JSONDecodeError, TypeError):
            r["skip_reasons_list"] = []
        r["signal_label"] = {"BUY": "買い候補", "SELL": "売り候補", "SKIP": "見送り"}.get(
            r.get("signal", ""), "不明"
        )
        r["action_label"] = {
            "buy_approved": "買い承認",
            "sell_approved": "売り承認",
            "skipped": "見送り",
        }.get(r.get("human_action", ""), "不明")
        # Phase 34: ジャーナルを各レコードに付与
        r["journal"] = get_journal_entry(r["id"])

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "records": records,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "entry_types": JOURNAL_ENTRY_TYPES,
            "emotion_labels": JOURNAL_EMOTION_LABELS,
        },
    )


@router.get("/performance", response_class=HTMLResponse)
async def performance(request: Request):
    """パフォーマンス統計ページ。"""
    stats = get_performance_stats()
    demo_stats = get_demo_performance_stats()
    open_trades = get_open_trades()

    # open_tradesにラベルを付与（historyルートと同様）
    for r in open_trades:
        try:
            r["skip_reasons_list"] = json.loads(r.get("skip_reasons") or "[]")
        except (json.JSONDecodeError, TypeError):
            r["skip_reasons_list"] = []
        r["signal_label"] = {"BUY": "買い候補", "SELL": "売り候補", "SKIP": "見送り"}.get(
            r.get("signal", ""), "不明"
        )
        r["action_label"] = {
            "buy_approved": "買い承認",
            "sell_approved": "売り承認",
            "skipped": "見送り",
        }.get(r.get("human_action", ""), "不明")

    return templates.TemplateResponse(
        "performance.html",
        {
            "request": request,
            "stats": stats,
            "demo_stats": demo_stats,
            "open_trades": open_trades,
        },
    )


@router.get("/api/analysis")
async def api_analysis():
    """分析結果をJSON APIで返す（将来の拡張用）。"""
    try:
        result = run_analysis()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "symbol": result.symbol,
        "analyzed_at": result.analyzed_at.isoformat(),
        "current_price": result.current_price,
        "signal": result.signal,
        "signal_label": result.signal_label,
        "score": result.score,
        "daily_trend": result.daily_trend,
        "h4_trend": result.h4_trend,
        "h1_status": result.h1_status,
        "rsi": result.rsi,
        "atr_value": result.atr_value,
        "atr_status": result.atr_status,
        "recent_high": result.recent_high,
        "recent_low": result.recent_low,
        "entry_price": result.entry_price,
        "stop_loss": result.stop_loss,
        "take_profit": result.take_profit,
        "risk_reward": result.risk_reward,
        "economic_warning": result.economic_warning,
        "ai_comment": result.ai_comment,
        "is_dummy_data": result.is_dummy_data,
    }


# ============================================================
# Phase 12: デモ注文フロー（承認ボタンとは完全に独立）
# ============================================================

@router.get("/demo-trade/{record_id}", response_class=HTMLResponse)
async def demo_trade_confirm(request: Request, record_id: int):
    """デモ注文 Step 1: 承認済み取引の詳細と警告を表示する。"""
    record = get_approval_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="承認履歴が見つかりません")

    if record["human_action"] not in {HUMAN_ACTION_BUY, HUMAN_ACTION_SELL}:
        raise HTTPException(status_code=400, detail="買い/売り承認済みの取引のみデモ注文できます")

    demo_available = is_demo_order_available()

    return templates.TemplateResponse(
        "demo_trade.html",
        {
            "request": request,
            "record": record,
            "step": 1,
            "demo_available": demo_available,
            "error": None,
        },
    )


@router.post("/demo-trade/{record_id}", response_class=HTMLResponse)
async def demo_trade_execute(
    request: Request,
    record_id: int,
    step: int = Form(...),
    confirm1: str = Form(""),
    confirm2: str = Form(""),
    units: int = Form(1000),
    notes: str = Form(""),
):
    """デモ注文 Step 2 → 確認 / Step 3 → 実行。"""
    record = get_approval_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="承認履歴が見つかりません")

    if record["human_action"] not in {HUMAN_ACTION_BUY, HUMAN_ACTION_SELL}:
        raise HTTPException(status_code=400, detail="買い/売り承認済みの取引のみデモ注文できます")

    # Step 1 → Step 2: 第1確認チェックボックス
    if step == 1:
        if confirm1 != "yes":
            return templates.TemplateResponse(
                "demo_trade.html",
                {
                    "request": request,
                    "record": record,
                    "step": 1,
                    "demo_available": is_demo_order_available(),
                    "error": "確認チェックボックスにチェックを入れてください。",
                },
            )
        return templates.TemplateResponse(
            "demo_trade.html",
            {
                "request": request,
                "record": record,
                "step": 2,
                "units": units,
                "demo_available": is_demo_order_available(),
                "error": None,
            },
        )

    # Step 2 → 実行: 第2確認チェックボックス
    if step == 2:
        if confirm2 != "yes":
            return templates.TemplateResponse(
                "demo_trade.html",
                {
                    "request": request,
                    "record": record,
                    "step": 2,
                    "units": units,
                    "demo_available": is_demo_order_available(),
                    "error": "最終確認チェックボックスにチェックを入れてください。",
                },
            )

        if not is_demo_order_available():
            return templates.TemplateResponse(
                "demo_trade.html",
                {
                    "request": request,
                    "record": record,
                    "step": 2,
                    "units": units,
                    "demo_available": False,
                    "error": "デモ注文が利用できません。DATA_SOURCE=oanda と OANDA_API_KEY を設定してください。",
                },
            )

        direction = "BUY" if record["human_action"] == HUMAN_ACTION_BUY else "SELL"
        try:
            adapter = DemoOrderAdapter.from_env()
            order_result = adapter.place_market_order(
                symbol=record["symbol"],
                direction=direction,
                units=max(1, abs(units)),
                stop_loss=record.get("stop_loss"),
                take_profit=record.get("take_profit"),
            )
        except DemoOrderError as exc:
            return templates.TemplateResponse(
                "demo_trade.html",
                {
                    "request": request,
                    "record": record,
                    "step": 2,
                    "units": units,
                    "demo_available": True,
                    "error": f"注文エラー: {exc}",
                },
            )

        demo_id = save_demo_order(
            approval_id=record_id,
            symbol=record["symbol"],
            direction=direction,
            units=units,
            entry_price=record.get("entry_price"),
            stop_loss=record.get("stop_loss"),
            take_profit=record.get("take_profit"),
            oanda_trade_id=order_result.trade_id,
            oanda_order_id=order_result.order_id,
            filled_price=order_result.filled_price,
            notes=notes,
        )
        logger.info("デモ注文保存: demo_id=%d trade_id=%s", demo_id, order_result.trade_id)

        return templates.TemplateResponse(
            "demo_trade.html",
            {
                "request": request,
                "record": record,
                "step": 3,
                "order_result": order_result,
                "demo_id": demo_id,
                "error": None,
            },
        )

    raise HTTPException(status_code=400, detail="無効なステップです")


@router.get("/demo-orders", response_class=HTMLResponse)
async def demo_orders_list(request: Request):
    """デモ注文履歴一覧ページ。"""
    orders = get_demo_orders(limit=50)
    demo_stats = get_demo_performance_stats()
    return templates.TemplateResponse(
        "demo_trade.html",
        {
            "request": request,
            "step": "list",
            "orders": orders,
            "demo_stats": demo_stats,
            "error": None,
        },
    )


# ============================================================
# Phase 13: デモ注文の手動クローズ
# ============================================================

@router.post("/demo-close/{demo_id}", response_class=HTMLResponse)
async def demo_close_trade(
    request: Request,
    demo_id: int,
    confirm_close: str = Form(""),
):
    """デモ注文を手動でクローズし、損益を記録する。"""
    order = get_demo_order_by_id(demo_id)
    if not order:
        raise HTTPException(status_code=404, detail="デモ注文が見つかりません")

    if order["status"] != "open":
        return templates.TemplateResponse(
            "demo_trade.html",
            {
                "request": request,
                "step": "list",
                "orders": get_demo_orders(limit=50),
                "error": f"デモ注文 #{demo_id} はすでに決済済みです。",
            },
        )

    if confirm_close != "yes":
        return templates.TemplateResponse(
            "demo_trade.html",
            {
                "request": request,
                "step": "list",
                "orders": get_demo_orders(limit=50),
                "error": "決済確認にチェックを入れてください。",
            },
        )

    if not order.get("oanda_trade_id"):
        return templates.TemplateResponse(
            "demo_trade.html",
            {
                "request": request,
                "step": "list",
                "orders": get_demo_orders(limit=50),
                "error": "OANDA Trade IDがないため決済できません。",
            },
        )

    try:
        adapter = DemoOrderAdapter.from_env()
        result = adapter.close_trade(order["oanda_trade_id"])
    except DemoOrderError as exc:
        return templates.TemplateResponse(
            "demo_trade.html",
            {
                "request": request,
                "step": "list",
                "orders": get_demo_orders(limit=50),
                "error": f"決済エラー: {exc}",
            },
        )

    exit_price = result.filled_price or 0.0
    filled_price = order.get("filled_price") or order.get("entry_price") or exit_price
    symbol = order.get("symbol", "")
    pip_size = 0.01 if "JPY" in symbol.upper() else 0.0001
    raw_pnl = (exit_price - filled_price) / pip_size
    pnl_pips = raw_pnl if order["direction"] == "BUY" else -raw_pnl

    close_demo_order(demo_id, exit_price, round(pnl_pips, 1))
    logger.info("デモ注文決済: demo_id=%d exit=%.3f pnl=%.1fpips", demo_id, exit_price, pnl_pips)

    return RedirectResponse(url="/demo-orders", status_code=303)


# ============================================================
# Phase 21: バックテスト可視化
# ============================================================

@router.get("/backtest", response_class=HTMLResponse)
async def backtest_page(
    request: Request,
    symbol: str = "",
    window: int = 500,
    step: int = 24,
    future: int = 100,
    save: bool = False,
):
    """バックテスト実行ページ。"""
    result = None
    error = None
    ran = False
    saved_count = None

    if symbol and symbol in SUPPORTED_SYMBOLS:
        ran = True
        try:
            result = run_backtest(symbol=symbol, window=window, step=step, future_bars=future)
        except Exception as exc:
            logger.error("バックテストエラー: %s", exc)
            error = str(exc)

    if ran and save and result:
        try:
            saved_count = save_backtest_results(result.trades, symbol)
            logger.info("バックテスト結果をDBに保存: %d件 [%s]", saved_count, symbol)
        except Exception as exc:
            logger.error("バックテスト結果の保存エラー: %s", exc)

    return templates.TemplateResponse(
        "backtest.html",
        {
            "request": request,
            "result": result,
            "error": error,
            "ran": ran,
            "saved_count": saved_count,
            "supported_symbols": SUPPORTED_SYMBOLS,
            "params": {"symbol": symbol, "window": window, "step": step, "future": future},
        },
    )


# ============================================================
# Phase 22: 設定画面
# ============================================================

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: bool = False):
    """設定画面。"""
    import os
    current = get_all_settings()
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": current,
            "saved": saved,
            "data_source": os.getenv("DATA_SOURCE", "csv"),
            "oanda_env": os.getenv("OANDA_ENVIRONMENT", "practice"),
            "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")),
            "oanda_key": bool(os.getenv("OANDA_API_KEY")),
            "email_set": bool(os.getenv("EMAIL_FROM")),
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_save(
    request: Request,
    scan_enabled: str = Form("false"),
    scan_interval_minutes: str = Form("60"),
    notify_on_buy: str = Form("false"),
    notify_on_sell: str = Form("false"),
    notify_on_skip: str = Form("false"),
    notify_min_score: str = Form("0"),
):
    """設定を保存する。"""
    try:
        interval = int(scan_interval_minutes)
        if interval < 1:
            interval = 1
        min_score = int(notify_min_score)
    except ValueError:
        interval = 60
        min_score = 0

    save_settings({
        "scan_enabled": scan_enabled,
        "scan_interval_minutes": str(interval),
        "notify_on_buy": notify_on_buy,
        "notify_on_sell": notify_on_sell,
        "notify_on_skip": notify_on_skip,
        "notify_min_score": str(min_score),
    })
    return RedirectResponse(url="/settings?saved=1", status_code=303)


# ============================================================
# Phase 23: 複数通貨ペアのダッシュボード
# ============================================================

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """全通貨ペアの現在判定をまとめたダッシュボード。"""
    analyses = []
    for sym in SUPPORTED_SYMBOLS:
        try:
            r = run_analysis(symbol=sym)
            analyses.append(r)
        except Exception as exc:
            logger.warning("ダッシュボード分析エラー [%s]: %s", sym, exc)

    # Phase 48: 連勝/連敗ストリーク統計
    try:
        streak_all = get_streak_stats(symbol=None)
        streak_by_sym = get_streak_stats_by_symbol()
    except Exception:
        streak_all = None
        streak_by_sym = []

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "analyses": analyses,
            "supported_symbols": SUPPORTED_SYMBOLS,
            "streak_all": streak_all,
            "streak_by_sym": streak_by_sym,
        },
    )


# ============================================================
# Phase 24: 判定精度レポート
# ============================================================

@router.get("/report", response_class=HTMLResponse)
async def report(request: Request):
    """判定精度レポートページ。"""
    data = get_performance_report()
    return templates.TemplateResponse(
        "report.html",
        {"request": request, "data": data},
    )


# ============================================================
# Phase 25: 設定JSON API（自動リフレッシュ用）
# ============================================================

@router.get("/api/settings")
async def api_settings():
    """現在のアプリ設定をJSONで返す（自動リフレッシュ間隔など）。"""
    return {
        "scan_interval_minutes": int(get_setting("scan_interval_minutes") or 60),
        "scan_enabled": get_setting("scan_enabled") == "true",
    }


# ============================================================
# Phase 26: チャートデータAPI
# ============================================================

@router.get("/api/chart-data")
async def api_chart_data(symbol: str = "", limit: int = 60):
    """クローズ済み取引の時系列データをJSONで返す（チャート描画用）。"""
    sym = symbol if symbol else None
    trades = get_chart_data(symbol=sym, limit=limit)
    return {"trades": trades, "symbol": symbol or "全ペア", "count": len(trades)}


@router.get("/api/chart-stats")
async def api_chart_stats():
    """チャートページ用の集計データをJSONで返す。

    レスポンス:
      - monthly: 月次 wins/losses/total_pips
      - by_signal: BUY/SELL別勝率
      - pips_distribution: pipsのヒストグラムバケット
    """
    report = get_performance_report()
    monthly = [
        {
            "month": m["month"],
            "wins": m["wins"],
            "losses": m["losses"],
            "total_pips": round(m.get("total_pips") or 0.0, 1),
            "win_rate": round(m["wins"] / (m["wins"] + m["losses"]) * 100, 1)
            if (m["wins"] + m["losses"]) > 0 else None,
        }
        for m in report.get("monthly", [])
    ]
    by_signal = [
        {
            "signal": r["signal"],
            "wins": r["wins"],
            "losses": r["losses"],
            "total_pips": round(r.get("total_pips") or 0.0, 1),
            "avg_pips": round(r.get("avg_pips") or 0.0, 1),
            "win_rate": round(r["wins"] / (r["wins"] + r["losses"]) * 100, 1)
            if (r["wins"] + r["losses"]) > 0 else None,
        }
        for r in report.get("by_signal", [])
    ]
    return {"monthly": monthly, "by_signal": by_signal}


@router.get("/charts", response_class=HTMLResponse)
async def charts_page(request: Request, symbol: str = "", limit: int = 100):
    """チャートダッシュボードページ。"""
    return templates.TemplateResponse("charts.html", {
        "request": request,
        "supported_symbols": SUPPORTED_SYMBOLS,
        "selected_symbol": symbol,
        "limit": limit,
    })


# ============================================================
# Phase 28: ローソク足チャートデータAPI
# ============================================================

_VALID_TF = {"1h", "4h", "1d"}


@router.get("/api/candles")
async def api_candles(symbol: str = DEFAULT_SYMBOL, limit: int = 60, tf: str = "1h"):
    """OHLCデータ＋MA20・MA50・BB をJSONで返す（Phase 31: 複数時間足対応）。

    tf: "1h"（デフォルト）| "4h" | "1d"
    """
    if symbol not in SUPPORTED_SYMBOLS:
        symbol = DEFAULT_SYMBOL
    if tf not in _VALID_TF:
        tf = "1h"

    csv_name = SYMBOL_CSV_MAP.get(symbol, "USDJPY_1h.csv")
    csv_path = DATA_DIR / csv_name
    df_1h, _ = load_or_generate(csv_path, symbol=symbol)
    if df_1h.empty:
        return {"candles": [], "symbol": symbol, "tf": tf, "count": 0}

    # 時間足変換（1h はそのまま）
    if tf == "4h":
        df = to_4h(df_1h)
    elif tf == "1d":
        df = to_daily(df_1h)
    else:
        df = df_1h

    if df.empty:
        return {"candles": [], "symbol": symbol, "tf": tf, "count": 0}

    # インジケーターはフル系列で計算してから最後の limit 本を切り出す
    ma20_series = calculate_ma(df["close"], 20)
    ma50_series = calculate_ma(df["close"], 50)
    bb_df = calculate_bollinger_bands(df, period=20)

    df = df.tail(limit).copy()
    ma20_series = ma20_series.iloc[-limit:]
    ma50_series = ma50_series.iloc[-limit:]
    bb_df = bb_df.iloc[-limit:]

    def _val(v) -> float | None:
        import math
        if v is None:
            return None
        try:
            f = float(v)
            return None if math.isnan(f) else round(f, 3)
        except (TypeError, ValueError):
            return None

    candles = []
    for i, (ts, row) in enumerate(df.iterrows()):
        candles.append({
            "t": str(ts)[:16],
            "o": round(float(row["open"]), 3),
            "h": round(float(row["high"]), 3),
            "l": round(float(row["low"]), 3),
            "c": round(float(row["close"]), 3),
            "ma20": _val(ma20_series.iloc[i]),
            "ma50": _val(ma50_series.iloc[i]),
            "bb_upper": _val(bb_df["bb_upper"].iloc[i]),
            "bb_lower": _val(bb_df["bb_lower"].iloc[i]),
        })
    return {"candles": candles, "symbol": symbol, "tf": tf, "count": len(candles)}


# ============================================================
# Phase 29: ブラウザ通知用シグナルAPI
# ============================================================

@router.get("/api/latest-signal")
async def api_latest_signal(symbol: str = DEFAULT_SYMBOL):
    """最新のシグナル情報をJSONで返す（ブラウザ通知ポーリング用）。

    _signal_cache に値がない場合は signal="NONE" を返す。
    ブラウザ側で前回値と比較し、BUY/SELL への変化時に通知を出す。
    """
    if symbol not in SUPPORTED_SYMBOLS:
        symbol = DEFAULT_SYMBOL
    cached = _signal_cache.get(symbol)
    if cached is None:
        return {"symbol": symbol, "signal": "NONE", "score": None, "current_price": None, "analyzed_at": None}
    return {"symbol": symbol, **cached}


@router.get("/api/all-signals")
async def api_all_signals():
    """全サポート通貨ペアの最新シグナルを一括返却する（ダッシュボード通知用）。"""
    result = []
    for sym in SUPPORTED_SYMBOLS:
        cached = _signal_cache.get(sym)
        if cached:
            result.append({"symbol": sym, **cached})
        else:
            result.append({"symbol": sym, "signal": "NONE", "score": None, "current_price": None, "analyzed_at": None})
    return {"signals": result}


# ============================================================
# Phase 33: カスタムアラート設定
# ============================================================

@router.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request):
    """アラート一覧・作成ページ。"""
    alerts = get_alerts()
    return templates.TemplateResponse("alerts.html", {
        "request": request,
        "alerts": alerts,
        "symbols": SUPPORTED_SYMBOLS,
        "condition_types": ALERT_CONDITION_TYPES,
    })


@router.post("/alerts")
async def create_alert_route(
    request: Request,
    symbol: str = Form(...),
    label: str = Form(...),
    condition_type: str = Form(...),
    condition_value: str = Form(...),
    cooldown_minutes: int = Form(60),
):
    """アラートを新規作成してアラートページへリダイレクト。"""
    label = label.strip()
    condition_value = condition_value.strip()
    if not label or not condition_value:
        raise HTTPException(status_code=400, detail="ラベルと条件値は必須です。")
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail="無効な通貨ペアです。")
    try:
        create_alert(
            symbol=symbol,
            label=label,
            condition_type=condition_type,
            condition_value=condition_value,
            cooldown_minutes=cooldown_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse("/alerts", status_code=303)


@router.post("/alerts/{alert_id}/toggle")
async def toggle_alert_route(alert_id: int):
    """アラートの有効/無効を切り替えてアラートページへリダイレクト。"""
    try:
        toggle_alert(alert_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return RedirectResponse("/alerts", status_code=303)


@router.post("/alerts/{alert_id}/delete")
async def delete_alert_route(alert_id: int):
    """アラートを削除してアラートページへリダイレクト。"""
    delete_alert(alert_id)
    return RedirectResponse("/alerts", status_code=303)


# ============================================================
# Phase 34: トレードジャーナル
# ============================================================

@router.get("/journal", response_class=HTMLResponse)
async def journal_page(
    request: Request,
    tag: str = "",
    entry_type: str = "",
    page: int = 1,
):
    """ジャーナル一覧ページ。タグ・タイプ絞り込み対応。"""
    per_page = 20
    offset = (page - 1) * per_page
    tag_filter = tag.strip() or None
    type_filter = entry_type.strip() or None

    entries = get_journal_entries(
        tag_filter=tag_filter,
        entry_type_filter=type_filter,
        limit=per_page,
        offset=offset,
    )
    total = get_journal_count(tag_filter=tag_filter, entry_type_filter=type_filter)
    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse("journal.html", {
        "request": request,
        "entries": entries,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "entry_types": JOURNAL_ENTRY_TYPES,
        "emotion_labels": JOURNAL_EMOTION_LABELS,
        "tag_filter": tag or "",
        "type_filter": entry_type or "",
    })


@router.post("/journal/{record_id}")
async def save_journal(
    record_id: int,
    notes: str = Form(""),
    tags: str = Form(""),
    entry_type: str = Form("その他"),
    emotion_score: int = Form(3),
):
    """ジャーナルを保存して履歴ページへリダイレクト。"""
    approval = get_approval_by_id(record_id)
    if not approval:
        raise HTTPException(status_code=404, detail="承認記録が見つかりません。")
    upsert_journal(
        approval_id=record_id,
        notes=notes.strip(),
        tags=tags.strip(),
        entry_type=entry_type,
        emotion_score=max(1, min(5, emotion_score)),
    )
    return RedirectResponse(f"/history?highlight={record_id}", status_code=303)


# ============================================================
# Phase 35: CSV エクスポート
# ============================================================

def _rows_to_csv(rows: list[dict], filename: str) -> StreamingResponse:
    """行リストを CSV StreamingResponse に変換する。"""
    if not rows:
        output = io.StringIO()
        output.write("データがありません\n")
        output.seek(0)
    else:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/history.csv")
async def export_history(
    symbol: str = "",
    signal: str = "",
    human_action: str = "",
    date_from: str = "",
    date_to: str = "",
):
    """承認履歴を CSV でダウンロード。"""
    rows = get_history_for_export(
        symbol=symbol or None,
        signal=signal or None,
        human_action=human_action or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )
    return _rows_to_csv(rows, "fx_history.csv")


@router.get("/export/journal.csv")
async def export_journal(
    tag: str = "",
    entry_type: str = "",
):
    """ジャーナルを CSV でダウンロード。"""
    rows = get_journal_for_export(
        tag_filter=tag or None,
        entry_type_filter=entry_type or None,
    )
    return _rows_to_csv(rows, "fx_journal.csv")


@router.get("/export/demo-orders.csv")
async def export_demo_orders():
    """デモ注文成績を CSV でダウンロード。"""
    rows = get_demo_orders_for_export()
    return _rows_to_csv(rows, "fx_demo_orders.csv")


# ============================================================
# Phase 36: 戦略パラメータ最適化
# ============================================================

@router.get("/optimizer", response_class=HTMLResponse)
async def optimizer_page(request: Request):
    """最適化フォームページ（初期表示）。"""
    return templates.TemplateResponse("optimizer.html", {
        "request": request,
        "symbols": SUPPORTED_SYMBOLS,
        "metrics": VALID_METRICS,
        "results": None,
        "error": None,
        "form": {},
    })


@router.post("/optimizer", response_class=HTMLResponse)
async def optimizer_run(
    request: Request,
    symbol: str = Form("USD/JPY"),
    ma_short: str = Form("10,15,20,25"),
    ma_long: str = Form("50,75,100"),
    rsi_max: str = Form("65,70,75"),
    metric: str = Form("win_rate"),
    window: int = Form(300),
    step: int = Form(24),
):
    """最適化を実行して結果を表示する。"""
    form = dict(symbol=symbol, ma_short=ma_short, ma_long=ma_long,
                rsi_max=rsi_max, metric=metric, window=window, step=step)
    try:
        ma_s  = sorted({int(x.strip()) for x in ma_short.split(",") if x.strip()})
        ma_l  = sorted({int(x.strip()) for x in ma_long.split(",") if x.strip()})
        rsi_m = sorted({int(x.strip()) for x in rsi_max.split(",") if x.strip()})
        results = optimize(
            symbol=symbol,
            ma_short_values=ma_s,
            ma_long_values=ma_l,
            rsi_buy_max_values=rsi_m,
            metric=metric,
            window=window,
            step=step,
        )
    except Exception as e:
        return templates.TemplateResponse("optimizer.html", {
            "request": request,
            "symbols": SUPPORTED_SYMBOLS,
            "metrics": VALID_METRICS,
            "results": None,
            "error": str(e),
            "form": form,
        })

    return templates.TemplateResponse("optimizer.html", {
        "request": request,
        "symbols": SUPPORTED_SYMBOLS,
        "metrics": VALID_METRICS,
        "results": results[:20],
        "error": None,
        "form": form,
        "best": results[0] if results else None,
    })


@router.get("/correlation", response_class=HTMLResponse)
async def correlation_page(
    request: Request,
    lookback: int = 63,
):
    """通貨相関マトリクスページ。"""
    try:
        corr = calculate_correlation_matrix(lookback_days=lookback)
        error = None
    except Exception as e:
        logger.exception("相関マトリクス計算エラー")
        corr = None
        error = str(e)

    return templates.TemplateResponse("correlation.html", {
        "request": request,
        "corr": corr,
        "error": error,
        "lookback": lookback,
        "lookback_options": LOOKBACK_OPTIONS,
        "correlation_label": correlation_label,
    })


# ============================================================
# Phase 39: 経済指標カレンダー
# ============================================================

@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    page: int = 1,
    currency: str = "",
    importance: str = "",
    per_page: int = 20,
):
    """経済指標カレンダーページ。"""
    offset = (page - 1) * per_page
    cur_filter = currency.strip().upper() or None
    imp_filter = importance.strip() or None
    events = get_economic_events(
        limit=per_page, offset=offset,
        currency=cur_filter, importance=imp_filter,
    )
    total = count_economic_events(currency=cur_filter, importance=imp_filter)
    total_pages = (total + per_page - 1) // per_page
    warning_events = get_upcoming_warning_events()
    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "events": events,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "currency_filter": currency,
        "importance_filter": importance,
        "importance_levels": IMPORTANCE_LEVELS,
        "importance_labels": IMPORTANCE_LABELS,
        "warning_events": warning_events,
    })


@router.post("/calendar", response_class=HTMLResponse)
async def calendar_create(
    request: Request,
    event_dt: str = Form(...),
    currency: str = Form(...),
    importance: str = Form("MEDIUM"),
    event_name: str = Form(...),
    note: str = Form(""),
):
    """経済指標イベントを新規登録する。"""
    try:
        create_economic_event(
            event_dt=event_dt,
            currency=currency,
            importance=importance,
            event_name=event_name,
            note=note,
        )
    except Exception as e:
        logger.warning("経済指標登録エラー: %s", e)
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/calendar/{event_id}/delete", response_class=HTMLResponse)
async def calendar_delete(event_id: int):
    """経済指標イベントを削除する。"""
    delete_economic_event(event_id)
    return RedirectResponse(url="/calendar", status_code=303)


@router.get("/api/upcoming-events")
async def api_upcoming_events(hours: int = 24):
    """直近 hours 時間以内の HIGH/MEDIUM イベントをJSONで返す。"""
    events = get_upcoming_warning_events(window_hours=hours)
    return {"events": events, "count": len(events), "has_warning": len(events) > 0}


# ============================================================
# Phase 41: Web Push 通知 API
# ============================================================

@router.get("/api/push/vapid-public-key")
async def api_vapid_public_key():
    """VAPID 公開鍵（base64url）を返す。ブラウザの pushManager.subscribe() で使用する。"""
    pub, _ = get_or_create_vapid_keys()
    return {"publicKey": pub}


@router.post("/api/push/subscribe")
async def api_push_subscribe(request: Request):
    """Push 購読情報を保存する。

    ボディ: {"endpoint": "...", "keys": {"p256dh": "...", "auth": "..."}}
    """
    try:
        body = await request.json()
        endpoint = body["endpoint"]
        keys = body.get("keys", {})
        p256dh = keys.get("p256dh", "")
        auth = keys.get("auth", "")
        user_agent = request.headers.get("user-agent", "")[:200]
        if not endpoint or not p256dh or not auth:
            return {"ok": False, "error": "endpoint / p256dh / auth は必須です"}
        sub_id = save_push_subscription(endpoint, p256dh, auth, user_agent)
        return {"ok": True, "id": sub_id}
    except Exception as exc:
        logger.warning("Push subscribe error: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.post("/api/push/unsubscribe")
async def api_push_unsubscribe(request: Request):
    """Push 購読情報を削除する。ボディ: {"endpoint": "..."}"""
    try:
        body = await request.json()
        endpoint = body.get("endpoint", "")
        deleted = delete_push_subscription(endpoint)
        return {"ok": True, "deleted": deleted}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/api/push/test")
async def api_push_test():
    """全購読者にテスト通知を送信する。"""
    from app.services.push_sender import send_push_to_all
    subs = get_push_subscriptions()
    if not subs:
        return {"ok": False, "sent": 0, "error": "購読者が0件です"}
    result = await send_push_to_all()
    return {"ok": True, **result, "total": len(subs)}


# ============================================================
# Phase 42: ウォークフォワード分析 API
# ============================================================

@router.get("/api/walk-forward")
async def api_walk_forward(
    symbol: str = "",
    n_windows: int = DEFAULT_N_WINDOWS,
    is_ratio: float = DEFAULT_IS_RATIO,
    window_bars: int = DEFAULT_WINDOW_BARS,
    step: int = DEFAULT_STEP,
    future_bars: int = DEFAULT_FUTURE_BARS,
):
    """ウォークフォワード分析を実行して JSON で返す。

    注文は発生しない。分析・集計のみ。
    """
    if not symbol or symbol not in SUPPORTED_SYMBOLS:
        return {"ok": False, "error": f"未対応シンボル: {symbol}"}

    is_ratio = max(0.5, min(0.9, is_ratio))
    n_windows = max(2, min(10, n_windows))
    window_bars = max(200, min(2000, window_bars))
    step = max(1, min(168, step))
    future_bars = max(10, min(500, future_bars))

    try:
        result = run_walk_forward(
            symbol=symbol,
            n_windows=n_windows,
            is_ratio=is_ratio,
            window_bars=window_bars,
            step=step,
            future_bars=future_bars,
        )
    except Exception as exc:
        logger.error("ウォークフォワードエラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    windows_data = [
        {
            "window_num": w.window_num,
            "is_start_bar": w.is_start_bar,
            "is_end_bar": w.is_end_bar,
            "oos_start_bar": w.oos_start_bar,
            "oos_end_bar": w.oos_end_bar,
            "is_trades": w.is_trades,
            "is_wins": w.is_wins,
            "is_losses": w.is_losses,
            "is_win_rate": w.is_win_rate,
            "is_total_pips": w.is_total_pips,
            "is_avg_pips": w.is_avg_pips,
            "oos_trades": w.oos_trades,
            "oos_wins": w.oos_wins,
            "oos_losses": w.oos_losses,
            "oos_win_rate": w.oos_win_rate,
            "oos_total_pips": w.oos_total_pips,
            "oos_avg_pips": w.oos_avg_pips,
            "overfitting_score": w.overfitting_score,
            "robustness_ratio": w.robustness_ratio,
        }
        for w in result.windows
    ]

    return {
        "ok": True,
        "symbol": result.symbol,
        "n_windows": result.n_windows,
        "is_ratio": result.is_ratio,
        "window_bars": result.window_bars,
        "step": result.step,
        "total_data_bars": result.total_data_bars,
        "windows": windows_data,
        "avg_is_win_rate": result.avg_is_win_rate,
        "avg_oos_win_rate": result.avg_oos_win_rate,
        "avg_is_pips": result.avg_is_pips,
        "avg_oos_pips": result.avg_oos_pips,
        "avg_overfitting_score": result.avg_overfitting_score,
        "avg_robustness_ratio": result.avg_robustness_ratio,
        "total_oos_trades": result.total_oos_trades,
        "total_oos_wins": result.total_oos_wins,
        "total_oos_losses": result.total_oos_losses,
        "combined_oos_win_rate": result.combined_oos_win_rate,
        "combined_oos_pips": result.combined_oos_pips,
        "assessment": result.assessment,
    }


# ============================================================
# Phase 43: モンテカルロ分析 API
# ============================================================

@router.get("/api/monte-carlo")
async def api_monte_carlo(
    symbol: str = "",
    n_simulations: int = DEFAULT_N_SIMULATIONS,
    ruin_threshold: float = DEFAULT_RUIN_THRESHOLD,
    data_source: str = "backtest",
):
    """モンテカルロ分析を実行して JSON で返す。

    注文は発生しない。分析・集計のみ。

    Args:
        symbol:        通貨ペア（空 = 全ペア）
        n_simulations: シミュレーション回数（10〜5000）
        ruin_threshold: 破産閾値 pips（例: -200）
        data_source:   "backtest"=バックテスト結果のみ / "real"=実承認のみ / "all"=両方
    """
    n_simulations = max(10, min(5000, n_simulations))

    is_simulation: bool | None = None
    if data_source == "backtest":
        is_simulation = True
    elif data_source == "real":
        is_simulation = False

    try:
        pnl_pips = get_pnl_pips_from_db(
            symbol=symbol or None,
            is_simulation=is_simulation,
        )
    except Exception as exc:
        logger.error("モンテカルロ DB取得エラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    if not pnl_pips:
        return {
            "ok": False,
            "error": "対象トレードデータがありません。先にバックテストを実行してDBに保存してください。",
        }

    try:
        result = run_monte_carlo(
            pnl_pips=pnl_pips,
            n_simulations=n_simulations,
            ruin_threshold=ruin_threshold,
        )
    except Exception as exc:
        logger.error("モンテカルロ実行エラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    def ps_to_dict(ps):
        if ps is None:
            return None
        return {
            "p5": ps.p5, "p25": ps.p25, "p50": ps.p50,
            "p75": ps.p75, "p95": ps.p95,
            "mean": ps.mean, "min": ps.minimum, "max": ps.maximum,
        }

    return {
        "ok": True,
        "n_trades": result.n_trades,
        "n_simulations": result.n_simulations,
        "ruin_threshold": result.ruin_threshold,
        "raw_win_rate": result.raw_win_rate,
        "raw_total_pips": result.raw_total_pips,
        "raw_max_drawdown": result.raw_max_drawdown,
        "final_pips": ps_to_dict(result.final_pips),
        "max_drawdown": ps_to_dict(result.max_drawdown),
        "ruin_probability": result.ruin_probability,
        "profit_probability": result.profit_probability,
        "win_rate_ci_lower": result.win_rate_ci_lower,
        "win_rate_ci_upper": result.win_rate_ci_upper,
        "assessment": result.assessment,
    }


# ============================================================
# Phase 44: パラメータ感度分析 API
# ============================================================

@router.get("/api/sensitivity")
async def api_sensitivity(
    symbol: str = "",
    param_x: str = "ma_short",
    param_y: str = "ma_long",
    base_ma_short: int = 20,
    base_ma_long: int = 75,
    base_rsi_buy_max: int = 70,
    base_rsi_buy_min: int = 40,
    base_rsi_sell_min: int = 30,
    base_rsi_sell_max: int = 60,
    window: int = 300,
    step_bars: int = 24,
    future_bars: int = 80,
):
    """パラメータ感度分析を実行して JSON で返す。

    注文は発生しない。分析・集計のみ。
    """
    if not symbol or symbol not in SUPPORTED_SYMBOLS:
        return {"ok": False, "error": f"未対応シンボル: {symbol}"}
    if param_x not in SENSITIVITY_PARAMS:
        return {"ok": False, "error": f"未対応パラメータ: {param_x}"}
    if param_y not in SENSITIVITY_PARAMS:
        return {"ok": False, "error": f"未対応パラメータ: {param_y}"}
    if param_x == param_y:
        return {"ok": False, "error": "param_x と param_y に同じパラメータは指定できません"}

    from app.scripts.optimizer import OptimizeParams
    base_params = OptimizeParams(
        ma_short=max(5, min(200, base_ma_short)),
        ma_long=max(5, min(200, base_ma_long)),
        rsi_buy_max=max(10, min(90, base_rsi_buy_max)),
        rsi_buy_min=max(10, min(90, base_rsi_buy_min)),
        rsi_sell_min=max(10, min(90, base_rsi_sell_min)),
        rsi_sell_max=max(10, min(90, base_rsi_sell_max)),
    )
    window = max(100, min(1000, window))
    step_bars = max(1, min(168, step_bars))
    future_bars = max(10, min(500, future_bars))

    try:
        result = run_sensitivity(
            symbol=symbol,
            param_x=param_x,
            param_y=param_y,
            base_params=base_params,
            steps=DEFAULT_STEPS,
            window=window,
            step_bars=step_bars,
            future_bars=future_bars,
        )
    except Exception as exc:
        logger.error("感度分析エラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    cells_data = [
        [
            {
                "x_val": c.x_val,
                "y_val": c.y_val,
                "trades": c.trades,
                "wins": c.wins,
                "losses": c.losses,
                "win_rate": c.win_rate,
                "total_pips": c.total_pips,
                "avg_pips": c.avg_pips,
            }
            for c in row
        ]
        for row in result.cells
    ]

    return {
        "ok": True,
        "symbol": result.symbol,
        "param_x": result.param_x,
        "param_x_label": SENSITIVITY_PARAMS[result.param_x],
        "param_y": result.param_y,
        "param_y_label": SENSITIVITY_PARAMS[result.param_y],
        "base_x": result.base_x,
        "base_y": result.base_y,
        "x_values": result.x_values,
        "y_values": result.y_values,
        "cells": cells_data,
        "base_win_rate": result.base_win_rate,
        "base_total_pips": result.base_total_pips,
        "assessment": result.assessment,
    }


@router.get("/api/heatmap-calendar")
async def api_heatmap_calendar(
    symbol: str = "",
    metric: str = "win_rate",
    data_source: str = "all",
):
    """曜日×時間帯ヒートマップを JSON で返す。

    注文は発生しない。集計・可視化のみ。
    """
    # symbol バリデーション（空文字は全通貨ペア）
    sym: str | None = None
    if symbol:
        if symbol not in SUPPORTED_SYMBOLS:
            return {"ok": False, "error": f"未対応シンボル: {symbol}"}
        sym = symbol

    if metric not in HEATMAP_VALID_METRICS:
        return {"ok": False, "error": f"未対応metric: {metric}。有効値: {sorted(HEATMAP_VALID_METRICS)}"}

    is_simulation: bool | None = None
    if data_source == "simulation":
        is_simulation = True
    elif data_source == "real":
        is_simulation = False

    try:
        rows = get_heatmap_rows(symbol=sym, is_simulation=is_simulation)
        result = build_heatmap(rows, metric=metric, symbol=sym)
    except Exception as exc:
        logger.error("ヒートマップ生成エラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    cells_data = [
        [
            {
                "weekday": c.weekday,
                "hour": c.hour,
                "trades": c.trades,
                "wins": c.wins,
                "losses": c.losses,
                "win_rate": c.win_rate,
                "total_pips": c.total_pips,
                "avg_pips": c.avg_pips,
            }
            for c in row
        ]
        for row in result.cells
    ]

    return {
        "ok": True,
        "symbol": result.symbol,
        "metric": result.metric,
        "weekday_labels": WEEKDAY_LABELS,
        "cells": cells_data,
        "total_trades": result.total_trades,
        "overall_win_rate": result.overall_win_rate,
        "assessment": result.assessment,
    }


@router.get("/api/signal-quality")
async def api_signal_quality(
    symbol: str = "",
    signal: str = "",
    score: int | None = None,
    rsi: float | None = None,
    daily_trend: str = "",
    h4_trend: str = "",
):
    """シグナル品質スコアを JSON で返す。

    注文は発生しない。分析・集計のみ。
    """
    if not symbol or symbol not in SUPPORTED_SYMBOLS:
        return {"ok": False, "error": f"未対応シンボル: {symbol}"}
    if signal not in ("BUY", "SELL"):
        return {"ok": False, "error": "signal は BUY または SELL を指定してください"}

    try:
        quality = get_signal_quality(
            symbol=symbol,
            signal=signal,
            score=score,
            rsi=rsi,
            daily_trend=daily_trend or None,
            h4_trend=h4_trend or None,
        )
    except Exception as exc:
        logger.error("品質スコアエラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "symbol": symbol,
        "signal": signal,
        "dimension": quality.dimension,
        "trades": quality.trades,
        "wins": quality.wins,
        "win_rate": quality.win_rate,
        "avg_pips": quality.avg_pips,
        "quality_label": quality.quality_label,
        "quality_level": quality.quality_level,
        "quality_description": quality.quality_description,
        "quality_css": QUALITY_CSS[quality.quality_level],
        "score_bucket": quality.score_bucket,
        "rsi_bucket": quality.rsi_bucket,
        "trend_match": quality.trend_match,
    }


@router.get("/api/signal-quality/patterns")
async def api_signal_quality_patterns(symbol: str = ""):
    """全パターン統計一覧を JSON で返す（分析ページ用）。

    注文は発生しない。集計のみ。
    """
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        patterns = get_all_pattern_stats(symbol=sym)
    except Exception as exc:
        logger.error("パターン統計エラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "symbol": sym, "patterns": patterns}


@router.get("/drawdown")
async def drawdown_page(request: Request, symbol: str = ""):
    """ドローダウン分析ページ（Phase 47）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    stats = get_drawdown_stats(symbol=sym)
    by_symbol = get_drawdown_by_symbol()
    chart_data = equity_curve_to_chart_data(stats.equity_curve)
    return templates.TemplateResponse(
        "drawdown.html",
        {
            "request": request,
            "symbol": sym,
            "supported_symbols": SUPPORTED_SYMBOLS,
            "stats": stats,
            "by_symbol": by_symbol,
            "chart_data": chart_data,
        },
    )


@router.get("/api/drawdown")
async def api_drawdown(symbol: str = ""):
    """ドローダウン統計を JSON で返す（Phase 47）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        stats = get_drawdown_stats(symbol=sym)
        chart_data = equity_curve_to_chart_data(stats.equity_curve)
    except Exception as exc:
        logger.error("ドローダウンエラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "symbol": sym,
        "trades": stats.trades,
        "total_pips": stats.total_pips,
        "max_drawdown": stats.max_drawdown,
        "max_drawdown_pct": stats.max_drawdown_pct,
        "avg_drawdown": stats.avg_drawdown,
        "longest_drawdown_bars": stats.longest_drawdown_bars,
        "recovery_factor": stats.recovery_factor,
        "profit_factor": stats.profit_factor,
        "avg_win_pips": stats.avg_win_pips,
        "avg_loss_pips": stats.avg_loss_pips,
        "risk_reward": stats.risk_reward,
        "win_rate": stats.win_rate,
        "chart_data": chart_data,
    }


@router.get("/multi-symbol", response_class=HTMLResponse)
async def multi_symbol_page(request: Request, sort_by: str = "total_pips"):
    """マルチシンボル比較分析ページ（Phase 49）。注文は発生しない。"""
    try:
        report = get_multi_symbol_report(sort_by=sort_by)
    except Exception as exc:
        logger.error("マルチシンボル分析エラー: %s", exc)
        report = None

    return templates.TemplateResponse(
        "multi_symbol.html",
        {
            "request": request,
            "report": report,
            "sort_by": sort_by,
            "supported_symbols": SUPPORTED_SYMBOLS,
            "sort_options": [
                ("total_pips", "合計損益"),
                ("win_rate", "勝率"),
                ("avg_pips", "平均損益"),
                ("trades", "トレード数"),
                ("profit_factor", "プロフィットファクター"),
                ("avg_score", "平均スコア"),
            ],
        },
    )


@router.get("/api/multi-symbol")
async def api_multi_symbol(sort_by: str = "total_pips"):
    """マルチシンボル比較統計を JSON で返す（Phase 49）。注文は発生しない。"""
    try:
        report = get_multi_symbol_report(sort_by=sort_by)
    except Exception as exc:
        logger.error("マルチシンボル統計APIエラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "sort_by": report.sort_by,
        "total_trades": report.total_trades,
        "total_pips": report.total_pips,
        "overall_win_rate": report.overall_win_rate,
        "symbols": [
            {
                "rank": s.rank,
                "symbol": s.symbol,
                "trades": s.trades,
                "win_count": s.win_count,
                "loss_count": s.loss_count,
                "open_count": s.open_count,
                "win_rate": s.win_rate,
                "total_pips": s.total_pips,
                "avg_pips": s.avg_pips,
                "avg_score": s.avg_score,
                "avg_rsi": s.avg_rsi,
                "profit_factor": s.profit_factor,
                "max_win_pips": s.max_win_pips,
                "max_loss_pips": s.max_loss_pips,
                "buy_count": s.buy_count,
                "sell_count": s.sell_count,
            }
            for s in report.symbols
        ],
    }


@router.get("/pattern", response_class=HTMLResponse)
async def pattern_page(request: Request, symbol: str = ""):
    """トレードパターン認識ページ（Phase 49）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        report = get_pattern_report(symbol=sym)
    except Exception as exc:
        logger.error("パターン認識エラー: %s", exc)
        report = None

    return templates.TemplateResponse(
        "pattern.html",
        {
            "request": request,
            "report": report,
            "selected_symbol": sym or "",
            "supported_symbols": SUPPORTED_SYMBOLS,
        },
    )


@router.get("/api/pattern")
async def api_pattern(symbol: str = ""):
    """パターン認識統計を JSON で返す（Phase 49）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        report = get_pattern_report(symbol=sym)
    except Exception as exc:
        logger.error("パターン認識APIエラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    def _clusters(lst):
        return [
            {
                "label": c.label,
                "category": c.category,
                "trades": c.trades,
                "win_count": c.win_count,
                "loss_count": c.loss_count,
                "win_rate": c.win_rate,
                "total_pips": c.total_pips,
                "avg_pips": c.avg_pips,
                "profit_factor": c.profit_factor,
            }
            for c in lst
        ]

    return {
        "ok": True,
        "symbol": sym,
        "total_closed": report.total_closed,
        "by_signal": _clusters(report.by_signal),
        "by_rsi": _clusters(report.by_rsi),
        "by_trend": _clusters(report.by_trend),
        "by_score": _clusters(report.by_score),
        "by_session": _clusters(report.by_session),
    }


@router.get("/api/streaks")
async def api_streaks(symbol: str = ""):
    """連勝/連敗ストリーク統計を JSON で返す（Phase 48）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        stats = get_streak_stats(symbol=sym)
    except Exception as exc:
        logger.error("ストリーク統計エラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "symbol": sym,
        "trades": stats.trades,
        "max_win_streak": stats.max_win_streak,
        "max_loss_streak": stats.max_loss_streak,
        "current_streak_type": stats.current_streak_type,
        "current_streak_length": stats.current_streak_length,
        "avg_win_streak": stats.avg_win_streak,
        "avg_loss_streak": stats.avg_loss_streak,
        "total_win_streaks": stats.total_win_streaks,
        "total_loss_streaks": stats.total_loss_streaks,
        "longest_win_streak_start": stats.longest_win_streak_start,
        "longest_loss_streak_start": stats.longest_loss_streak_start,
        "streaks": [
            {
                "type": e.type,
                "length": e.length,
                "start_at": e.start_at,
                "end_at": e.end_at,
            }
            for e in stats.streaks
        ],
    }


@router.get("/r-multiple", response_class=HTMLResponse)
async def r_multiple_page(request: Request, symbol: str = ""):
    """R倍数・期待値分析ページ（Phase 50）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        report = get_r_multiple_report(symbol=sym)
    except Exception as exc:
        logger.error("R倍数レポートエラー: %s", exc)
        report = get_r_multiple_report.__wrapped__(symbol=None) if False else None

    return templates.TemplateResponse(
        "r_multiple.html",
        {
            "request": request,
            "report": report,
            "symbol": sym or "",
            "supported_symbols": SUPPORTED_SYMBOLS,
        },
    )


@router.get("/api/r-multiple")
async def api_r_multiple(symbol: str = ""):
    """R倍数・期待値・SQN を JSON で返す（Phase 50）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        report = get_r_multiple_report(symbol=sym)
    except Exception as exc:
        logger.error("R倍数APIエラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "symbol": sym,
        "trades": report.trades,
        "avg_loss_pips": report.avg_loss_pips,
        "mean_r": report.mean_r,
        "median_r": report.median_r,
        "std_r": report.std_r,
        "min_r": report.min_r,
        "max_r": report.max_r,
        "expectancy": report.expectancy,
        "sqn": report.sqn,
        "sqn_grade": report.sqn_grade,
        "positive_r_count": report.positive_r_count,
        "negative_r_count": report.negative_r_count,
        "histogram_labels": report.histogram_labels,
        "histogram_counts": report.histogram_counts,
        "by_symbol": report.by_symbol,
        "series": [
            {
                "record_id": t.record_id,
                "symbol": t.symbol,
                "outcome": t.outcome,
                "pnl_pips": t.pnl_pips,
                "r_value": t.r_value,
                "created_at": t.created_at,
            }
            for t in report.series
        ],
    }


@router.get("/position-sizing", response_class=HTMLResponse)
async def position_sizing_page(request: Request, symbol: str = ""):
    """ポジションサイジング計算ページ（Phase 51）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        hist = get_historical_stats(symbol=sym)
    except Exception as exc:
        logger.error("ポジションサイジング成績取得エラー: %s", exc)
        hist = {"win_rate": None, "avg_win_pips": None, "avg_loss_pips": None, "trades": 0}

    return templates.TemplateResponse(
        "position_sizing.html",
        {
            "request": request,
            "hist": hist,
            "symbol": sym or "",
            "supported_symbols": SUPPORTED_SYMBOLS,
        },
    )


@router.get("/api/position-sizing")
async def api_position_sizing(
    balance: float = 100000,
    risk_pct: float = 1.0,
    stop_pips: float = 20,
    pip_value: float = 1000,
    win_rate: float = 55,
    avg_win_pips: float = 20,
    avg_loss_pips: float = 10,
    min_lot: float = 0.01,
    lot_step: float = 0.01,
):
    """ポジションサイズを計算して JSON で返す（Phase 51）。注文は発生しない。"""
    try:
        inp = SizingInput(
            balance=balance,
            risk_pct=risk_pct,
            stop_pips=stop_pips,
            pip_value=pip_value,
            win_rate=win_rate,
            avg_win_pips=avg_win_pips,
            avg_loss_pips=avg_loss_pips,
            min_lot=min_lot,
            lot_step=lot_step,
        )
        result = calculate_sizing(inp)
    except Exception as exc:
        logger.error("ポジションサイジング計算エラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "fixed_risk_lot": result.fixed_risk_lot,
        "fixed_risk_amount": result.fixed_risk_amount,
        "kelly_fraction": result.kelly_fraction,
        "kelly_lot": result.kelly_lot,
        "half_kelly_lot": result.half_kelly_lot,
        "kelly_grade": result.kelly_grade,
        "expectancy_pips": result.expectancy_pips,
        "payoff_ratio": result.payoff_ratio,
        "warnings": result.warnings,
    }


@router.get("/period-stats", response_class=HTMLResponse)
async def period_stats_page(request: Request, symbol: str = ""):
    """月次・週次パフォーマンスサマリーページ（Phase 52）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        report = get_period_report(symbol=sym)
    except Exception as exc:
        logger.error("期間別統計エラー: %s", exc)
        report = get_period_report.__wrapped__(symbol=None) if False else None

    return templates.TemplateResponse(
        "period_stats.html",
        {
            "request": request,
            "report": report,
            "symbol": sym or "",
            "supported_symbols": SUPPORTED_SYMBOLS,
        },
    )


@router.get("/api/period-stats")
async def api_period_stats(symbol: str = ""):
    """月次・週次統計を JSON で返す（Phase 52）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        report = get_period_report(symbol=sym)
    except Exception as exc:
        logger.error("期間別統計APIエラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    def _stat(s):
        return {
            "label": s.label,
            "trades": s.trades,
            "wins": s.wins,
            "losses": s.losses,
            "win_rate": s.win_rate,
            "total_pips": s.total_pips,
            "avg_pips": s.avg_pips,
        }

    return {
        "ok": True,
        "symbol": sym,
        "total_trades": report.total_trades,
        "total_pips": report.total_pips,
        "max_consecutive_positive": report.max_consecutive_positive,
        "max_consecutive_negative": report.max_consecutive_negative,
        "best_month": _stat(report.best_month) if report.best_month else None,
        "worst_month": _stat(report.worst_month) if report.worst_month else None,
        "monthly": [_stat(s) for s in report.monthly],
        "weekly": [_stat(s) for s in report.weekly],
    }


@router.get("/scorecard", response_class=HTMLResponse)
async def scorecard_page(request: Request, symbol: str = ""):
    """システムスコアカードページ（Phase 53）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        sc = get_scorecard(symbol=sym)
    except Exception as exc:
        logger.error("スコアカードエラー: %s", exc)
        sc = get_scorecard.__wrapped__(symbol=None) if False else None

    return templates.TemplateResponse(
        "scorecard.html",
        {
            "request": request,
            "scorecard": sc,
            "grade_colors": GRADE_COLORS,
            "symbol": sym or "",
            "supported_symbols": SUPPORTED_SYMBOLS,
        },
    )


@router.get("/api/scorecard")
async def api_scorecard(symbol: str = ""):
    """システムスコアカードを JSON で返す（Phase 53）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    try:
        sc = get_scorecard(symbol=sym)
    except Exception as exc:
        logger.error("スコアカードAPIエラー: %s", exc)
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "symbol": sym,
        "total_trades": sc.total_trades,
        "overall_grade": sc.overall_grade,
        "overall_score": sc.overall_score,
        "recommendation": sc.recommendation,
        "metrics": [
            {
                "name": m.name,
                "key": m.key,
                "value": m.value,
                "unit": m.unit,
                "grade": m.grade,
                "comment": m.comment,
            }
            for m in sc.metrics
        ],
        "radar_labels": sc.radar_labels,
        "radar_values": sc.radar_values,
    }


@router.get("/goals", response_class=HTMLResponse)
async def goals_page(request: Request):
    """目標管理ページ（Phase 54）。注文は発生しない。"""
    try:
        goals = get_goals()
    except Exception as exc:
        logger.error("目標一覧取得エラー: %s", exc)
        goals = []

    return templates.TemplateResponse(
        "goals.html",
        {
            "request": request,
            "goals": goals,
            "current_month": current_month_label(),
            "current_week": current_week_label(),
            "supported_symbols": SUPPORTED_SYMBOLS,
        },
    )


@router.post("/goals", response_class=HTMLResponse)
async def goals_create(
    request: Request,
    period_type: str = Form(...),
    period_label: str = Form(...),
    target_pips: float = Form(...),
    symbol: str = Form(""),
    note: str = Form(""),
):
    """目標作成（Phase 54）。注文は発生しない。"""
    sym = symbol.strip() if symbol and symbol in SUPPORTED_SYMBOLS else None
    try:
        if period_type not in VALID_PERIOD_TYPES:
            raise ValueError(f"無効な期間タイプ: {period_type}")
        create_goal(
            period_type=period_type,
            period_label=period_label.strip(),
            target_pips=target_pips,
            symbol=sym,
            note=note.strip(),
        )
    except Exception as exc:
        logger.error("目標作成エラー: %s", exc)
    return RedirectResponse(url="/goals", status_code=303)


@router.post("/goals/{goal_id}/delete", response_class=HTMLResponse)
async def goals_delete(request: Request, goal_id: int):
    """目標削除（Phase 54）。注文は発生しない。"""
    try:
        delete_goal(goal_id)
    except Exception as exc:
        logger.error("目標削除エラー: %s", exc)
    return RedirectResponse(url="/goals", status_code=303)


@router.get("/rolling-stats", response_class=HTMLResponse)
async def rolling_stats_page(
    request: Request,
    symbol: str = "",
    window: int = ROLLING_DEFAULT_WINDOW,
):
    """ローリング成績分析ページ（Phase 55）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    win = window if window in ROLLING_VALID_WINDOWS else ROLLING_DEFAULT_WINDOW
    try:
        report = get_rolling_report(symbol=sym, window=win)
    except Exception as exc:
        logger.error("ローリング成績エラー: %s", exc)
        from app.scripts.rolling_stats import RollingReport
        report = RollingReport(window=win, symbol=sym, total_trades=0)

    return templates.TemplateResponse(
        "rolling_stats.html",
        {
            "request": request,
            "report": report,
            "symbol": sym or "",
            "supported_symbols": SUPPORTED_SYMBOLS,
            "valid_windows": sorted(ROLLING_VALID_WINDOWS),
        },
    )


@router.get("/api/rolling-stats")
async def api_rolling_stats(symbol: str = "", window: int = ROLLING_DEFAULT_WINDOW):
    """ローリング成績を JSON で返す（Phase 55）。注文は発生しない。"""
    sym = symbol if symbol in SUPPORTED_SYMBOLS else None
    win = window if window in ROLLING_VALID_WINDOWS else ROLLING_DEFAULT_WINDOW
    try:
        report = get_rolling_report(symbol=sym, window=win)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "symbol": sym,
        "window": report.window,
        "total_trades": report.total_trades,
        "trend": report.trend,
        "trend_label": report.trend_label,
        "overall_win_rate": report.overall_win_rate,
        "overall_expectancy": report.overall_expectancy,
        "last_win_rate": report.last_win_rate,
        "last_expectancy": report.last_expectancy,
        "last_profit_factor": report.last_profit_factor,
        "labels": report.labels,
        "win_rate_series": report.win_rate_series,
        "expectancy_series": report.expectancy_series,
        "profit_factor_series": report.profit_factor_series,
        "cumulative_series": report.cumulative_series,
    }
