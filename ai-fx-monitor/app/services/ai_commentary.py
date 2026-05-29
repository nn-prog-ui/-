"""AIコメント生成モジュール

ANTHROPIC_API_KEY が設定されている場合は Claude API を使用し、
未設定の場合はモック実装（ルール結果から自動文章生成）にフォールバックする。

重要制約：
- AIコメントは売買判定を変更してはいけない
- AIは補足説明のみを行う
- 禁止表現（「必ず」「絶対」「全力」等）は使わない
"""
from __future__ import annotations

import os

from app.indicators.candlestick_patterns import CandlePattern
from app.strategy.rules import SignalResult
from app.strategy.risk import TradeSetup

# 禁止ワードリスト（安全チェック用）
_FORBIDDEN_WORDS = [
    "絶対に勝てる", "必ず上がる", "必ず下がる", "今すぐ全力",
    "損切り不要", "ナンピン推奨", "マーチンゲール推奨",
    "儲かる", "勝率100%", "放置で稼げる",
]

# Claude API用システムプロンプト（安全制約を含む）
# cache_control を付与するが、Haiku 4.5 の最小キャッシュサイズは 4096 トークンのため
# 短いシステムプロンプトではキャッシュは動作しない。将来的に拡張した場合に有効になる。
_SYSTEM_PROMPT = """あなたはFX市場分析ツールの補足コメント生成アシスタントです。

## 役割
ルールベースの売買判定システムが出力した分析結果に対して、100〜200文字程度の補足コメントを日本語で生成します。

## 絶対に守るルール
1. 与えられた売買判定（BUY/SELL/SKIP）を変更してはいけません
2. 補足説明のみを行い、判定を上書きする表現は使わないでください
3. 最終判断は必ず人間が行うことを前提とした表現にしてください
4. 以下の表現は絶対に使わないでください：
   - 「絶対に勝てる」「必ず上がる」「必ず下がる」
   - 「今すぐ全力」「損切り不要」
   - 「ナンピン推奨」「マーチンゲール推奨」
   - 「儲かる」「勝率100%」「放置で稼げる」

## 出力形式
コメントのみを返してください。前置き・説明・改行は不要です。"""


def generate_commentary(
    signal_result: SignalResult,
    setup: TradeSetup | None = None,
    historical_stats: dict | None = None,
    candlestick_patterns: list[CandlePattern] | None = None,
) -> str:
    """ルール判定結果からAIコメントを生成する。

    優先順位: ANTHROPIC_API_KEY(Claude) > OPENAI_API_KEY(OpenAI) > モック
    signalの変更は行わず、補足説明のみを返すこと。
    """
    patterns = candlestick_patterns or []
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ClaudeCommentaryAdapter().generate(signal_result, setup, historical_stats,
                                                  candlestick_patterns=patterns)
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAICommentaryAdapter().generate(signal_result, setup, historical_stats,
                                                  candlestick_patterns=patterns)
    comment = _generate_mock_commentary(signal_result, setup, historical_stats, patterns)
    return _sanitize_commentary(comment)


