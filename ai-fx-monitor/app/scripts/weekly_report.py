"""Phase 65: AIトレード週次レポート自動生成

直近1週間のトレード成績・累計指標・スコアカード・ストリークを集約し、
Claude API（または mock）で日本語サマリーを生成・DBに保存する。
注文は一切発生しない。集計・AI分析のみ。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from app.config import DB_PATH
from app.database.db import get_db


# ── データクラス ──────────────────────────────────────────────────────────

@dataclass
class WeeklyMetrics:
    week_label: str          # "2026-W21"
    week_start: str          # "2026-05-18"
    week_end: str            # "2026-05-24"
    symbol: str              # "" = 全通貨ペア

    # 今週のトレード
    week_trades: int = 0
    week_wins: int = 0
    week_losses: int = 0
    week_open: int = 0
    week_win_rate: Optional[float] = None
    week_pips: float = 0.0
    week_best_pips: Optional[float] = None
    week_worst_pips: Optional[float] = None

    # 全期間累計
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0
    total_win_rate: Optional[float] = None
    total_pips: float = 0.0

    # ストリーク
    current_streak: int = 0
    current_streak_type: str = ""  # "win" | "loss" | ""
    max_win_streak: int = 0
    max_loss_streak: int = 0

    # スコアカード
    overall_grade: str = "N/A"
    overall_score: float = 0.0

    # 目標管理
    goals_total: int = 0
    goals_achieved: int = 0

    # マクロイベント（今週分）
    macro_events: list[str] = field(default_factory=list)

    # Phase 70: 地政学リスクサマリー（今週分）
    geo_events: list[dict] = field(default_factory=list)
    geo_risk_summary: str = ""


@dataclass
class WeeklyReport:
    id: Optional[int]
    metrics: WeeklyMetrics
    ai_narrative: str
    ai_provider: str     # "claude" | "openai" | "mock"
    created_at: str


# ── 週ラベルユーティリティ ─────────────────────────────────────────────────

def current_week_label() -> str:
    """ISO 週番号ラベルを返す（例: "2026-W21"）。"""
    d = date.today()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(week_label: str) -> tuple[str, str]:
    """ISO 週ラベルから月曜〜日曜の日付文字列を返す (YYYY-MM-DD)。"""
    year_str, wnum_str = week_label.split("-W")
    year, wnum = int(year_str), int(wnum_str)
    monday = date.fromisocalendar(year, wnum, 1)
    sunday = monday + timedelta(days=6)
    return str(monday), str(sunday)


# ── 集計ロジック ──────────────────────────────────────────────────────────

def _collect_metrics(symbol: str, week_label: str, db_path=None) -> WeeklyMetrics:
    week_start, week_end = week_bounds(week_label)
    week_end_dt = week_end + " 23:59:59"
    sym_filter = symbol if symbol else ""

    metrics = WeeklyMetrics(
        week_label=week_label,
        week_start=week_start,
        week_end=week_end,
        symbol=symbol,
    )

    with get_db(db_path) as conn:
        # 今週のクローズ済みトレード
        rows = conn.execute(
            """
            SELECT outcome, pnl_pips FROM approval_history
            WHERE closed_at IS NOT NULL
              AND closed_at >= ? AND closed_at <= ?
              AND (symbol = ? OR ? = '')
              AND is_dummy_data = 0
            """,
            (week_start, week_end_dt, sym_filter, sym_filter),
        ).fetchall()

        week_pips_list = [r["pnl_pips"] for r in rows if r["pnl_pips"] is not None]
        metrics.week_trades = len(rows)
        metrics.week_wins = sum(1 for r in rows if r["outcome"] == "win")
        metrics.week_losses = sum(1 for r in rows if r["outcome"] == "loss")
        metrics.week_open = sum(1 for r in rows if r["outcome"] == "open")
        if metrics.week_trades > 0:
            closed = metrics.week_wins + metrics.week_losses
            metrics.week_win_rate = (metrics.week_wins / closed * 100) if closed > 0 else None
        metrics.week_pips = sum(week_pips_list)
        metrics.week_best_pips = max(week_pips_list) if week_pips_list else None
        metrics.week_worst_pips = min(week_pips_list) if week_pips_list else None

        # 全期間累計
        all_rows = conn.execute(
            """
            SELECT outcome, pnl_pips FROM approval_history
            WHERE closed_at IS NOT NULL
              AND (symbol = ? OR ? = '')
              AND is_dummy_data = 0
            """,
            (sym_filter, sym_filter),
        ).fetchall()
        metrics.total_trades = len(all_rows)
        metrics.total_wins = sum(1 for r in all_rows if r["outcome"] == "win")
        metrics.total_losses = sum(1 for r in all_rows if r["outcome"] == "loss")
        closed_total = metrics.total_wins + metrics.total_losses
        metrics.total_win_rate = (metrics.total_wins / closed_total * 100) if closed_total > 0 else None
        metrics.total_pips = sum(r["pnl_pips"] for r in all_rows if r["pnl_pips"] is not None)

        # ストリーク（最新順で連続 outcome をカウント）
        streak_rows = conn.execute(
            """
            SELECT outcome FROM approval_history
            WHERE closed_at IS NOT NULL
              AND outcome IN ('win', 'loss')
              AND (symbol = ? OR ? = '')
              AND is_dummy_data = 0
            ORDER BY closed_at DESC
            """,
            (sym_filter, sym_filter),
        ).fetchall()
        if streak_rows:
            first_outcome = streak_rows[0]["outcome"]
            streak = 0
            win_streak = 0
            loss_streak = 0
            cur_type = first_outcome
            for r in streak_rows:
                if r["outcome"] == cur_type:
                    streak += 1
                else:
                    break
            metrics.current_streak = streak
            metrics.current_streak_type = cur_type
            # 全期間の最大連勝/連敗
            run, run_type = 0, None
            for r in streak_rows[::-1]:
                if r["outcome"] == run_type:
                    run += 1
                else:
                    run = 1
                    run_type = r["outcome"]
                if run_type == "win":
                    win_streak = max(win_streak, run)
                else:
                    loss_streak = max(loss_streak, run)
            metrics.max_win_streak = win_streak
            metrics.max_loss_streak = loss_streak

        # 目標管理
        goal_rows = conn.execute(
            "SELECT COUNT(*) as total FROM trade_goals WHERE period_type = 'weekly'"
        ).fetchone()
        metrics.goals_total = goal_rows["total"] if goal_rows else 0

        # マクロイベント（今週）
        macro_rows = conn.execute(
            """
            SELECT title, event_type FROM macro_event_log
            WHERE event_date >= ? AND event_date <= ?
            ORDER BY event_date
            """,
            (week_start, week_end),
        ).fetchall()
        metrics.macro_events = [f"{r['event_type']}: {r['title']}" for r in macro_rows]

        # Phase 70: 地政学リスク（今週分）
        try:
            geo_rows = conn.execute(
                """
                SELECT event_date, category, usd_impact, event_text
                FROM geopolitical_log
                WHERE event_date >= ? AND event_date <= ?
                ORDER BY event_date
                """,
                (week_start, week_end),
            ).fetchall()
            metrics.geo_events = [
                {
                    "date": r["event_date"],
                    "category": r["category"],
                    "usd_impact": r["usd_impact"],
                    "event_text": r["event_text"][:80],
                }
                for r in geo_rows
            ]
            metrics.geo_risk_summary = _summarize_geo_risk(metrics.geo_events)
        except Exception:
            pass

    # スコアカードは別モジュールから取得
    try:
        from app.scripts.scorecard import get_scorecard
        sc = get_scorecard(symbol if symbol else None, db_path)
        metrics.overall_grade = sc.overall_grade
        metrics.overall_score = sc.overall_score
    except Exception:
        pass

    return metrics


# ── AI ナレーティブ生成 ────────────────────────────────────────────────────

_WEEKLY_SYSTEM_PROMPT = """あなたはFX取引のパフォーマンスレビューアシスタントです。

