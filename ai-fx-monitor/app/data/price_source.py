"""価格データソースファクトリー

CSVファイルとOANDA APIを統一インターフェースで切り替える。

DATA_SOURCE 環境変数で切り替える:
    DATA_SOURCE=csv     (デフォルト) CSVファイルから読み込む
    DATA_SOURCE=oanda   OANDAデモAPIから取得する

どちらのソースを使っても get_all_timeframes() は同じ形式のDataFrameを返す。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from app.data.loader import load_or_generate
from app.data.resampler import get_all_timeframes

logger = logging.getLogger(__name__)


class PriceSourceError(Exception):
    pass


def get_price_data(
    symbol: str = "USD/JPY",
    csv_path: str | Path | None = None,
) -> tuple[dict[str, pd.DataFrame], bool]:
    """設定に応じて価格データを取得する。

    Args:
        symbol: 通貨ペア（例: "USD/JPY"）
        csv_path: CSVパス（DATA_SOURCE=csv の場合）

    Returns:
        (timeframes_dict, is_dummy): {"1h": df, "4h": df, "daily": df} とダミーフラグ
    """
    source = os.getenv("DATA_SOURCE", "csv").lower()

    if source == "oanda":
        return _get_from_oanda(symbol)
    else:
        return _get_from_csv(csv_path)


def _get_from_csv(csv_path: str | Path | None) -> tuple[dict[str, pd.DataFrame], bool]:
    """CSVファイルからデータを読み込む（デフォルト）。"""
    from app.config import DATA_DIR, DEFAULT_CSV_FILE

    path = csv_path or (DATA_DIR / DEFAULT_CSV_FILE)
    df_1h, is_dummy = load_or_generate(path)
    timeframes = get_all_timeframes(df_1h)
    return timeframes, is_dummy


def _get_from_oanda(symbol: str) -> tuple[dict[str, pd.DataFrame], bool]:
    """OANDAデモAPIからデータを取得する。

    失敗時はCSVフォールバックを行う。
    """
    from app.config import DATA_DIR, DEFAULT_CSV_FILE
    from app.data.oanda_adapter import OandaAdapter, OandaAdapterError

    # USD/JPY → USD_JPY（OANDAの形式）
    instrument = symbol.replace("/", "_")

    try:
        adapter = OandaAdapter.from_env()

        logger.info("OANDAから1時間足データ取得中: %s", instrument)
        df_1h = adapter.get_ohlcv(instrument, "1h", count=3000)

        if df_1h.empty:
            logger.warning("OANDA: データが空。CSVにフォールバック")
            return _get_from_csv(None)

        # 4時間足・日足はAPIから別途取得するか、1hからリサンプル
        # MVPではリサンプルで対応（API呼び出し数を節約）
        timeframes = get_all_timeframes(df_1h)
        logger.info("OANDAデータ取得成功: 1h=%d本", len(df_1h))
        return timeframes, False

    except OandaAdapterError as exc:
        logger.warning("OANDA取得失敗（%s）→ CSVにフォールバック", exc)
        return _get_from_csv(None)
    except Exception as exc:
        logger.error("予期しないエラー（%s）→ CSVにフォールバック", exc)
        return _get_from_csv(None)


def check_oanda_connection() -> dict[str, str | bool]:
    """OANDA接続状態を確認する（設定画面用）。"""
    source = os.getenv("DATA_SOURCE", "csv").lower()
    if source != "oanda":
        return {"source": "csv", "connected": False, "message": "DATA_SOURCE=csv（OANDAは無効）"}

    try:
        from app.data.oanda_adapter import OandaAdapter, OandaAdapterError

        adapter = OandaAdapter.from_env()
        connected = adapter.test_connection()
        return {
            "source": "oanda",
            "connected": connected,
            "message": "接続成功" if connected else "接続失敗（APIキーを確認してください）",
        }
    except Exception as exc:
        return {"source": "oanda", "connected": False, "message": str(exc)}
