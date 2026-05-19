"""Phase 44: パラメータ感度分析エンジン

基準パラメータ（MA期間・RSI閾値）を ±10%〜±20% 変動させてバックテストを実行し、
勝率・損益の変化をマトリクスとして可視化する。

注文は一切発生しない。分析・集計のみ。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DATA_DIR, SUPPORTED_SYMBOLS, SYMBOL_CSV_MAP
from app.data.loader import load_or_generate
from app.scripts.optimizer import OptimizeParams, _run_one


# 感度分析で対応するパラメータ名とラベル
SENSITIVITY_PARAMS = {
    "ma_short": "短期MA期間",
    "ma_long": "長期MA期間",
    "rsi_buy_max": "RSI買い上限",
    "rsi_buy_min": "RSI買い下限",
    "rsi_sell_min": "RSI売り下限",
    "rsi_sell_max": "RSI売り上限",
}

# デフォルト変動ステップ（基準値に対する乗数）
DEFAULT_STEPS = [-0.20, -0.10, 0.0, +0.10, +0.20]

# バックテスト設定
DEFAULT_WINDOW = 300
DEFAULT_STEP_BARS = 24
DEFAULT_FUTURE_BARS = 80


@dataclass
class SensitivityCell:
    """感度マトリクスの1セル。"""
    x_val: float           # param_x の値
    y_val: float           # param_y の値
    trades: int
    wins: int
    losses: int
    win_rate: float | None
    total_pips: float
    avg_pips: float | None


@dataclass
class SensitivityResult:
    """感度分析の全体結果。"""
    symbol: str
    param_x: str           # X軸パラメータ名
    param_y: str           # Y軸パラメータ名
    base_x: float          # param_x の基準値
    base_y: float          # param_y の基準値
    x_values: list[float]  # X軸の値リスト
    y_values: list[float]  # Y軸の値リスト
    # cells[xi][yi] = SensitivityCell
    cells: list[list[SensitivityCell]] = field(default_factory=list)
    assessment: str = ""
    # 基準セル統計（steps=0の列）
    base_win_rate: float | None = None
    base_total_pips: float = 0.0


def _clamp_param(name: str, value: float) -> int:
    """パラメータ値を整数化して妥当な範囲にクランプする。"""
    v = max(1, int(round(value)))
    if name in ("ma_short", "ma_long"):
        return max(5, min(200, v))
    if name.startswith("rsi_"):
        return max(10, min(90, v))
    return v


def run_sensitivity(
    symbol: str,
    param_x: str = "ma_short",
    param_y: str = "ma_long",
    base_params: OptimizeParams | None = None,
    steps: list[float] = DEFAULT_STEPS,
    window: int = DEFAULT_WINDOW,
    step_bars: int = DEFAULT_STEP_BARS,
    future_bars: int = DEFAULT_FUTURE_BARS,
) -> SensitivityResult:
    """パラメータ感度分析を実行する。

    Args:
        symbol:      通貨ペア
        param_x:     X軸パラメータ名（SENSITIVITY_PARAMS のキー）
        param_y:     Y軸パラメータ名
        base_params: 基準パラメータ（None = デフォルト）
        steps:       変動ステップ（乗数リスト、例: [-0.2, 0, +0.2]）
        window:      判定ウィンドウ（バー数）
        step_bars:   判定ステップ
        future_bars: SL/TP判定用の未来バー数
    """
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"未対応シンボル: {symbol}")
    if param_x not in SENSITIVITY_PARAMS:
        raise ValueError(f"未対応パラメータ: {param_x}")
    if param_y not in SENSITIVITY_PARAMS:
        raise ValueError(f"未対応パラメータ: {param_y}")

    if base_params is None:
        base_params = OptimizeParams()

    base_x = float(getattr(base_params, param_x))
    base_y = float(getattr(base_params, param_y))

    x_values = [round(base_x * (1 + s), 1) for s in steps]
    y_values = [round(base_y * (1 + s), 1) for s in steps]

    csv_path = DATA_DIR / SYMBOL_CSV_MAP[symbol]
    df_full, _ = load_or_generate(csv_path, symbol=symbol)

    result = SensitivityResult(
        symbol=symbol,
        param_x=param_x,
        param_y=param_y,
        base_x=base_x,
        base_y=base_y,
        x_values=x_values,
        y_values=y_values,
    )

    cells: list[list[SensitivityCell]] = []
    base_xi = next((i for i, s in enumerate(steps) if s == 0.0), len(steps) // 2)

    for xi, xv in enumerate(x_values):
        row: list[SensitivityCell] = []
        for yi, yv in enumerate(y_values):
            # パラメータを組み立て
            params_dict = {
                "ma_short": int(base_params.ma_short),
                "ma_long": int(base_params.ma_long),
                "rsi_buy_max": int(base_params.rsi_buy_max),
                "rsi_buy_min": int(base_params.rsi_buy_min),
                "rsi_sell_min": int(base_params.rsi_sell_min),
                "rsi_sell_max": int(base_params.rsi_sell_max),
            }
            params_dict[param_x] = _clamp_param(param_x, xv)
            params_dict[param_y] = _clamp_param(param_y, yv)

            # ma_short < ma_long を保証
            if params_dict["ma_short"] >= params_dict["ma_long"]:
                cell = SensitivityCell(
                    x_val=xv, y_val=yv,
                    trades=0, wins=0, losses=0,
                    win_rate=None, total_pips=0.0, avg_pips=None,
                )
                row.append(cell)
                continue

            p = OptimizeParams(**params_dict)
            opt = _run_one(symbol, df_full, p, window=window, step=step_bars, future_bars=future_bars)
            cell = SensitivityCell(
                x_val=xv, y_val=yv,
                trades=opt.wins + opt.losses,
                wins=opt.wins,
                losses=opt.losses,
                win_rate=opt.win_rate,
                total_pips=round(opt.total_pips, 1),
                avg_pips=round(opt.avg_pips, 1) if opt.avg_pips is not None else None,
            )
            row.append(cell)
        cells.append(row)

    result.cells = cells

    # 基準行の統計
    if 0 <= base_xi < len(cells):
        base_row = cells[base_xi]
        base_yi = next((i for i, s in enumerate(steps) if s == 0.0), len(steps) // 2)
        if 0 <= base_yi < len(base_row):
            base_cell = base_row[base_yi]
            result.base_win_rate = base_cell.win_rate
            result.base_total_pips = base_cell.total_pips

    result.assessment = _assess(result, steps)
    return result


def _assess(r: SensitivityResult, steps: list[float]) -> str:
    """感度分析結果を日本語で評価する。"""
    all_cells = [c for row in r.cells for c in row if c.win_rate is not None]
    if not all_cells:
        return "有効なセルがありません（データ不足またはパラメータ制約違反）"

    win_rates = [c.win_rate for c in all_cells]
    wr_min = min(win_rates)
    wr_max = max(win_rates)
    wr_range = wr_max - wr_min

    parts = []
    if wr_range < 5.0:
        parts.append(f"感度: 低（勝率変動 {wr_range:.1f}%pt）")
    elif wr_range < 15.0:
        parts.append(f"感度: 中（勝率変動 {wr_range:.1f}%pt）")
    else:
        parts.append(f"感度: 高（勝率変動 {wr_range:.1f}%pt）")

    if r.base_win_rate is not None:
        above = sum(1 for c in all_cells if c.win_rate > r.base_win_rate)
        below = sum(1 for c in all_cells if c.win_rate < r.base_win_rate)
        if above > below:
            parts.append("改善余地: あり（基準より高い勝率の組み合わせが存在）")
        else:
            parts.append("現行パラメータ: 相対的に良好")

    return " / ".join(parts) if parts else "評価データ不足"
