"""FastAPIルーティング"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database.repository import (
    HUMAN_ACTION_BUY,
    HUMAN_ACTION_SELL,
    HUMAN_ACTION_SKIP,
    check_and_close_open_trades,
    get_approval_by_id,
    get_demo_orders,
    get_history,
    get_history_count,
    get_open_trades,
    get_performance_stats,
    save_approval,
    save_demo_order,
)
from app.services.demo_order import DemoOrderError, DemoOrderAdapter, is_demo_order_available
from app.config import DEFAULT_SYMBOL, SUPPORTED_SYMBOLS
from app.services.market_analyzer import AnalysisResult, run_analysis
from app.services.notification import notify_analysis_result

logger = logging.getLogger(__name__)
router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# 分析結果をリクエスト間で一時保持（本番ではRedisや引数渡しに変更）
_last_result: AnalysisResult | None = None


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, symbol: str = DEFAULT_SYMBOL):
    global _last_result
    if symbol not in SUPPORTED_SYMBOLS:
        symbol = DEFAULT_SYMBOL
    try:
        result = run_analysis(symbol=symbol)
        _last_result = result
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

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "records": records,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@router.get("/performance", response_class=HTMLResponse)
async def performance(request: Request):
    """パフォーマンス統計ページ。"""
    stats = get_performance_stats()
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
    return templates.TemplateResponse(
        "demo_trade.html",
        {
            "request": request,
            "step": "list",
            "orders": orders,
            "error": None,
        },
    )
