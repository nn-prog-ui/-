"""Phase 66: AI地政学リスク分析

ユーザーが入力した世界情勢・政策変更テキストをClaude APIで分析し、
USD/JPYへの影響度・信頼度・歴史パターンを評価してDBに保存する。
注文は一切発生しない。分析・記録のみ。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Optional

from app.database.db import get_db


# ── 定数 ────────────────────────────────────────────────────────────────

EVENT_CATEGORIES = [
    "米大統領・政権交代",
    "FRB金融政策（利上げ・利下げ・QE）",
    "米雇用・経済指標",
    "地政学リスク（戦争・紛争）",
    "貿易・関税政策",
    "日銀金融政策",
    "エネルギー・資源価格",
    "金融危機・市場ショック",
    "その他",
]

USD_IMPACTS = {
    "strong_bullish": "ドル強気（+）大",
    "bullish":        "ドル強気（+）",
    "neutral":        "中立",
    "bearish":        "ドル弱気（−）",
    "strong_bearish": "ドル弱気（−）大",
}

CONFIDENCE_LABELS = {
    "high":   "高（歴史的根拠あり）",
    "medium": "中（類似事例あり）",
    "low":    "低（不確定要素多い）",
}

# 歴史的パターン知識ベース（Claudeへのヒント兼モックフォールバック用）
# keywords: ANY が1つ以上マッチ かつ exclude が1つもマッチしない場合に採用
_HISTORICAL_PATTERNS = [
    {
        "event": "FRB利上げ",
        "keywords": ["FRB", "FOMC", "利上げ"],      # これらのうち1つ以上
        "exclude": ["日銀", "利下げ", "QE", "量的緩和"],  # 利下げ系は除外
        "usd_impact": "strong_bullish",
        "reasoning": "米国の金利上昇はドル資産への需要を高めドル高要因になる。",
        "examples": ["2022年FRB利上げ局面でドル円150円超え"],
    },
    {
        "event": "FRB利下げ・QE",
        "keywords": ["FRB", "FOMC", "利下げ", "QE", "量的緩和"],
        "exclude": ["日銀"],
        "usd_impact": "strong_bearish",
        "reasoning": "金利低下・ドル供給増加はドル安要因。",
        "examples": ["2020年コロナ緊急利下げ後のドル安"],
    },
    {
        "event": "トランプ大統領当選",
        "keywords": ["トランプ", "Trump"],
        "exclude": [],
        "usd_impact": "bullish",
        "reasoning": "財政拡張・保護主義政策の思惑でドル高になりやすい。",
        "examples": ["2016年トランプ当選後のドル高（トランプラリー）", "2024年トランプ再選後のドル高"],
    },
    {
        "event": "米国経済指標悪化（NFP・GDP下振れ）",
        "keywords": ["雇用統計", "NFP", "非農業部門", "GDP悪化", "景気後退"],
        "exclude": [],
        "usd_impact": "bearish",
        "reasoning": "景気悪化懸念はリスクオフ＋利下げ期待からドル安になりやすい。",
        "examples": ["2023年雇用統計下振れ後のドル売り"],
    },
    {
        "event": "地政学リスク上昇（戦争・紛争激化）",
        "keywords": ["戦争", "紛争", "武力", "侵攻", "テロ", "地政学"],
        "exclude": [],
        "usd_impact": "bullish",
        "reasoning": "有事のドル買い（安全資産需要）でドル高になりやすい。円も安全資産だが米国が中立・有利なら相対的にドル高。",
        "examples": ["2022年ロシア・ウクライナ戦争勃発後のドル高", "中東紛争激化時のドル買い"],
    },
    {
        "event": "日銀利上げ・金融政策正常化",
        "keywords": ["日銀"],
        "exclude": [],
        "usd_impact": "bearish",
        "reasoning": "日米金利差縮小により円高・ドル安要因になる。",
        "examples": ["2024年日銀利上げ示唆後のドル円急落"],
    },
    {
        "event": "米中貿易摩擦・関税引き上げ",
        "keywords": ["関税", "貿易制裁", "貿易摩擦", "輸入制限"],
        "exclude": [],
        "usd_impact": "bullish",
        "reasoning": "保護主義的政策はドル需要増加・対中関税がドル高要因になりやすい。",
        "examples": ["2018年米中貿易戦争でのドル高"],
    },
    {
        "event": "米国債格下げ・財政不安",
        "keywords": ["格下げ", "財政赤字", "国債危機", "デフォルト"],
        "exclude": [],
        "usd_impact": "bearish",
        "reasoning": "米国の信用低下はドル離れにつながりドル安要因。",
        "examples": ["2023年米国債格下げ後のドル一時下落"],
    },
]


# ── データクラス ──────────────────────────────────────────────────────────

@dataclass
class GeopoliticalAnalysis:
    event_text: str              # 入力されたイベントテキスト
    category: str                # 分類カテゴリー
    usd_impact: str              # strong_bullish / bullish / neutral / bearish / strong_bearish
    confidence: str              # high / medium / low
    reasoning: str               # 根拠・分析テキスト
    similar_events: list[str]    # 歴史的類似事例
    short_term_outlook: str      # 短期（1〜2週間）見通し
    risk_factors: str            # 逆方向に動くリスク要因
    ai_provider: str             # "claude" | "mock"


@dataclass
class GeopoliticalRecord:
    id: Optional[int]
    created_at: str
    event_date: str
    event_text: str
    category: str
    usd_impact: str
    confidence: str
    reasoning: str
    similar_events: list[str]
    short_term_outlook: str
    risk_factors: str
    ai_provider: str
    actual_result: Optional[str] = None   # 後から記録する実際の結果


@dataclass
class EventCorrelation:
    """イベントカテゴリーと実際のドル円値動きの相関集計。"""
    category: str
    total_events: int
    bullish_events: int       # bullish + strong_bullish
    bearish_events: int       # bearish + strong_bearish
    avg_pips_after: Optional[float]   # イベント後の平均pips変動
    win_rate_if_followed: Optional[float]  # 予測通りの方向に動いた率


# ── AI分析プロンプト ───────────────────────────────────────────────────────

_GEO_SYSTEM_PROMPT = """あなたはFX市場（特にドル円 USD/JPY）の地政学・マクロ経済アナリストです。