def _generate_mock_commentary(
    result: SignalResult,
    setup: TradeSetup | None,
    historical_stats: dict | None = None,
    candlestick_patterns: list[CandlePattern] | None = None,
) -> str:
    """ルール結果から文章コメントを生成する（モック実装）。"""
    parts: list[str] = []
    patterns = candlestick_patterns or []

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

    # Phase 86: ローソク足パターン言及
    if patterns:
        bullish_pats = [p for p in patterns if p.direction == "bullish"]
        bearish_pats = [p for p in patterns if p.direction == "bearish"]
        strong_pats  = [p for p in patterns if p.strength >= 3]

        if strong_pats:
            names = "・".join(p.name for p in strong_pats[:2])
            dirs  = strong_pats[0].direction
            if dirs == "bullish":
                parts.append(f"直近のローソク足では強い強気パターン（{names}）が検出されており、上昇圧力の存在を示しています。")
            else:
                parts.append(f"直近のローソク足では強い弱気パターン（{names}）が検出されており、下落圧力の存在を示しています。")
        elif bullish_pats and not bearish_pats:
            names = "・".join(p.name for p in bullish_pats[:2])
            parts.append(f"直近のローソク足では強気パターン（{names}）が確認されています。")
        elif bearish_pats and not bullish_pats:
            names = "・".join(p.name for p in bearish_pats[:2])
            parts.append(f"直近のローソク足では弱気パターン（{names}）が確認されています。")
        elif bullish_pats and bearish_pats:
            parts.append("直近のローソク足では強気・弱気両方のパターンが混在しており、方向感が定まっていません。")

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

    # Phase 20: 過去トレードからの学習データを補足
    if historical_stats and result.signal in ("BUY", "SELL"):
        overall_closed = historical_stats.get("overall_closed", 0)
        overall_win_rate = historical_stats.get("overall_win_rate")
        pattern_closed = historical_stats.get("pattern_closed", 0)
        pattern_win_rate = historical_stats.get("pattern_win_rate")

        if pattern_closed >= 3 and pattern_win_rate is not None:
            parts.append(
                f"参考：同パターン（日足{result.daily_trend}・4H{result.h4_trend}）"
                f"の過去成績は{pattern_closed}件中{pattern_win_rate:.0f}%勝率です。"
            )
        elif overall_closed >= 3 and overall_win_rate is not None:
            signal_label = "買い" if result.signal == "BUY" else "売り"
            parts.append(
                f"参考：過去の{signal_label}取引{overall_closed}件の勝率は"
                f"{overall_win_rate:.0f}%です。"
            )

    return "".join(parts)


def _build_signal_prompt(
    result: SignalResult,
    setup: TradeSetup | None,
    historical_stats: dict | None = None,
    candlestick_patterns: list[CandlePattern] | None = None,
) -> str:
    """Claude API向けのユーザープロンプトを構築する。"""
    lines = [
        f"【判定】{result.signal}",
        f"【日足トレンド】{result.daily_trend}",
        f"【4時間足トレンド】{result.h4_trend}",
        f"【1時間足状態】{result.h1_status}",
    ]
    if result.rsi is not None:
        lines.append(f"【RSI】{result.rsi:.1f}")
    lines.append(f"【ATR異常】{'あり' if result.atr_abnormal else 'なし'}")
    if not result.data_sufficient:
        lines.append("【データ状態】不足")
    if result.skip_reasons:
        lines.append(f"【見送り理由】{' / '.join(result.skip_reasons)}")
    if setup and setup.is_valid:
        if setup.entry_price:
            lines.append(f"【エントリー価格】{setup.entry_price:.3f}")
        if setup.stop_loss:
            lines.append(f"【損切り価格】{setup.stop_loss:.3f}")
        if setup.take_profit:
            lines.append(f"【利確価格】{setup.take_profit:.3f}")
        if setup.risk_reward:
            lines.append(f"【リスクリワード】{setup.risk_reward:.2f}")

    # Phase 20: 過去トレードの学習データを追加
    if historical_stats and result.signal in ("BUY", "SELL"):
        overall_closed = historical_stats.get("overall_closed", 0)
        overall_win_rate = historical_stats.get("overall_win_rate")
        pattern_closed = historical_stats.get("pattern_closed", 0)
        pattern_win_rate = historical_stats.get("pattern_win_rate")
        recent = historical_stats.get("recent_outcomes", [])

        if overall_closed > 0:
            signal_label = "買い" if result.signal == "BUY" else "売り"
            wr_str = f"{overall_win_rate:.0f}%" if overall_win_rate is not None else "N/A"
            lines.append(f"【過去{signal_label}取引数】{overall_closed}件（勝率{wr_str}）")
        if pattern_closed > 0:
            p_wr_str = f"{pattern_win_rate:.0f}%" if pattern_win_rate is not None else "N/A"
            lines.append(
                f"【同パターン成績（日足{result.daily_trend}・4H{result.h4_trend}）】"
                f"{pattern_closed}件（勝率{p_wr_str}）"
            )
        if recent:
            lines.append(f"【直近結果】{' / '.join(recent)}")

    # Phase 86: ローソク足パターン情報
    patterns = candlestick_patterns or []
    if patterns:
        pat_parts = []
        for p in patterns[:4]:  # 最大4パターン
            dir_label = {"bullish": "強気", "bearish": "弱気", "neutral": "中立"}.get(p.direction, p.direction)
            pat_parts.append(f"{p.name}（{p.name_en}・{dir_label}・強度{p.strength}）")
        lines.append(f"【直近ローソク足パターン】{' / '.join(pat_parts)}")

    lines.append("\n上記の市場状況について補足コメントを生成してください。")
    return "\n".join(lines)


