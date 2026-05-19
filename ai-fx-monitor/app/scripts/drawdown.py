"""Phase 47: ドローダウン分析

過去の取引履歴から資産曲線・最大ドローダウン・回復期間・
プロフィットファクターなどを計算して提供する。

注文は発生しない。集計・分析のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DB_PATH
from app.database.db import get_db


@dataclass
class EquityPoint:
    index: int            # トレード連番
    created_at: str       # 約定日時 (ISO 文字列)
    pnl_pips: float       # 当該トレードの損益
    equity: float         # 累積損益 (pips)
    peak: float           # ここまでの累積最高値
    drawdown: float       # equity - peak (常に <= 0)
    drawdown_pct: float   # drawdown / peak * 100 (peak=0 なら 0)


@dataclass
class DrawdownStats:
    symbol: str | None           # None = 全通貨ペア合算
    trades: int                  # 集計対象トレード数
    total_pips: float            # 合計損益 (pips)
    max_drawdown: float          # 最大ドローダウン (pips, <= 0)
    max_drawdown_pct: float      # 最大ドローダウン (%)
    avg_drawdown: float          # ドローダウン期間中の平均 (pips)
    longest_drawdown_bars: int   # 最大ドローダウン継続トレード数
    recovery_factor: float       # total_pips / |max_drawdown| (inf if dd=0)
    profit_factor: float         # Σwins / Σ|losses|
    avg_win_pips: float          # 勝ちトレードの平均損益
    avg_loss_pips: float         # 負けトレードの平均損益 (>= 0 として保持)
    risk_reward: float           # avg_win / avg_loss
    win_rate: float              # 勝率 (0〜100)
    equity_curve: list[EquityPoint] = field(default_factory=list)


def _build_equity_curve(rows: list) -> list[EquityPoint]:
    """DB 行リストから EquityPoint リストを生成する。"""
    points: list[EquityPoint] = []
    equity = 0.0
    peak = 0.0
    for i, row in enumerate(rows):
        pnl = float(row["pnl_pips"] or 0.0)
        equity = round(equity + pnl, 4)
        if equity > peak:
            peak = equity
        drawdown = round(equity - peak, 4)
        drawdown_pct = round(drawdown / peak * 100, 2) if peak > 0 else 0.0
        points.append(EquityPoint(
            index=i + 1,
            created_at=row["created_at"],
            pnl_pips=pnl,
            equity=equity,
            peak=peak,
            drawdown=drawdown,
            drawdown_pct=drawdown_pct,
        ))
    return points


def _compute_stats(
    symbol: str | None,
    equity_curve: list[EquityPoint],
    raw_pnls: list[float],
) -> DrawdownStats:
    """EquityPoint リストから統計指標を計算する。"""
    n = len(equity_curve)
    if n == 0:
        return DrawdownStats(
            symbol=symbol, trades=0, total_pips=0.0,
            max_drawdown=0.0, max_drawdown_pct=0.0, avg_drawdown=0.0,
            longest_drawdown_bars=0, recovery_factor=0.0,
            profit_factor=0.0, avg_win_pips=0.0, avg_loss_pips=0.0,
            risk_reward=0.0, win_rate=0.0, equity_curve=[],
        )

    total_pips = equity_curve[-1].equity

    # ドローダウン統計
    drawdowns = [p.drawdown for p in equity_curve]
    max_dd = min(drawdowns)
    max_dd_pct = min(p.drawdown_pct for p in equity_curve)

    dd_values = [d for d in drawdowns if d < 0]
    avg_dd = round(sum(dd_values) / len(dd_values), 4) if dd_values else 0.0

    # 最大ドローダウン継続期間（連続して peak 未満の期間）
    longest = 0
    current_run = 0
    for p in equity_curve:
        if p.drawdown < 0:
            current_run += 1
            longest = max(longest, current_run)
        else:
            current_run = 0

    # プロフィットファクター・勝率
    wins = [p for p in raw_pnls if p > 0]
    losses = [p for p in raw_pnls if p < 0]
    wins_sum = sum(wins)
    losses_sum = abs(sum(losses))
    profit_factor = round(wins_sum / losses_sum, 3) if losses_sum > 0 else float("inf")

    avg_win = round(sum(wins) / len(wins), 3) if wins else 0.0
    avg_loss = round(abs(sum(losses) / len(losses)), 3) if losses else 0.0
    risk_reward = round(avg_win / avg_loss, 3) if avg_loss > 0 else float("inf")
    win_rate = round(len(wins) / n * 100, 1)

    # リカバリーファクター
    if max_dd < 0:
        recovery_factor = round(total_pips / abs(max_dd), 3)
    elif total_pips > 0:
        recovery_factor = float("inf")
    else:
        recovery_factor = 0.0

    return DrawdownStats(
        symbol=symbol,
        trades=n,
        total_pips=round(total_pips, 3),
        max_drawdown=round(max_dd, 3),
        max_drawdown_pct=round(max_dd_pct, 2),
        avg_drawdown=avg_dd,
        longest_drawdown_bars=longest,
        recovery_factor=recovery_factor,
        profit_factor=profit_factor,
        avg_win_pips=avg_win,
        avg_loss_pips=avg_loss,
        risk_reward=risk_reward,
        win_rate=win_rate,
        equity_curve=equity_curve,
    )


def get_drawdown_stats(
    symbol: str | None = None,
    db_path=None,
) -> DrawdownStats:
    """指定通貨ペア（None = 全ペア）のドローダウン統計を返す。

    pnl_pips が NULL のトレードは 0 として扱う。
    human_action が buy / sell のクローズ済みトレードのみ対象。
    """
    path = db_path or DB_PATH
    clauses = ["outcome IS NOT NULL", "human_action IN ('buy', 'sell')"]
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)

    where = " AND ".join(clauses)
    sql = f"""
        SELECT created_at, pnl_pips
        FROM approval_history
        WHERE {where}
        ORDER BY created_at ASC
    """

    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()

    raw_pnls = [float(r["pnl_pips"] or 0.0) for r in rows]
    curve = _build_equity_curve(rows)
    return _compute_stats(symbol, curve, raw_pnls)


def get_drawdown_by_symbol(db_path=None) -> list[DrawdownStats]:
    """各通貨ペア別のドローダウン統計一覧を返す。"""
    path = db_path or DB_PATH
    with get_db(path) as conn:
        symbols = [
            row[0]
            for row in conn.execute(
                """SELECT DISTINCT symbol FROM approval_history
                   WHERE outcome IS NOT NULL AND human_action IN ('buy','sell')
                   ORDER BY symbol"""
            ).fetchall()
        ]
    return [get_drawdown_stats(sym, db_path=path) for sym in symbols]


def equity_curve_to_chart_data(curve: list[EquityPoint]) -> dict:
    """Chart.js 用のデータ構造に変換する。"""
    labels = [p.created_at[:10] for p in curve]
    equity_data = [p.equity for p in curve]
    drawdown_data = [p.drawdown for p in curve]
    return {
        "labels": labels,
        "equity": equity_data,
        "drawdown": drawdown_data,
    }