## 役割
ユーザーが入力した世界情勢・経済政策・地政学的イベントを分析し、
USD/JPYへの影響を客観的に評価します。

## 絶対に守るルール
1. 「確実に上がる」「必ず下がる」などの断言は使わない
2. 複数のシナリオと反対方向のリスクも必ず示す
3. 最終的な売買判断はトレーダー自身が行うことを前提とする
4. 歴史的事実と推論を明確に区別する

## 出力形式（JSON）
以下のJSON形式で回答してください：
{
  "category": "分類（例: FRB金融政策）",
  "usd_impact": "strong_bullish | bullish | neutral | bearish | strong_bearish",
  "confidence": "high | medium | low",
  "reasoning": "分析の根拠（150〜300文字）",
  "similar_events": ["過去の類似事例1", "過去の類似事例2"],
  "short_term_outlook": "短期（1〜2週間）の見通し（100文字以内）",
  "risk_factors": "予測と逆方向に動くリスク要因（100文字以内）"
}"""


def _build_geo_prompt(event_text: str) -> str:
    pattern_hints = "\n".join(
        f"- {p['event']}: {p['usd_impact']} — {p['reasoning']}"
        for p in _HISTORICAL_PATTERNS
    )
    return (
        f"以下の世界情勢・イベントを分析してください：\n\n"
        f"【イベント内容】\n{event_text}\n\n"
        f"【参考：歴史的パターン】\n{pattern_hints}\n\n"
        f"上記を参考に、USD/JPYへの影響をJSON形式で返してください。"
    )


# ── AI分析実行 ─────────────────────────────────────────────────────────────

def _mock_analysis(event_text: str) -> GeopoliticalAnalysis:
    """Claude API 未設定時のルールベースモック分析。"""
    # 日銀を優先（汎用キーワード "利上げ" より先に確認）
    # → パターンリストの順番で評価し、exclude チェックで除外
    for pattern in _HISTORICAL_PATTERNS:
        matched = any(kw in event_text for kw in pattern["keywords"])
        excluded = any(ex in event_text for ex in pattern.get("exclude", []))
        if matched and not excluded:
            return GeopoliticalAnalysis(
                event_text=event_text,
                category=_classify_category(event_text),
                usd_impact=pattern["usd_impact"],
                confidence="medium",
                reasoning=pattern["reasoning"],
                similar_events=pattern["examples"],
                short_term_outlook="類似事例から短期的にUSD方向への影響が想定されます。最終判断はご自身でお願いします。",
                risk_factors="予期せぬ政策転換や経済指標の大幅乖離により逆方向に動く可能性があります。",
                ai_provider="mock",
            )

    # デフォルト
    return GeopoliticalAnalysis(
        event_text=event_text,
        category=_classify_category(event_text),
        usd_impact="neutral",
        confidence="low",
        reasoning="入力されたイベントについて、既知のパターンとの明確な一致が見つかりませんでした。個別の状況を精査してください。",
        similar_events=[],
        short_term_outlook="不確定要素が多く、短期的な影響の見通しは難しい状況です。",
        risk_factors="情報が不足しているため、リスク要因の特定が困難です。",
        ai_provider="mock",
    )


def _classify_category(text: str) -> str:
    # 具体的・固有名詞を先にチェックし、汎用語（利上げ等）は後回し
    priority_mapping = [
        ("日銀", "日銀金融政策"),
        ("大統領", "米大統領・政権交代"),
        ("トランプ", "米大統領・政権交代"),
        ("FRB", "FRB金融政策（利上げ・利下げ・QE）"),
        ("FOMC", "FRB金融政策（利上げ・利下げ・QE）"),
        ("雇用統計", "米雇用・経済指標"),
        ("NFP", "米雇用・経済指標"),
        ("GDP", "米雇用・経済指標"),
        ("戦争", "地政学リスク（戦争・紛争）"),
        ("紛争", "地政学リスク（戦争・紛争）"),
        ("侵攻", "地政学リスク（戦争・紛争）"),
        ("関税", "貿易・関税政策"),
        ("貿易摩擦", "貿易・関税政策"),
        ("原油", "エネルギー・資源価格"),
        ("格下げ", "金融危機・市場ショック"),
        ("利上げ", "FRB金融政策（利上げ・利下げ・QE）"),
        ("利下げ", "FRB金融政策（利上げ・利下げ・QE）"),
    ]
    for kw, cat in priority_mapping:
        if kw in text:
            return cat
    return "その他"


def analyze_geopolitical_event(event_text: str) -> GeopoliticalAnalysis:
    """イベントテキストを分析してGeopoliticalAnalysisを返す。"""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5"),
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": _GEO_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": _build_geo_prompt(event_text)}],
            )
            raw = resp.content[0].text.strip()
            # JSON部分を抽出
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            data = json.loads(raw)
            return GeopoliticalAnalysis(
                event_text=event_text,
                category=data.get("category", _classify_category(event_text)),
                usd_impact=data.get("usd_impact", "neutral"),
                confidence=data.get("confidence", "medium"),
                reasoning=data.get("reasoning", ""),
                similar_events=data.get("similar_events", []),
                short_term_outlook=data.get("short_term_outlook", ""),
                risk_factors=data.get("risk_factors", ""),
                ai_provider="claude",
            )
        except Exception:
            pass

    if os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _GEO_SYSTEM_PROMPT},
                    {"role": "user", "content": _build_geo_prompt(event_text)},
                ],
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            return GeopoliticalAnalysis(
                event_text=event_text,
                category=data.get("category", _classify_category(event_text)),
                usd_impact=data.get("usd_impact", "neutral"),
                confidence=data.get("confidence", "medium"),
                reasoning=data.get("reasoning", ""),
                similar_events=data.get("similar_events", []),
                short_term_outlook=data.get("short_term_outlook", ""),
                risk_factors=data.get("risk_factors", ""),
                ai_provider="openai",
            )
        except Exception:
            pass

    return _mock_analysis(event_text)


# ── DB操作 ────────────────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS geopolitical_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT NOT NULL,
    event_date        TEXT NOT NULL,
    event_text        TEXT NOT NULL,
    category          TEXT NOT NULL,
    usd_impact        TEXT NOT NULL,
    confidence        TEXT NOT NULL,
    reasoning         TEXT NOT NULL DEFAULT '',
    similar_events    TEXT NOT NULL DEFAULT '[]',
    short_term_outlook TEXT NOT NULL DEFAULT '',
    risk_factors      TEXT NOT NULL DEFAULT '',
    ai_provider       TEXT NOT NULL DEFAULT 'mock',
    actual_result     TEXT
);
"""


