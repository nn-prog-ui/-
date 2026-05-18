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
)
from app.services.demo_order import DemoOrderError, DemoOrderAdapter, is_demo_order_available
from app.config import DATA_DIR, DEFAULT_SYMBOL, SUPPORTED_SYMBOLS, SYMBOL_CSV_MAP
from app.data.loader import load_or_generate
from app.data.resampler import to_4h, to_daily
from app.indicators.bollinger_bands import calculate_bollinger_bands
from app.indicators.moving_average import calculate_ma
from app.scripts.backtest import run_backtest
from app.scripts.optimizer import VALID_METRICS, optimize
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

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "result": result,
            "error": None,
            "supported_symbols": SUPPORTED_SYMBOLS,
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

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "analyses": analyses, "supported_symbols": SUPPORTED_SYMBOLS},
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
