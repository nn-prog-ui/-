"""市場分析統合サービス

データ読み込み→指標計算→ルール判定→コメント生成を統合する。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import DATA_DIR, DEFAULT_CSV_FILE, DEFAULT_SYMBOL
from app.data.loader import load_or_generate
from app.data.resampler import get_all_timeframes
from app.indicators.atr import get_atr_status, get_atr_value, get_recent_high, get_recent_low
from app.indicators.rsi import get_rsi_value
from app.services.ai_commentary import MockCommentaryAdapter
from app.services.economic_calendar import is_near_economic_event
from app.strategy.risk import TradeSetup, calculate_buy_setup, calculate_sell_setup
from app.strategy.rules import SIGNAL_BUY, SIGNAL_SELL, SIGNAL_SKIP, SignalResult, analyze_signal

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    symbol: str
    analyzed_at: datetime
    current_price: float | None
    signal: str
    score: int | None
    daily_trend: str
    h4_trend: str
    h1_status: str
    rsi: float | None
    atr_value: float | None
    atr_status: str
    recent_high: float | None
    recent_low: float | None
    setup: TradeSetup | None
    economic_warning: bool
    economic_event_name: str
    ai_comment: str
    skip_reasons: list[str]
    data_sufficient: bool
    is_dummy_data: bool

    @property
    def signal_label(self) -> str:
        labels = {SIGNAL_BUY: "買い候補", SIGNAL_SELL: "売り候補", SIGNAL_SKIP: "見送り"}
        return labels.get(self.signal, "不明")

    @property
    def signal_css_class(self) -> str:
        classes = {SIGNAL_BUY: "signal-buy", SIGNAL_SELL: "signal-sell", SIGNAL_SKIP: "signal-skip"}
        return classes.get(self.signal, "signal-skip")

    @property
    def entry_price(self) -> float | None:
        return self.setup.entry_price if self.setup else None

    @property
    def stop_loss(self) -> float | None:
        return self.setup.stop_loss if self.setup else None

    @property
    def take_profit(self) -> float | None:
        return self.setup.take_profit if self.setup else None

    @property
    def risk_reward(self) -> float | None:
        return self.setup.risk_reward if self.setup else None

    @property
    def can_approve_buy(self) -> bool:
        if self.signal != SIGNAL_BUY:
            return False
        if not self.setup:
            return False
        return self.setup.is_valid

    @property
    def can_approve_sell(self) -> bool:
        if self.signal != SIGNAL_SELL:
            return False
        if not self.setup:
            return False
        return self.setup.is_valid


def run_analysis(
    symbol: str | None = None,
    csv_path: str | Path | None = None,
) -> AnalysisResult:
    """メイン分析を実行して AnalysisResult を返す。"""
    symbol = symbol or DEFAULT_SYMBOL
    csv_path = csv_path or (DATA_DIR / DEFAULT_CSV_FILE)

    df_1h, is_dummy = load_or_generate(csv_path)
    if is_dummy:
        logger.warning("ダミーデータで分析中（CSVが見つかりません）")

    timeframes = get_all_timeframes(df_1h)
    df_daily = timeframes["daily"]
    df_4h = timeframes["4h"]

    economic_warning, event_name = is_near_economic_event()

    signal_result: SignalResult = analyze_signal(
        df_daily=df_daily,
        df_4h=df_4h,
        df_1h=df_1h,
        economic_warning=economic_warning,
    )

    current_price: float | None = None
    if not df_1h.empty:
        current_price = round(float(df_1h["close"].iloc[-1]), 3)

    setup: TradeSetup | None = None
    if signal_result.signal == SIGNAL_BUY:
        setup = calculate_buy_setup(df_1h, df_daily)
    elif signal_result.signal == SIGNAL_SELL:
        setup = calculate_sell_setup(df_1h, df_daily)

    commentary_adapter = MockCommentaryAdapter()
    ai_comment = commentary_adapter.generate(signal_result, setup)

    score_val: int | None = None
    if signal_result.score is not None:
        score_val = signal_result.score.score

    return AnalysisResult(
        symbol=symbol,
        analyzed_at=datetime.utcnow(),
        current_price=current_price,
        signal=signal_result.signal,
        score=score_val,
        daily_trend=signal_result.daily_trend,
        h4_trend=signal_result.h4_trend,
        h1_status=signal_result.h1_status,
        rsi=signal_result.rsi,
        atr_value=get_atr_value(df_1h),
        atr_status=get_atr_status(df_1h),
        recent_high=signal_result.recent_high,
        recent_low=signal_result.recent_low,
        setup=setup,
        economic_warning=economic_warning,
        economic_event_name=event_name,
        ai_comment=ai_comment,
        skip_reasons=signal_result.skip_reasons,
        data_sufficient=signal_result.data_sufficient,
        is_dummy_data=is_dummy,
    )