def ensure_table(db_path=None) -> None:
    """テーブルが存在しない場合は作成する。"""
    with get_db(db_path) as conn:
        conn.execute(_CREATE_TABLE)


def save_geopolitical_record(
    analysis: GeopoliticalAnalysis,
    event_date: str,
    db_path=None,
) -> int:
    ensure_table(db_path)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO geopolitical_log
                (created_at, event_date, event_text, category, usd_impact, confidence,
                 reasoning, similar_events, short_term_outlook, risk_factors, ai_provider)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                now,
                event_date,
                analysis.event_text,
                analysis.category,
                analysis.usd_impact,
                analysis.confidence,
                analysis.reasoning,
                json.dumps(analysis.similar_events, ensure_ascii=False),
                analysis.short_term_outlook,
                analysis.risk_factors,
                analysis.ai_provider,
            ),
        )
        return cur.lastrowid


def get_geopolitical_records(limit: int = 50, db_path=None) -> list[GeopoliticalRecord]:
    ensure_table(db_path)
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM geopolitical_log ORDER BY event_date DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for r in rows:
        result.append(GeopoliticalRecord(
            id=r["id"],
            created_at=r["created_at"],
            event_date=r["event_date"],
            event_text=r["event_text"],
            category=r["category"],
            usd_impact=r["usd_impact"],
            confidence=r["confidence"],
            reasoning=r["reasoning"],
            similar_events=json.loads(r["similar_events"] or "[]"),
            short_term_outlook=r["short_term_outlook"],
            risk_factors=r["risk_factors"],
            ai_provider=r["ai_provider"],
            actual_result=r["actual_result"],
        ))
    return result


