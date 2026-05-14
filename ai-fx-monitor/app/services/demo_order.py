"""デモ注文アダプター（OANDA practice環境専用）

重要な安全制約：
- OANDA_ENVIRONMENT=practice の場合のみ動作する
- ライブ口座への接続は設計レベルで不可能にしている
- このモジュールは本番注文機能を含まない
- 人間が2段階で確認した後でのみ注文が実行される
- 承認ボタンからは呼び出されない（完全に独立したフロー）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ライブ環境URLはコード内に存在させない
_PRACTICE_BASE_URL = "https://api-fxtrade.oanda.com"

# シンボル変換（USD/JPY → USD_JPY）
def _to_oanda_instrument(symbol: str) -> str:
    return symbol.replace("/", "_")


@dataclass
class DemoOrderResult:
    success: bool
    trade_id: str | None
    order_id: str | None
    filled_price: float | None
    units: int
    instrument: str
    message: str


class DemoOrderError(Exception):
    pass


class DemoOrderAdapter:
    """OANDA practice 口座へデモ注文を送信するアダプター。

    使用条件:
    - OANDA_ENVIRONMENT=practice が必須
    - DATA_SOURCE=oanda が必須
    - 人間が2段階確認した後でのみ呼び出される
    """

    def __init__(self, api_key: str, account_id: str, environment: str = "practice") -> None:
        if environment != "practice":
            raise DemoOrderError(
                "デモ注文は OANDA_ENVIRONMENT=practice（デモ口座）でのみ使用できます。"
                "ライブ口座への接続はこのシステムでは実装していません。"
            )
        self._api_key = api_key
        self._account_id = account_id
        self._base_url = _PRACTICE_BASE_URL
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @classmethod
    def from_env(cls) -> "DemoOrderAdapter":
        """環境変数から設定を読み込んでインスタンスを作成する。"""
        import os
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv("OANDA_API_KEY", "")
        account_id = os.getenv("OANDA_ACCOUNT_ID", "")
        environment = os.getenv("OANDA_ENVIRONMENT", "practice")

        if not api_key or not account_id:
            raise DemoOrderError(
                "OANDA_API_KEY と OANDA_ACCOUNT_ID を .env に設定してください。"
            )
        return cls(api_key, account_id, environment)

    def place_market_order(
        self,
        symbol: str,
        direction: str,
        units: int,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> DemoOrderResult:
        """成行注文をデモ口座に送信する。

        Args:
            symbol: 通貨ペア（例: "USD/JPY"）
            direction: "BUY" または "SELL"
            units: 注文数量（正数 = 買い、負数 = 売りに自動変換）
            stop_loss: 損切り価格
            take_profit: 利確価格
        """
        try:
            import requests
        except ImportError:
            raise DemoOrderError("'requests' パッケージが必要です: pip install requests")

        instrument = _to_oanda_instrument(symbol)
        signed_units = units if direction == "BUY" else -units

        order_body: dict = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(signed_units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }

        if stop_loss is not None:
            order_body["order"]["stopLossOnFill"] = {"price": f"{stop_loss:.3f}"}
        if take_profit is not None:
            order_body["order"]["takeProfitOnFill"] = {"price": f"{take_profit:.3f}"}

        url = f"{self._base_url}/v3/accounts/{self._account_id}/orders"

        try:
            resp = requests.post(url, json=order_body, headers=self._headers, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("OANDA デモ注文エラー: %s", exc)
            raise DemoOrderError(f"注文送信失敗: {exc}") from exc

        data = resp.json()
        fill = data.get("orderFillTransaction", {})
        trade_id = fill.get("tradeOpened", {}).get("tradeID")
        related = data.get("relatedTransactionIDs") or []
        order_id = related[0] if related else None
        filled_price_str = fill.get("price")
        filled_price = float(filled_price_str) if filled_price_str else None

        logger.info(
            "デモ注文完了: %s %s %d units @ %s (trade_id=%s)",
            direction, instrument, units, filled_price, trade_id,
        )
        return DemoOrderResult(
            success=True,
            trade_id=trade_id,
            order_id=order_id,
            filled_price=filled_price,
            units=signed_units,
            instrument=instrument,
            message=f"デモ注文完了: {direction} {units}units @ {filled_price}",
        )

    def close_trade(self, trade_id: str) -> DemoOrderResult:
        """デモ口座の指定トレードをクローズ（成行決済）する。

        Args:
            trade_id: OANDA トレードID（文字列）

        Returns:
            DemoOrderResult（filled_price が決済価格）
        """
        try:
            import requests
        except ImportError:
            raise DemoOrderError("'requests' パッケージが必要です")

        url = f"{self._base_url}/v3/accounts/{self._account_id}/trades/{trade_id}/close"

        try:
            resp = requests.put(url, headers=self._headers, json={}, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("デモトレードクローズエラー: %s", exc)
            raise DemoOrderError(f"クローズ失敗: {exc}") from exc

        data = resp.json()
        fill = data.get("orderFillTransaction", {})
        price_str = fill.get("price")
        exit_price = float(price_str) if price_str else None
        related = data.get("relatedTransactionIDs") or []
        order_id = related[0] if related else None

        logger.info("デモトレードクローズ完了: trade_id=%s @ %s", trade_id, exit_price)
        return DemoOrderResult(
            success=True,
            trade_id=trade_id,
            order_id=order_id,
            filled_price=exit_price,
            units=0,
            instrument="",
            message=f"クローズ完了 @ {exit_price}",
        )

    def get_trade_detail(self, trade_id: str) -> dict | None:
        """デモ口座の指定トレード詳細（現在P&L含む）を取得する。

        Returns:
            OANDA APIのトレード詳細dict、取得失敗時はNone
        """
        try:
            import requests
        except ImportError:
            raise DemoOrderError("'requests' パッケージが必要です")

        url = f"{self._base_url}/v3/accounts/{self._account_id}/trades/{trade_id}"
        try:
            resp = requests.get(url, headers=self._headers, timeout=15)
            resp.raise_for_status()
            return resp.json().get("trade")
        except Exception as exc:
            logger.error("トレード詳細取得エラー: %s", exc)
            return None

    def get_open_trades(self, instrument: str | None = None) -> list[dict]:
        """デモ口座のオープントレード一覧を返す。"""
        try:
            import requests
        except ImportError:
            raise DemoOrderError("'requests' パッケージが必要です")

        url = f"{self._base_url}/v3/accounts/{self._account_id}/openTrades"
        params = {}
        if instrument:
            params["instrument"] = _to_oanda_instrument(instrument)

        try:
            resp = requests.get(url, headers=self._headers, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json().get("trades", [])
        except Exception as exc:
            logger.error("オープントレード取得エラー: %s", exc)
            return []


def is_demo_order_available() -> bool:
    """デモ注文が利用可能な設定になっているか確認する。"""
    import os
    from dotenv import load_dotenv

    load_dotenv()
    data_source = os.getenv("DATA_SOURCE", "csv").lower()
    environment = os.getenv("OANDA_ENVIRONMENT", "practice")
    api_key = os.getenv("OANDA_API_KEY", "")
    account_id = os.getenv("OANDA_ACCOUNT_ID", "")

    return (
        data_source == "oanda"
        and environment == "practice"
        and bool(api_key)
        and bool(account_id)
    )