## 役割
トレーダーが自分の成績を振り返るための週次レポートを日本語で作成します。

## 絶対に守るルール
1. 具体的な売買指示・エントリー推奨は行わない
2. 「必ず」「絶対」「確実に」などの断言表現は使わない
3. 客観的な成績評価と改善のヒントのみを提供する
4. 最終判断は常にトレーダー自身が行うことを前提にする

## 出力形式
300〜500文字程度の日本語レポート。箇条書き不要。段落形式。
週の振り返り → 累計トレンド → 改善ポイント の順に記述。"""


def _build_weekly_prompt(m: WeeklyMetrics) -> str:
    lines = [
        f"【週次レポート対象期間】{m.week_start} 〜 {m.week_end}（{m.week_label}）",
        f"【対象通貨ペア】{m.symbol or '全ペア'}",
        "",
        "【今週の取引成績】",
        f"- 取引数: {m.week_trades}件",
        f"- 勝ち: {m.week_wins}件 / 負け: {m.week_losses}件",
        f"- 勝率: {m.week_win_rate:.1f}%" if m.week_win_rate is not None else "- 勝率: N/A",
        f"- 合計損益: {m.week_pips:+.1f} pips",
        f"- 最大利益: {m.week_best_pips:+.1f} pips" if m.week_best_pips is not None else "- 最大利益: N/A",
        f"- 最大損失: {m.week_worst_pips:+.1f} pips" if m.week_worst_pips is not None else "- 最大損失: N/A",
        "",
        "【累計成績】",
        f"- 総取引数: {m.total_trades}件",
        f"- 累計勝率: {m.total_win_rate:.1f}%" if m.total_win_rate is not None else "- 累計勝率: N/A",
        f"- 累計損益: {m.total_pips:+.1f} pips",
        f"- システムグレード: {m.overall_grade}（スコア: {m.overall_score:.1f}）",
        "",
        "【現在のストリーク】",
        f"- 現在: {m.current_streak}連{_streak_ja(m.current_streak_type)}" if m.current_streak else "- データなし",
        f"- 最大連勝: {m.max_win_streak}回 / 最大連敗: {m.max_loss_streak}回",
    ]
    if m.macro_events:
        lines += ["", "【今週のマクロイベント】"]
        lines += [f"- {e}" for e in m.macro_events[:5]]
    if m.geo_events:
        lines += ["", "【今週の地政学リスク分析】"]
        lines.append(f"- 概要: {m.geo_risk_summary}")
        for e in m.geo_events[:5]:
            impact_labels = {
                "strong_bullish": "強いドル高",
                "bullish": "ドル高",
                "neutral": "中立",
                "bearish": "ドル安",
                "strong_bearish": "強いドル安",
            }
            label = impact_labels.get(e["usd_impact"], e["usd_impact"])
            lines.append(f"- {e['date']} [{e['category']}] {e['event_text']} → {label}")
    return "\n".join(lines)


def _streak_ja(t: str) -> str:
    return "勝" if t == "win" else "敗" if t == "loss" else ""


def _summarize_geo_risk(geo_events: list[dict]) -> str:
    """地政学イベントリストからドル影響のサマリー文字列を生成する。"""
    if not geo_events:
        return ""
    bullish = sum(1 for e in geo_events if e["usd_impact"] in ("bullish", "strong_bullish"))
    bearish = sum(1 for e in geo_events if e["usd_impact"] in ("bearish", "strong_bearish"))
    neutral = len(geo_events) - bullish - bearish
    parts = []
    if bullish:
        parts.append(f"ドル高バイアス {bullish}件")
    if bearish:
        parts.append(f"ドル安バイアス {bearish}件")
    if neutral:
        parts.append(f"中立 {neutral}件")
    return " / ".join(parts)


def _generate_mock_narrative(m: WeeklyMetrics) -> str:
    parts = []
    # 今週の成績
    if m.week_trades == 0:
        parts.append(f"{m.week_label}は取引がありませんでした。")
    else:
        wr = f"{m.week_win_rate:.1f}%" if m.week_win_rate is not None else "N/A"
        direction = "プラス" if m.week_pips >= 0 else "マイナス"
        parts.append(
            f"{m.week_label}は{m.week_trades}件取引し、"
            f"勝率{wr}・{m.week_pips:+.1f}pipsの{direction}で終えました。"
        )
    # 累計
    if m.total_trades > 0:
        wr_total = f"{m.total_win_rate:.1f}%" if m.total_win_rate is not None else "N/A"
        parts.append(
            f"累計では{m.total_trades}件・勝率{wr_total}・"
            f"{m.total_pips:+.1f}pips、システムグレードは{m.overall_grade}です。"
        )
    # ストリーク
    if m.current_streak > 0:
        ja = _streak_ja(m.current_streak_type)
        parts.append(f"現在{m.current_streak}連{ja}中です。")
    # 地政学コンテキスト
    if m.geo_events and m.geo_risk_summary:
        parts.append(f"今週の地政学リスクは「{m.geo_risk_summary}」で、ドルへの影響が{len(m.geo_events)}件記録されました。")
    # 改善ヒント
    if m.week_losses > m.week_wins:
        parts.append("今週は損失が多かった週です。エントリー根拠の質を振り返り、無理なトレードがなかったか確認してみましょう。")
    elif m.week_pips < 0:
        parts.append("今週はトータルでマイナスです。RR比の実績を見直し、利確目標に到達できているか確認しましょう。")
    else:
        parts.append("着実に成績を積み上げています。ルールを守り続けることが長期的な安定につながります。")
    return "".join(parts)


def _generate_ai_narrative(m: WeeklyMetrics) -> tuple[str, str]:
    """(narrative, provider) を返す。"""
    user_prompt = _build_weekly_prompt(m)

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5"),
                max_tokens=800,
                system=[
                    {
                        "type": "text",
                        "text": _WEEKLY_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
            narrative = resp.content[0].text.strip()
            return narrative, "claude"
        except Exception:
            pass

    if os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _WEEKLY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=800,
            )
            narrative = resp.choices[0].message.content.strip()
            return narrative, "openai"
        except Exception:
            pass

    return _generate_mock_narrative(m), "mock"


# ── DB 操作 ───────────────────────────────────────────────────────────────

def save_weekly_report(report: WeeklyReport, db_path=None) -> int:
    """レポートをDBに保存してIDを返す。"""
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO weekly_report_log
                (created_at, week_label, week_start, week_end, symbol,
                 report_json, ai_narrative, ai_provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.created_at,
                report.metrics.week_label,
                report.metrics.week_start,
                report.metrics.week_end,
                report.metrics.symbol,
                json.dumps(asdict(report.metrics), ensure_ascii=False),
                report.ai_narrative,
                report.ai_provider,
            ),
        )
        return cur.lastrowid


def get_weekly_reports(symbol: str = "", limit: int = 12, db_path=None) -> list[WeeklyReport]:
    """過去レポートを新しい順で取得する。"""
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM weekly_report_log
            WHERE (symbol = ? OR ? = '')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (symbol, symbol, limit),
        ).fetchall()
    reports = []
    for row in rows:
        try:
            metrics_dict = json.loads(row["report_json"])
            metrics = WeeklyMetrics(**metrics_dict)
        except Exception:
            metrics = WeeklyMetrics(
                week_label=row["week_label"],
                week_start=row["week_start"],
                week_end=row["week_end"],
                symbol=row["symbol"],
            )
        reports.append(WeeklyReport(
            id=row["id"],
            metrics=metrics,
            ai_narrative=row["ai_narrative"],
            ai_provider=row["ai_provider"],
            created_at=row["created_at"],
        ))
    return reports


def get_latest_weekly_report(symbol: str = "", db_path=None) -> Optional[WeeklyReport]:
    reports = get_weekly_reports(symbol, limit=1, db_path=db_path)
    return reports[0] if reports else None


# ── 公開 API ─────────────────────────────────────────────────────────────

def generate_and_save_weekly_report(symbol: str = "", db_path=None) -> WeeklyReport:
    """今週のレポートを生成してDBに保存し、WeeklyReport を返す。"""
    week_label = current_week_label()
    metrics = _collect_metrics(symbol, week_label, db_path)
    narrative, provider = _generate_ai_narrative(metrics)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    report = WeeklyReport(
        id=None,
        metrics=metrics,
        ai_narrative=narrative,
        ai_provider=provider,
        created_at=now,
    )
    report.id = save_weekly_report(report, db_path)
    return report
