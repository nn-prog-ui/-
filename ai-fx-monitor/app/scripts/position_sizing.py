"""Phase 51: ポジションサイジング計算機

口座残高・リスク許容度・過去成績から適正ロットサイズを算出する。
注文は発生しない。計算・表示のみ。

計算手法:
  1. 固定リスク法（Fixed Fractional）  : lot = (balance × risk_pct/100) / (stop_pips × pip_value)
  2. ケリー基準（Kelly Criterion）       : f* = p - (1-p)/R、推奨は半ケリー
  3. 固定比率法（Fixed Ratio）           : 参考提示のみ（Delta パラメータ依存）

注意: 計算結果はシミュレーションです。実際の取引には専門家の助言を求めてください。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db


@dataclass
class SizingInput:
    balance: float         # 口座残高（通貨単位）
    risk_pct: float        # 1トレードあたりのリスク割合（%）
    stop_pips: float       # 想定ストップロス（pips）
    pip_value: float       # 1pip あたりの価値（通貨単位 / lot）
    win_rate: float        # 勝率（0〜100）
    avg_win_pips: float    # 平均利益（pips）
    avg_loss_pips: float   # 平均損失（pips、正値）
    min_lot: float = 0.01  # 最小ロット
    lot_step: float = 0.01 # ロットステップ


@dataclass
class SizingResult:
    # 固定リスク法
    fixed_risk_lot: float         # 計算ロット
    fixed_risk_amount: float      # リスク額

    # ケリー基準
    kelly_fraction: float | None  # ケリー比率（0〜1）
    kelly_lot: float | None       # フルケリーロット
    half_kelly_lot: float | None  # 半ケリーロット（推奨）
    kelly_grade: str              # "負の期待値" / "低" / "適正" / "過大"

    # 共通
    expectancy_pips: float | None  # 期待値（pips/トレード）
    payoff_ratio: float | None     # 平均利益 / 平均損失

    warnings: list[str] = field(default_factory=list)


_KELLY_MAX_SAFE = 0.25  # フルケリー 25% 超は過大とみなす


def _round_lot(lot: float, min_lot: float, lot_step: float) -> float:
    """ロットをステップ単位に切り捨て、最小ロット以上を保証する。"""
    if lot_step <= 0:
        lot_step = 0.01
    steps = math.floor(lot / lot_step)
    rounded = steps * lot_step
    rounded = round(rounded, 10)
    return max(min_lot, rounded)


def calculate_sizing(inp: SizingInput) -> SizingResult:
    """3手法でポジションサイズを計算して返す。"""
    warnings: list[str] = []

    # 入力バリデーション
    if inp.balance <= 0:
        warnings.append("口座残高は正の値を入力してください。")
    if not (0 < inp.risk_pct <= 100):
        warnings.append("リスク割合は 0〜100% の範囲で入力してください。")
    if inp.stop_pips <= 0:
        warnings.append("ストップロス pips は正の値を入力してください。")
    if inp.pip_value <= 0:
        warnings.append("1pip 価値は正の値を入力してください。")

    # ── 固定リスク法 ────────────────────────────────────────────────
    risk_amount = inp.balance * inp.risk_pct / 100
    if inp.stop_pips > 0 and inp.pip_value > 0:
        raw_lot = risk_amount / (inp.stop_pips * inp.pip_value)
        fixed_risk_lot = _round_lot(raw_lot, inp.min_lot, inp.lot_step)
    else:
        fixed_risk_lot = inp.min_lot
        warnings.append("ストップロス pips または pip 価値が無効なため最小ロットを返します。")

    # ── ケリー基準 ──────────────────────────────────────────────────
    kelly_fraction: float | None = None
    kelly_lot: float | None = None
    half_kelly_lot: float | None = None
    kelly_grade = "N/A"
    expectancy_pips: float | None = None
    payoff_ratio: float | None = None

    p = inp.win_rate / 100  # 勝率（0〜1）
    q = 1 - p

    if inp.avg_win_pips > 0 and inp.avg_loss_pips > 0:
        rr = inp.avg_win_pips / inp.avg_loss_pips  # Payoff Ratio
        payoff_ratio = round(rr, 3)
        expectancy_pips = round(p * inp.avg_win_pips - q * inp.avg_loss_pips, 2)

        # f* = p - (1-p)/R = p - q/R
        kf = p - q / rr
        kelly_fraction = round(kf, 6)

        if kf <= 0:
            kelly_grade = "負の期待値"
            warnings.append("ケリー基準が負です。現在の成績ではシステムに期待値がありません。")
        else:
            # ケリー比率からロットを計算（口座の何%を1pip価値で割る）
            if inp.pip_value > 0 and inp.stop_pips > 0:
                kelly_risk_amount = inp.balance * kf
                raw_kelly_lot = kelly_risk_amount / (inp.stop_pips * inp.pip_value)
                kelly_lot = round(_round_lot(raw_kelly_lot, inp.min_lot, inp.lot_step), 2)
                hk_raw = kelly_risk_amount / 2 / (inp.stop_pips * inp.pip_value)
                half_kelly_lot = round(_round_lot(hk_raw, inp.min_lot, inp.lot_step), 2)

            if kf > _KELLY_MAX_SAFE:
                kelly_grade = "過大"
                warnings.append(
                    f"フルケリー比率が {kf*100:.1f}% と高すぎます。"
                    "半ケリー（Half Kelly）の使用を推奨します。"
                )
            elif kf > 0.1:
                kelly_grade = "適正"
            else:
                kelly_grade = "低"

    if inp.risk_pct > 5:
        warnings.append(f"リスク {inp.risk_pct}% は一般的な推奨値（1〜2%）を大きく上回ります。")

    return SizingResult(
        fixed_risk_lot=fixed_risk_lot,
        fixed_risk_amount=round(risk_amount, 2),
        kelly_fraction=kelly_fraction,
        kelly_lot=kelly_lot,
        half_kelly_lot=half_kelly_lot,
        kelly_grade=kelly_grade,
        expectancy_pips=expectancy_pips,
        payoff_ratio=payoff_ratio,
        warnings=warnings,
    )


def get_historical_stats(symbol: str | None = None, db_path=None) -> dict:
    """approval_history から勝率・平均利益・平均損失を返す（フォーム事前入力用）。"""
    path = db_path or DB_PATH
    clauses = [
        "outcome IN ('win', 'loss')",
        "human_action IN ('buy_approved', 'sell_approved')",
        "pnl_pips IS NOT NULL",
    ]
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    with get_db(path) as conn:
        rows = conn.execute(
            f"SELECT outcome, pnl_pips FROM approval_history WHERE {' AND '.join(clauses)}",
            params,
        ).fetchall()

    if not rows:
        return {"win_rate": None, "avg_win_pips": None, "avg_loss_pips": None, "trades": 0}

    wins = [float(r["pnl_pips"]) for r in rows if r["outcome"] == "win"]
    losses = [abs(float(r["pnl_pips"])) for r in rows if r["outcome"] == "loss"]
    n = len(rows)

    return {
        "win_rate": round(len(wins) / n * 100, 1) if n > 0 else None,
        "avg_win_pips": round(sum(wins) / len(wins), 1) if wins else None,
        "avg_loss_pips": round(sum(losses) / len(losses), 1) if losses else None,
        "trades": n,
    }
