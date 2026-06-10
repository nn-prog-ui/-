"""音声AIアシスタントサービス（Phase 90）

ユーザーの音声質問に対して、現在のFX分析データをもとに
音声読み上げに適した短い日本語で回答する。

ANTHROPIC_API_KEY が設定されている場合はClaude APIを使用。
未設定の場合はルールベースの回答にフォールバック。

重要制約:
- 売買注文の指示は絶対にしない
- 最終判断は人間が行うことを必ず明示
- 禁止表現（「必ず」「絶対」等）は使わない
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# 禁止ワード（ai_commentary.py と同じ制約）
_FORBIDDEN_WORDS = [
    "絶対に勝てる", "必ず上がる", "必ず下がる", "今すぐ全力",
    "損切り不要", "ナンピン推奨", "マーチンゲール推奨",
    "儲かる", "勝率100%", "放置で稼げる",
]

_SYSTEM_PROMPT = """あなたはFX市場監視システムの音声アシスタントです。

## 役割
現在の市場分析データを参照しながら、ユーザーの音声質問に簡潔に答えます。

## 厳守事項
1. 最終的な売買判断は必ず人間が行います。あなたは情報提供のみです
2. 「今すぐ買え」「売れ」などの具体的な注文指示は絶対にしないでください
3. 以下の表現は絶対に使わないでください：
   「絶対に勝てる」「必ず上がる」「今すぐ全力」「損切り不要」「儲かる」「勝率100%」

## 回答スタイル
- 音声読み上げに適した自然な日本語（です・ます調）
- 80〜180文字程度の簡潔な回答
- 数値は読みやすく（例: 149.850 → 「149円85銭」）
- 回答のみ返してください（前置き不要）
"""


def _build_context(symbol: str, analysis: dict | None) -> str:
    """現在の分析データをプロンプト文字列に変換する。"""
    if not analysis:
        return f"現在、{symbol}の分析データはキャッシュにありません。"

    signal_map = {"BUY": "買い候補", "SELL": "売り候補", "SKIP": "見送り"}
    signal = analysis.get("signal", "NONE")
    lines = [
        f"【現在の{symbol}分析データ】",
        f"判定: {signal_map.get(signal, 'データなし')}",
    ]

    score = analysis.get("score")
    if score is not None:
        lines.append(f"スコア: {score}点")

    price = analysis.get("current_price")
    if price is not None:
        lines.append(f"現在価格: {price:.3f}")

    for key, label in [
        ("daily_trend", "日足トレンド"),
        ("h4_trend", "4時間足トレンド"),
        ("h1_status", "1時間足状態"),
        ("atr_status", "ATR状態"),
    ]:
        val = analysis.get(key)
        if val:
            lines.append(f"{label}: {val}")

    rsi = analysis.get("rsi")
    if rsi is not None:
        lines.append(f"RSI: {rsi:.1f}")

    ai_comment = analysis.get("ai_comment")
    if ai_comment:
        lines.append(f"AIコメント: {ai_comment[:80]}...")

    return "\n".join(lines)


def _rule_based_response(question: str, symbol: str, analysis: dict | None) -> str:
    """APIキーなしで使えるルールベースの回答（フォールバック）。"""
    if not analysis:
        return (
            f"現在{symbol}の分析データがありません。"
            "メイン画面で分析を実行してから、もう一度お試しください。"
        )

    signal_map = {"BUY": "買い候補", "SELL": "売り候補", "SKIP": "見送り"}
    signal = analysis.get("signal", "NONE")
    label = signal_map.get(signal, "データなし")
    score = analysis.get("score", "N/A")
    daily = analysis.get("daily_trend", "不明")
    h4 = analysis.get("h4_trend", "不明")
    h1 = analysis.get("h1_status", "不明")
    price = analysis.get("current_price")
    rsi = analysis.get("rsi")

    q = question

    # 判定・状況
    if any(w in q for w in ["判定", "シグナル", "どう", "状況", "教えて", "分析"]):
        resp = f"{symbol}の現在の判定は{label}、スコアは{score}点です。"
        resp += f"日足は{daily}、4時間足は{h4}トレンドです。"
        resp += "最終判断は必ずご自身で行ってください。"
        return resp

    # スコア
    if any(w in q for w in ["スコア", "点数", "score"]):
        return (
            f"{symbol}の現在のスコアは{score}点です。"
            "7点以上で買い候補、マイナス7点以下で売り候補が目安です。"
        )

    # 価格
    if any(w in q for w in ["価格", "レート", "いくら", "円", "値段"]):
        if price:
            return f"{symbol}の現在価格は{price:.3f}です。"
        return f"{symbol}の価格データが取得できていません。"

    # 日足
    if any(w in q for w in ["日足", "デイリー", "長期"]):
        return f"{symbol}の日足トレンドは{daily}方向です。"

    # 4時間足
    if any(w in q for w in ["4時間", "4h", "中期"]):
        return f"{symbol}の4時間足トレンドは{h4}方向です。"

    # 1時間足
    if any(w in q for w in ["1時間", "1h", "短期"]):
        return f"{symbol}の1時間足の状態は{h1}です。"

    # RSI
    if any(w in q for w in ["rsi", "RSI", "強弱", "過熱"]):
        if rsi is not None:
            state = "買われすぎ" if rsi >= 70 else ("売られすぎ" if rsi <= 30 else "適正範囲")
            return f"{symbol}のRSIは{rsi:.0f}で、{state}の水準です。"
        return "RSIデータが取得できていません。"

    # エントリー・注文
    if any(w in q for w in ["エントリー", "買い", "売り", "入る", "注文", "いい", "すべき"]):
        return (
            f"現在の判定は{label}（スコア{score}点）です。"
            "ただし売買の最終判断は必ずご自身で行ってください。"
            "このシステムは参考情報の提供のみです。"
        )

    # デフォルト
    price_str = f"{price:.3f}" if price else "N/A"
    return (
        f"{symbol}は現在{label}（スコア{score}点）、価格{price_str}です。"
        f"日足{daily}・4H{h4}・1H{h1}の状況です。"
    )


async def get_voice_response(
    question: str,
    symbol: str,
    analysis: dict | None,
) -> str:
    """ユーザーの質問に音声向きの回答を返す。

    Args:
        question: ユーザーの質問文
        symbol: 対象通貨ペア（例: "USD/JPY"）
        analysis: 現在の分析キャッシュデータ（_signal_cache[symbol]）

    Returns:
        音声読み上げ向きの日本語テキスト（100〜200文字程度）
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.debug("ANTHROPIC_API_KEY 未設定 → ルールベース回答")
        return _rule_based_response(question, symbol, analysis)

    try:
        import anthropic  # 遅延import

        client = anthropic.Anthropic()
        model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")

        context = _build_context(symbol, analysis)
        user_prompt = f"{context}\n\n【ユーザーの質問】{question}"

        response = client.messages.create(
            model=model,
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        answer = response.content[0].text.strip()

        # 禁止ワードチェック
        for word in _FORBIDDEN_WORDS:
            if word in answer:
                answer = answer.replace(word, "")

        return answer or _rule_based_response(question, symbol, analysis)

    except Exception as exc:
        logger.warning("音声AI APIエラー（%s）→ ルールベース回答にフォールバック", exc)
        return _rule_based_response(question, symbol, analysis)