def _sanitize_commentary(comment: str) -> str:
    """禁止表現が含まれていないかチェックし、含まれていれば削除する。"""
    for word in _FORBIDDEN_WORDS:
        if word in comment:
            comment = comment.replace(word, "（表現を削除しました）")
    return comment


# AIコメント生成アダプター

class CommentaryAdapter:
    """AIコメント生成アダプターの基底クラス。"""

    def generate(
        self,
        signal_result: SignalResult,
        setup: TradeSetup | None = None,
        historical_stats: dict | None = None,
        candlestick_patterns: list[CandlePattern] | None = None,
    ) -> str:
        raise NotImplementedError


class MockCommentaryAdapter(CommentaryAdapter):
    """モック実装アダプター（API不要）。"""

    def generate(
        self,
        signal_result: SignalResult,
        setup: TradeSetup | None = None,
        historical_stats: dict | None = None,
        candlestick_patterns: list[CandlePattern] | None = None,
    ) -> str:
        comment = _generate_mock_commentary(signal_result, setup, historical_stats,
                                            candlestick_patterns=candlestick_patterns)
        return _sanitize_commentary(comment)


class OpenAICommentaryAdapter(CommentaryAdapter):
    """OpenAI APIを使ったコメント生成アダプター。

    OPENAI_API_KEY 環境変数が必要。
    モデルは OPENAI_MODEL 環境変数で変更可能（デフォルト: gpt-4o-mini）。
    API呼び出し失敗時は MockCommentaryAdapter にフォールバックする。
    """

    def __init__(self) -> None:
        import openai  # 遅延importでopenaiが未インストールでも他機能は動作する
        self._client = openai.OpenAI()
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def generate(
        self,
        signal_result: SignalResult,
        setup: TradeSetup | None = None,
        historical_stats: dict | None = None,
        candlestick_patterns: list[CandlePattern] | None = None,
    ) -> str:
        if not signal_result.data_sufficient:
            return "データが不足しているため、判定を行えません。CSVファイルを確認してください。"

        try:
            user_prompt = _build_signal_prompt(signal_result, setup, historical_stats,
                                               candlestick_patterns=candlestick_patterns)
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=512,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            comment = response.choices[0].message.content.strip()
            return _sanitize_commentary(comment)
        except Exception:
            fallback = MockCommentaryAdapter()
            return fallback.generate(signal_result, setup, historical_stats,
                                     candlestick_patterns=candlestick_patterns)


class ClaudeCommentaryAdapter(CommentaryAdapter):
    """Anthropic Claude APIを使ったコメント生成アダプター。

    ANTHROPIC_API_KEY 環境変数が必要。
    モデルは CLAUDE_MODEL 環境変数で変更可能（デフォルト: claude-haiku-4-5）。
    API呼び出し失敗時は MockCommentaryAdapter にフォールバックする。
    """

    def __init__(self) -> None:
        import anthropic  # 遅延importでanthropicが未インストールでも他機能は動作する
        self._client = anthropic.Anthropic()
        self._model = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")

    def generate(
        self,
        signal_result: SignalResult,
        setup: TradeSetup | None = None,
        historical_stats: dict | None = None,
        candlestick_patterns: list[CandlePattern] | None = None,
    ) -> str:
        if not signal_result.data_sufficient:
            return "データが不足しているため、判定を行えません。CSVファイルを確認してください。"

        try:
            user_prompt = _build_signal_prompt(signal_result, setup, historical_stats,
                                               candlestick_patterns=candlestick_patterns)
            response = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        # プロンプトキャッシュを有効化（システムプロンプトは毎回同じため）
                        # Haiku 4.5 の最小キャッシュサイズ(4096 tokens)には満たないが
                        # システムプロンプト拡張時に自動的に有効になる
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
            comment = response.content[0].text.strip()
            return _sanitize_commentary(comment)
        except Exception:
            # API呼び出し失敗時はモックにフォールバック
            fallback = MockCommentaryAdapter()
            return fallback.generate(signal_result, setup, historical_stats,
                                     candlestick_patterns=candlestick_patterns)
