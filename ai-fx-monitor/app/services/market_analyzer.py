"""市場分析統合サービス

データ読み込み→指標計算→ルール判定→コメント生成を統合する。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.config import DATA_DIR, DEFAULT_CSV_FILE, DEFAULT_SYMBOL, SYMBOL_CSV_MAP
from app.data.loader import load_or_generate
from app.data.price_source import get_price_data
from app.data.resampler import get_all_timeframes
from app.indicators.atr import get_atr_status, get_atr_value, get_recent_high, get_recent_low
from app.indicators.bollinger_bands import get_bb_status, get_bb_values
from app.indicators.currency_strength import calculate_pair_momentum, get_strength_status
from app.indicators.macd import get_macd_status, get_macd_values
from app.indicators.rsi import get_rsi_value
from app.services.ai_commentary import MockCommentaryAdapter
from app.services.economic_calendar import is_near_economic_event
from app.strategy.risk import TradeSetup, calculate_buy_setup, calculate_sell_setup
from app.strategy.rules import SIGNAL_BUY, SIGNAL_SELL, SIGNAL_SKIP, SignalResult, analyze_signal
from app.strategy.scoring import ConditionResult, ConfluenceResult

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
    # Phase 11: ボリンジャーバンド
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_status: str = "判定不能"
    # Phase 11: MACD
    macd_value: float | None = None
    macd_signal_value: float | None = None
    macd_histogram: float | None = None
    macd_status: str = "判定不能"
    # Phase 11: 通貨強弱（単一ペアモメンタムスコア）
    currency_strength: float | None = None
    currency_strength_status: str = "判定不能"
    # Phase 19: 判定根拠（条件ごとの結果）
    buy_conditions: list[ConditionResult] = field(default_factory=list)
    sell_conditions: list[ConditionResult] = field(default_factory=list)
    # Phase 20: 過去トレードからの学習データ
    historical_stats: dict = field(default_factory=dict)
    # Phase 32: マルチタイムフレーム一致度
    confluence: ConfluenceResult | None = None
    # Phase 46: シグナル品質スコアリング
    signal_quality: object = None  # QualityStats | None
    # Phase 68: 地政学リスクスコア補正
    geo_score_adjustment: int = 0
    geo_risk_level: str = "neutral"

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
    """メイン分析を実行して AnalysisResult を返す。

    DATA_SOURCE=oanda の場合はOANDA APIを使用する。
    失敗時は自動的にCSVにフォールバックする。
    symbol が SYMBOL_CSV_MAP に含まれる場合、対応する CSV を自動選択する。
    """
    symbol = symbol or DEFAULT_SYMBOL

    if csv_path is None:
        csv_filename = SYMBOL_CSV_MAP.get(symbol, DEFAULT_CSV_FILE)
        csv_path = DATA_DIR / csv_filename

    timeframes, is_dummy = get_price_data(symbol, csv_path)
    if is_dummy:
        logger.warning("ダミーデータで分析中（CSVが見つかりません）")

    df_1h = timeframes.get("1h", pd.DataFrame())
    df_daily = timeframes.get("daily", pd.DataFrame())
    df_4h = timeframes.get("4h", pd.DataFrame())

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

    # Phase 20: 過去トレードからの学習データを取得
    try:
        from app.database.repository import get_signal_pattern_stats
        historical_stats = get_signal_pattern_stats(
            signal=signal_result.signal,
            daily_trend=signal_result.daily_trend,
            h4_trend=signal_result.h4_trend,
        )
    except Exception:
        historical_stats = {}

    commentary_adapter = MockCommentaryAdapter()
    ai_comment = commentary_adapter.generate(signal_result, setup, historical_stats)

    score_val: int | None = None
    if signal_result.score is not None:
        score_val = signal_result.score.score

    # Phase 68: 地政学リスクによるスコア補正（シグナル変更なし・表示スコアのみ）
    _GEO_ADJUSTMENT = {
        "strong_bullish": 1,
        "bullish": 1,
        "neutral": 0,
        "bearish": -1,
        "strong_bearish": -1,
    }
    geo_score_adjustment = 0
    geo_risk_level = "neutral"
    try:
        from app.scripts.geopolitical import get_geopolitical_records
        geo_recs = get_geopolitical_records(limit=1)
        if geo_recs:
            geo_risk_level = geo_recs[0].usd_impact
            geo_score_adjustment = _GEO_ADJUSTMENT.get(geo_risk_level, 0)
            if score_val is not None:
                score_val = max(-7, min(7, score_val + geo_score_adjustment))
    except Exception:
        pass

    # Phase 46: シグナル品質スコアリング
    signal_quality = None
    try:
        from app.scripts.signal_quality import get_signal_quality
        rsi_val = None
        if not df_1h.empty:
            from app.indicators.rsi import get_rsi_value
            rsi_val = get_rsi_value(df_1h)
        signal_quality = get_signal_quality(
            symbol=symbol,
            signal=signal_result.signal,
            score=score_val,
            rsi=rsi_val,
            daily_trend=signal_result.daily_trend,
            h4_trend=signal_result.h4_trend,
        )
    except Exception:
        signal_quality = None

    # Phase 11: ボリンジャーバンド（1時間足）
    bb_upper, bb_middle, bb_lower = get_bb_values(df_1h)
    bb_status = get_bb_status(df_1h)

    # Phase 11: MACD（1時間足）
    macd_val, macd_sig, macd_hist = get_macd_values(df_1h)
    macd_status = get_macd_status(df_1h)

    # Phase 11: 通貨強弱（日足モメンタム）
    strength_score: float | None = None
    strength_status = "判定不能"
    if not df_daily.empty:
        strength_score = calculate_pair_momentum(df_daily)
        strength_status = get_strength_status(strength_score)

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
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
        bb_status=bb_status,
        macd_value=macd_val,
        macd_signal_value=macd_sig,
        macd_histogram=macd_hist,
        macd_status=macd_status,
        currency_strength=strength_score,
        currency_strength_status=strength_status,
        buy_conditions=signal_result.buy_conditions,
        sell_conditions=signal_result.sell_conditions,
        historical_stats=historical_stats,
        confluence=signal_result.confluence,
        signal_quality=signal_quality,
        geo_score_adjustment=geo_score_adjustment,
        geo_risk_level=geo_risk_level,
    )
