"""ローソク足パターン検出モジュール（Phase 85）

単体・複合ローソク足パターンを検出して、シグナル補足情報として提供する。
注文の発生・自動取引とは無関係。あくまで「傾向」の参考情報。

検出パターン一覧:
  【単体】下影陽線, 首吊り線, 流れ星, 上影陰線, 大陽線, 大陰線
  【2本】 抱きの一本立ち(強気), 陰の抱き(弱気), 二本たくり線
  【3本】 三川明けの明星, 三川宵の明星, 赤三兵, 黒三兵
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class CandlePattern:
    """検出されたローソク足パターン。"""
    name: str           # 日本語名（例: "下影陽線"）
    name_en: str        # 英語名（例: "Hammer"）
    direction: str      # "bullish" / "bearish" / "neutral"
    strength: int       # 1（弱）〜 3（強）
    description: str    # 簡単な説明


# ── ヘルパー関数 ─────────────────────────────────────────────────────────────

def _body(o: float, c: float) -> float:
    """実体の大きさ（絶対値）。"""
    return abs(c - o)


def _upper_shadow(o: float, h: float, c: float) -> float:
    """上ひげの長さ。"""
    return h - max(o, c)


def _lower_shadow(o: float, l: float, c: float) -> float:
    """下ひげの長さ。"""
    return min(o, c) - l


def _is_bullish(o: float, c: float) -> bool:
    return c > o


def _is_bearish(o: float, c: float) -> bool:
    return c < o


def _candle_range(h: float, l: float) -> float:
    return h - l


# ── 単体パターン ─────────────────────────────────────────────────────────────

def _detect_single(o: float, h: float, l: float, c: float,
                   prev_trend: str = "") -> list[CandlePattern]:
    """直近1本のローソク足からパターンを検出する。"""
    patterns: list[CandlePattern] = []
    body = _body(o, c)
    upper = _upper_shadow(o, h, c)
    lower = _lower_shadow(o, l, c)
    total = _candle_range(h, l)

    if total < 1e-10:
        return patterns

    # ── 下影陽線（ハンマー）──────────────────────────────────────
    # 条件: 下ひげ≥実体×2、上ひげ≤実体×0.5、陽線
    if (body > 0
            and lower >= body * 2.0
            and upper <= body * 0.5
            and _is_bullish(o, c)):
        patterns.append(CandlePattern(
            name="下影陽線",
            name_en="Hammer",
            direction="bullish",
            strength=2,
            description="長い下ひげが売り圧力の吸収を示す。下落トレンド末期に出やすい反転サイン。",
        ))

    # ── 首吊り線（ハンギングマン）────────────────────────────────
    # 形はハンマーと同じだが上昇トレンド末期に出ると弱気サイン
    elif (body > 0
            and lower >= body * 2.0
            and upper <= body * 0.5
            and _is_bearish(o, c)
            and prev_trend in ("上昇", "bullish")):
        patterns.append(CandlePattern(
            name="首吊り線",
            name_en="Hanging Man",
            direction="bearish",
            strength=2,
            description="上昇トレンド中に出る下ひげの長いローソク足。上昇の勢いが衰えるサイン。",
        ))

    # ── 流れ星（シューティングスター）──────────────────────────
    # 条件: 上ひげ≥実体×2、下ひげ≤実体×0.5、陰線
    if (body > 0
            and upper >= body * 2.0
            and lower <= body * 0.5
            and _is_bearish(o, c)):
        patterns.append(CandlePattern(
            name="流れ星",
            name_en="Shooting Star",
            direction="bearish",
            strength=2,
            description="長い上ひげが買い圧力の失速を示す。上昇トレンド末期に出やすい反転サイン。",
        ))

    # ── 上影陰線（インバーテッドハンマー）──────────────────────
    elif (body > 0
            and upper >= body * 2.0
            and lower <= body * 0.5
            and _is_bullish(o, c)
            and prev_trend in ("下降", "bearish")):
        patterns.append(CandlePattern(
            name="上影陽線",
            name_en="Inverted Hammer",
            direction="bullish",
            strength=1,
            description="下落トレンド中に出る長い上ひげ。反転の可能性を示すが確認が必要。",
        ))

    # ── 大陽線 ──────────────────────────────────────────────────
    # 条件: 実体が全体の70%以上、陽線
    if body >= total * 0.7 and _is_bullish(o, c):
        patterns.append(CandlePattern(
            name="大陽線",
            name_en="Strong Bullish Candle",
            direction="bullish",
            strength=2,
            description="実体が大きく上昇の勢いが強い。買い圧力の強さを示す。",
        ))

    # ── 大陰線 ──────────────────────────────────────────────────
    elif body >= total * 0.7 and _is_bearish(o, c):
        patterns.append(CandlePattern(
            name="大陰線",
            name_en="Strong Bearish Candle",
            direction="bearish",
            strength=2,
            description="実体が大きく下落の勢いが強い。売り圧力の強さを示す。",
        ))

    return patterns


# ── 2本パターン ──────────────────────────────────────────────────────────────

def _detect_two_candle(
    o1: float, h1: float, l1: float, c1: float,
    o2: float, h2: float, l2: float, c2: float,
) -> list[CandlePattern]:
    """直近2本のローソク足からパターンを検出する。"""
    patterns: list[CandlePattern] = []
    body1 = _body(o1, c1)
    body2 = _body(o2, c2)

    if body1 < 1e-10:
        return patterns

    # ── 抱きの一本立ち（強気エンゴルフィング）──────────────────
    # 条件: 1本目が陰線、2本目が陽線で1本目の実体を包む
    if (_is_bearish(o1, c1)
            and _is_bullish(o2, c2)
            and o2 <= c1
            and c2 >= o1):
        patterns.append(CandlePattern(
            name="陽の包み足",
            name_en="Bullish Engulfing",
            direction="bullish",
            strength=3,
            description="前日の陰線を完全に包む大陽線。強い買い転換サイン。",
        ))

    # ── 陰の包み足（弱気エンゴルフィング）──────────────────────
    elif (_is_bullish(o1, c1)
            and _is_bearish(o2, c2)
            and o2 >= c1
            and c2 <= o1):
        patterns.append(CandlePattern(
            name="陰の包み足",
            name_en="Bearish Engulfing",
            direction="bearish",
            strength=3,
            description="前日の陽線を完全に包む大陰線。強い売り転換サイン。",
        ))

    # ── 二本たくり線（ツイーザーボトム）────────────────────────
    # 条件: 2本の安値がほぼ同じ、下ひげがある、2本目が陽線
    tol = abs(l1) * 0.001 + 1e-6
    if (abs(l1 - l2) <= tol
            and _is_bullish(o2, c2)
            and _lower_shadow(o1, l1, c1) > body1 * 0.5):
        patterns.append(CandlePattern(
            name="二本たくり線",
            name_en="Tweezer Bottom",
            direction="bullish",
            strength=2,
            description="2本連続で同じ安値をつけて反発。底値固めのサイン。",
        ))

    return patterns


# ── 3本パターン ──────────────────────────────────────────────────────────────

def _detect_three_candle(
    o1: float, h1: float, l1: float, c1: float,
    o2: float, h2: float, l2: float, c2: float,
    o3: float, h3: float, l3: float, c3: float,
) -> list[CandlePattern]:
    """直近3本のローソク足からパターンを検出する。"""
    patterns: list[CandlePattern] = []
    body1 = _body(o1, c1)
    body2 = _body(o2, c2)
    body3 = _body(o3, c3)
    mid1 = (o1 + c1) / 2

    if body1 < 1e-10 or body3 < 1e-10:
        return patterns

    # ── 三川明けの明星（モーニングスター）──────────────────────
    # 条件: 大陰線 → 小実体（ギャップ or 接続）→ 大陽線（1本目中心超え）
    if (_is_bearish(o1, c1)
            and body1 > body2 * 1.5
            and _is_bullish(o3, c3)
            and body3 > body2 * 1.5
            and c3 > mid1):
        patterns.append(CandlePattern(
            name="三川明けの明星",
            name_en="Morning Star",
            direction="bullish",
            strength=3,
            description="大陰線→小実体→大陽線の3本で形成。下落トレンドの強力な反転サイン。",
        ))

    # ── 三川宵の明星（イブニングスター）────────────────────────
    elif (_is_bullish(o1, c1)
            and body1 > body2 * 1.5
            and _is_bearish(o3, c3)
            and body3 > body2 * 1.5
            and c3 < mid1):
        patterns.append(CandlePattern(
            name="三川宵の明星",
            name_en="Evening Star",
            direction="bearish",
            strength=3,
            description="大陽線→小実体→大陰線の3本で形成。上昇トレンドの強力な反転サイン。",
        ))

    # ── 赤三兵（スリーホワイトソルジャーズ）────────────────────
    # 条件: 3本連続陽線、各ローソク足が前の終値より高く始まり高く終わる
    if (_is_bullish(o1, c1)
            and _is_bullish(o2, c2)
            and _is_bullish(o3, c3)
            and c2 > c1
            and c3 > c2
            and o2 >= o1 and o2 <= c1
            and o3 >= o2 and o3 <= c2):
        patterns.append(CandlePattern(
            name="赤三兵",
            name_en="Three White Soldiers",
            direction="bullish",
            strength=3,
            description="3本連続の大陽線。上昇の勢いが非常に強く、トレンド継続のサイン。",
        ))

    # ── 黒三兵（スリーブラッククロウズ）────────────────────────
    elif (_is_bearish(o1, c1)
            and _is_bearish(o2, c2)
            and _is_bearish(o3, c3)
            and c2 < c1
            and c3 < c2
            and o2 <= o1 and o2 >= c1
            and o3 <= o2 and o3 >= c2):
        patterns.append(CandlePattern(
            name="黒三兵",
            name_en="Three Black Crows",
            direction="bearish",
            strength=3,
            description="3本連続の大陰線。下落の勢いが非常に強く、トレンド継続のサイン。",
        ))

    return patterns


# ── メイン検出関数 ────────────────────────────────────────────────────────────

def detect_patterns(
    df: pd.DataFrame,
    prev_trend: str = "",
) -> list[CandlePattern]:
    """DataFrame の直近ローソク足からパターンを検出する。

    Args:
        df: OHLC DataFrame（index=datetime, columns=[open,high,low,close]）
             最低3行必要。
        prev_trend: 直前のトレンド方向（"上昇"/"下降" など）。
                    首吊り線・上影陽線の判定に使用。

    Returns:
        検出されたパターンのリスト（新しい順）。空の場合は []。
    """
    if df is None or len(df) < 1:
        return []

    required = {"open", "high", "low", "close"}
    if not required.issubset(set(df.columns)):
        return []

    patterns: list[CandlePattern] = []
    rows = df.tail(3)

    if len(rows) >= 1:
        r = rows.iloc[-1]
        patterns.extend(_detect_single(
            float(r["open"]), float(r["high"]),
            float(r["low"]),  float(r["close"]),
            prev_trend=prev_trend,
        ))

    if len(rows) >= 2:
        r1, r2 = rows.iloc[-2], rows.iloc[-1]
        patterns.extend(_detect_two_candle(
            float(r1["open"]), float(r1["high"]),
            float(r1["low"]),  float(r1["close"]),
            float(r2["open"]), float(r2["high"]),
            float(r2["low"]),  float(r2["close"]),
        ))

    if len(rows) >= 3:
        r1, r2, r3 = rows.iloc[-3], rows.iloc[-2], rows.iloc[-1]
        patterns.extend(_detect_three_candle(
            float(r1["open"]), float(r1["high"]),
            float(r1["low"]),  float(r1["close"]),
            float(r2["open"]), float(r2["high"]),
            float(r2["low"]),  float(r2["close"]),
            float(r3["open"]), float(r3["high"]),
            float(r3["low"]),  float(r3["close"]),
        ))

    # 重複除去（名前が同じものは最初の1つだけ残す）
    seen: set[str] = set()
    unique: list[CandlePattern] = []
    for p in patterns:
        if p.name not in seen:
            seen.add(p.name)
            unique.append(p)

    return unique