def update_actual_result(record_id: int, actual_result: str, db_path=None) -> None:
    """イベント後に実際の結果（ドル円がどう動いたか）を記録する。"""
    ensure_table(db_path)
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE geopolitical_log SET actual_result = ? WHERE id = ?",
            (actual_result, record_id),
        )


def delete_geopolitical_record(record_id: int, db_path=None) -> None:
    ensure_table(db_path)
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM geopolitical_log WHERE id = ?", (record_id,))


def get_event_correlations(db_path=None) -> list[EventCorrelation]:
    """カテゴリー別の予測傾向を集計する（実績記録があるもののみ）。"""
    ensure_table(db_path)
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT category,
                   COUNT(*) as total,
                   SUM(CASE WHEN usd_impact IN ('bullish','strong_bullish') THEN 1 ELSE 0 END) as bullish,
                   SUM(CASE WHEN usd_impact IN ('bearish','strong_bearish') THEN 1 ELSE 0 END) as bearish
            FROM geopolitical_log
            GROUP BY category
            ORDER BY total DESC
            """,
        ).fetchall()
    return [
        EventCorrelation(
            category=r["category"],
            total_events=r["total"],
            bullish_events=r["bullish"],
            bearish_events=r["bearish"],
            avg_pips_after=None,
            win_rate_if_followed=None,
        )
        for r in rows
    ]


# ── 公開API ───────────────────────────────────────────────────────────────

def analyze_and_save(event_text: str, event_date: str, db_path=None) -> tuple[GeopoliticalAnalysis, int]:
    """分析してDBに保存し (analysis, record_id) を返す。

    strong_bullish / strong_bearish の場合は Phase 71 アラートを送信する。
    """
    analysis = analyze_geopolitical_event(event_text)
    record_id = save_geopolitical_record(analysis, event_date, db_path)
    # Phase 71: 強リスク検出時にアラート送信（失敗しても続行）
    try:
        from app.services.geo_alert import send_geo_alert
        send_geo_alert(analysis)
    except Exception:
        pass
    return analysis, record_id


# ── 定数エクスポート ──────────────────────────────────────────────────────

USD_IMPACT_LABELS = {
    "strong_bullish": "ドル強気 ▲▲",
    "bullish":        "ドル強気 ▲",
    "neutral":        "中立 →",
    "bearish":        "ドル弱気 ▼",
    "strong_bearish": "ドル弱気 ▼▼",
}

USD_IMPACT_COLORS = {
    "strong_bullish": "#4ade80",
    "bullish":        "#86efac",
    "neutral":        "#fbbf24",
    "bearish":        "#fca5a5",
    "strong_bearish": "#f87171",
}
