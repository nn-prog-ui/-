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
