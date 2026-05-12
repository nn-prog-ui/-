"""AIコメント生成モジュール

現在はモック実装（ルール結果から自動文章生成）。
将来はOpenAI API / Claude APIへの切り替えが可能な設計。

重要制約：
- AIコメントは売買判定を変更してはいけない
- AIは補足説明のみを行う
- 禁止表現（「必ず」「絶対」「全力」等）は使わない
"""
from __future__ import annotations

from app.strategy.rules import SignalResult
from app.strategy.risk import TradeSetup

# 禁止ワードリスト（安全チェック用）
_FORBIDDEN_WORDS = [
    "絶対に勝てる", "必ず上がる", "必ず下がる", "今すぐ全力",
    "損切り不要", "ナンピン推奨", "マーチンゲール推奨",
    "儲かる", "勝率100%", "放置で稼げる",
]


def generate_commentary(
    signal_result: SignalResult,
    setup: TradeSetup | None = None,
) -> str:
    """ルール判定結果からAIコメントを生成する（モック実装）。

    将来はこの関数内部をOpenAI/Claude API呼び出しに切り替える。
    ただし、signalの変更は行わず、補足説明のみを返すこと。
    """
    comment = _generate_mock_commentary(signal_result, setup)
    comment = _sanitize_commentary(comment)
    return comment


def _generate_mock_commentary(
    result: SignalResult,
    setup: TradeSetup | None,
) -> str:
    """ルール結果から文章コメントを生成する。"""
    parts: list[str] = []

    # データ不足時
    if not result.data_sufficient:
        return "データが不足しているため、判定を行えません。CSVファイルを確認してください。"

    # トレンド状況
    if result.daily_trend == "上昇" and result.h4_trend == "上昇":
        parts.append("日足・4時間足ともに上昇方向のMAの並びとなっています。")
    elif result.daily_trend == "下降" and result.h4_trend == "下降":
        parts.append("日足・4時間足ともに下降方向のMAの並びとなっています。")
    elif result.daily_trend != result.h4_trend:
        parts.append(
            f"日足は{result.daily_trend}方向ですが、4時間足は{result.h4_trend}方向です。"
            "上位足と下位足のトレンドが一致していません。"
        )

    # 1時間足の状態
    if result.h1_status == "高値突破":
        parts.append("1時間足では直近高値を上抜けており、短期的な上方ブレイクアウトが確認できます。")
    elif result.h1_status == "安値割れ":
        parts.append("1時間足では直近安値を下抜けており、短期的な下方ブレイクアウトが確認できます。")
    else:
        parts.append("1時間足ではまだブレイクアウトが確認できず、レンジ内での推移です。")

    # RSI
    if result.rsi is not None:
        if result.rsi >= 70:
            parts.append(f"RSIは{result.rsi}と高く、買われすぎの状態に近いため注意が必要です。")
        elif result.rsi <= 30:
            parts.append(f"RSIは{result.rsi}と低く、売られすぎの状態に近いため注意が必要です。")
        else:
            parts.append(f"RSIは{result.rsi}と適正範囲内にあります。")

    # ATR警戒
    if result.atr_abnormal:
        parts.append("現在のATR（ボラティリティ）が通常より高いため、大きな値動きに注意が必要です。")

    # 重要指標警戒
    if result.skip_reasons and any("経済指標" in r for r in result.skip_reasons):
        parts.append("重要な経済指標の発表前後60分に該当するため、ルール上は見送りが適切です。")

    # 判定のサマリー
    if result.signal == "BUY":
        parts.append("現在のルールでは買い候補の条件が揃っています。ただし、最終判断は必ず人間が行ってください。")
        if setup and setup.risk_reward:
            parts.append(f"リスクリワードは約{setup.risk_reward}です。損切り・利確価格を必ず確認した上で判断してください。")
    elif result.signal == "SELL":
        parts.append("現在のルールでは売り候補の条件が揃っています。ただし、最終判断は必ず人間が行ってください。")
        if setup and setup.risk_reward:
            parts.append(f"リスクリワードは約{setup.risk_reward}です。損切り・利確価格を必ず確認した上で判断してください。")
    else:
        if result.skip_reasons:
            parts.append(f"見送り理由：{result.skip_reasons[0]}")
        parts.append("現時点ではルール上の条件が揃っていないため、見送りが妥当です。")

    return "".join(parts)


def _sanitize_commentary(comment: str) -> str:
    """禁止表現が含まれていないかチェックし、含まれていれば削除する。"""
    for word in _FORBIDDEN_WORDS:
        if word in comment:
            comment = comment.replace(word, "（表現を削除しました）")
    return comment


# 将来のAPI切り替え用インターフェース
class CommentaryAdapter:
    """AIコメント生成アダプターの基底クラス。将来のAPI実装はこれを継承する。"""

    def generate(self, signal_result: SignalResult, setup: TradeSetup | None = None) -> str:
        raise NotImplementedError


class MockCommentaryAdapter(CommentaryAdapter):
    def generate(self, signal_result: SignalResult, setup: TradeSetup | None = None) -> str:
        return generate_commentary(signal_result, setup)
