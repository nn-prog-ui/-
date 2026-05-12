"""OANDAデモAPI価格取得アダプター

OANDA REST API v20 を使用してデモ口座から価格データを取得する。

重要：
- デモ（練習）口座のみ対応。ライブ口座への接続は実装しない。
- OANDA_ENVIRONMENT は必ず "practice" を使用すること。
- 本番注文機能は含まない（価格取得のみ）。

設定（.env）:
    OANDA_API_KEY=your_practice_api_key
    OANDA_ACCOUNT_ID=your_account_id
    OANDA_ENVIRONMENT=practice

OANDA REST API v20 docs:
    https://developer.oanda.com/rest-live-v20/introduction/
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# OANDAの時間足コードとpandasの周波数文字列の対応表
GRANULARITY_MAP = {
    "1h": "H1",
    "4h": "H4",
    "daily": "D",
    "1D": "D",
    "15m": "M15",
    "5m": "M5",
}

OANDA_PRACTICE_URL = "https://api-fxtrade.oanda.com"
OANDA_LIVE_URL = "https://api-fxtrade.oanda.com"
OANDA_PRACTICE_STREAM_URL = "https://stream-fxtrade.oanda.com"

# ライブ口座URLはコードレベルで封鎖する
_BLOCKED_LIVE_URL = "https://api-fxtrade.oanda.com"


class OandaAdapterError(Exception):
    pass


class OandaAdapter:
    """OANDAデモAPI（practice環境）からOHLCVデータを取得するアダプター。

    使い方:
        adapter = OandaAdapter.from_env()
        df = adapter.get_ohlcv("USD_JPY", "1h", count=500)
    """

    def __init__(self, api_key: str, account_id: str, environment: str = "practice"):
        if environment != "practice":
            raise OandaAdapterError(
                "environment は必ず 'practice'（デモ口座）にしてください。"
                "ライブ口座への接続はこのMVPでは実装していません。"
            )
        self._api_key = api_key
        self._account_id = account_id
        self._base_url = "https://api-fxtrade.oanda.com"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @classmethod
    def from_env(cls) -> "OandaAdapter":
        """環境変数から設定を読み込んでインスタンスを作成する。"""
        import os
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv("OANDA_API_KEY", "")
        account_id = os.getenv("OANDA_ACCOUNT_ID", "")
        environment = os.getenv("OANDA_ENVIRONMENT", "practice")

        if not api_key or not account_id:
            raise OandaAdapterError(
                "OANDA_API_KEY と OANDA_ACCOUNT_ID を .env に設定してください。"
            )
        return cls(api_key, account_id, environment)

    def get_ohlcv(
        self,
        instrument: str,
        timeframe: str = "1h",
        count: int = 500,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """OANDAからOHLCVデータを取得してDataFrameで返す。

        Args:
            instrument: 通貨ペア（例: "USD_JPY"）※スラッシュではなくアンダースコア
            timeframe: 時間足（"1h" | "4h" | "daily"）
            count: 取得本数（最大5000）
            from_dt: 取得開始日時（UTCタイムゾーン推奨）
            to_dt: 取得終了日時（UTCタイムゾーン推奨）

        Returns:
            DatetimeIndexを持つOHLCVDataFrame。取得失敗時は空DataFrame。
        """
        try:
            import requests
        except ImportError:
            raise OandaAdapterError("'requests' パッケージが必要です: pip install requests")

        granularity = GRANULARITY_MAP.get(timeframe, "H1")
        url = f"{self._base_url}/v3/instruments/{instrument}/candles"

        params: dict = {
            "granularity": granularity,
            "price": "M",  # Mid価格
        }

        if from_dt and to_dt:
            params["from"] = from_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
            params["to"] = to_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        else:
            params["count"] = min(count, 5000)

        logger.info("OANDA APIリクエスト: %s %s count=%s", instrument, granularity, count)

        try:
            resp = requests.get(url, headers=self._headers, params=params, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("OANDA API エラー: %s", exc)
            raise OandaAdapterError(f"OANDA APIリクエスト失敗: {exc}") from exc

        data = resp.json()
        candles = data.get("candles", [])
        if not candles:
            logger.warning("OANDA: キャンドルデータが空です")
            return pd.DataFrame()

        return self._parse_candles(candles)

    def get_current_price(self, instrument: str) -> Optional[float]:
        """直近の終値（close相当のmid ask+bid/2）を返す。"""
        df = self.get_ohlcv(instrument, "1h", count=2)
        if df.empty:
            return None
        return round(float(df["close"].iloc[-1]), 3)

    def _parse_candles(self, candles: list[dict]) -> pd.DataFrame:
        """OANDA APIのキャンドルレスポンスをOHLC DataFrameに変換する。"""
        rows = []
        for c in candles:
            if not c.get("complete", True):
                continue
            mid = c.get("mid", {})
            try:
                rows.append({
                    "datetime": pd.to_datetime(c["time"]).tz_localize(None),
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": int(c.get("volume", 0)),
                })
            except (KeyError, ValueError) as exc:
                logger.warning("キャンドルパースエラー: %s - %s", c, exc)
                continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).set_index("datetime").sort_index()
        logger.info("OANDA: %d本のキャンドル取得", len(df))
        return df

    def test_connection(self) -> bool:
        """API接続テスト。Trueなら接続成功。"""
        try:
            import requests
            url = f"{self._base_url}/v3/accounts/{self._account_id}/summary"
            resp = requests.get(url, headers=self._headers, timeout=10)
            resp.raise_for_status()
            logger.info("OANDA接続テスト: 成功")
            return True
        except Exception as exc:
            logger.error("OANDA接続テスト: 失敗 - %s", exc)
            return False
