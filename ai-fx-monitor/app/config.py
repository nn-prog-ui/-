import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

APP_ENV = os.getenv("APP_ENV", "development")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data/raw")
PROCESSED_DIR = BASE_DIR / os.getenv("PROCESSED_DIR", "data/processed")
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "data/fx_monitor.db")

DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "USD/JPY")
DEFAULT_CSV_FILE = os.getenv("DEFAULT_CSV_FILE", "USDJPY_1h.csv")

# サポートする通貨ペアと対応 CSV ファイルのマッピング（Phase 11: 複数ペア対応）
SYMBOL_CSV_MAP: dict[str, str] = {
    "USD/JPY": "USDJPY_1h.csv",
    "EUR/USD": "EURUSD_1h.csv",
    "GBP/USD": "GBPUSD_1h.csv",
    "EUR/JPY": "EURJPY_1h.csv",
}
SUPPORTED_SYMBOLS: list[str] = list(SYMBOL_CSV_MAP.keys())

# データソース: "csv"（デフォルト）または "oanda"
DATA_SOURCE = os.getenv("DATA_SOURCE", "csv").lower()

# OANDA デモAPI設定（DATA_SOURCE=oanda の場合のみ使用）
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice")

# 安全チェック：OANDAのライブ環境への接続を禁止
if OANDA_ENVIRONMENT == "live":
    raise RuntimeError(
        "OANDA_ENVIRONMENT=live は許可されていません。"
        "デモ口座（practice）のみ使用可能です。"
    )

TRADING_MODE = os.getenv("TRADING_MODE", "demo_only")

# 安全チェック：本番注文モードへの切り替えをブロック
if TRADING_MODE == "live":
    raise RuntimeError(
        "TRADING_MODE=live は許可されていません。"
        "このMVPでは本番注文機能は実装されていません。"
    )

DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
