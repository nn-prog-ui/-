"""Phase 76: Railway 起動時チェック・初期化

アプリ起動時に実行される初期化処理。
- 必要なディレクトリの作成
- CSVデータファイルが存在しない場合はダミーデータを生成
- 環境変数の安全チェック（TRADING_MODE）

注文機能は一切含まない。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_directories(base_dir: Path | None = None) -> None:
    """必要なデータディレクトリを作成する。"""
    if base_dir is None:
        from app.config import BASE_DIR
        base_dir = BASE_DIR

    dirs = [
        base_dir / "data",
        base_dir / "data" / "raw",
        base_dir / "data" / "processed",
        base_dir / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        logger.debug("ディレクトリ確認: %s", d)


def ensure_csv_data(base_dir: Path | None = None) -> dict[str, bool]:
    """CSVデータファイルが存在しない場合はダミーデータを生成する。

    Returns:
        {symbol: was_generated} — 生成した場合 True、既存の場合 False
    """
    if base_dir is None:
        from app.config import BASE_DIR
        base_dir = BASE_DIR

    from app.config import SYMBOL_CSV_MAP
    from app.data.loader import load_or_generate

    results: dict[str, bool] = {}
    raw_dir = base_dir / "data" / "raw"

    for symbol, csv_file in SYMBOL_CSV_MAP.items():
        csv_path = raw_dir / csv_file
        already_exists = csv_path.exists() and csv_path.stat().st_size > 0

        if not already_exists:
            logger.info("CSVファイルが存在しないためダミーデータを生成: %s", csv_path)
            try:
                load_or_generate(csv_path, symbol)
                logger.info("ダミーデータ生成完了: %s", csv_file)
                results[symbol] = True
            except Exception as exc:
                logger.warning("ダミーデータ生成失敗 [%s]: %s", symbol, exc)
                results[symbol] = False
        else:
            logger.debug("CSVファイル確認: %s (%d bytes)", csv_file, csv_path.stat().st_size)
            results[symbol] = False

    return results


def check_safety_env() -> list[str]:
    """安全に関わる環境変数を検証し、問題があれば警告リストを返す。

    Returns:
        警告メッセージのリスト（空リストなら問題なし）
    """
    warnings: list[str] = []

    trading_mode = os.getenv("TRADING_MODE", "demo_only")
    if trading_mode != "demo_only":
        warnings.append(
            f"TRADING_MODE='{trading_mode}' は不正な値です。'demo_only' に設定してください。"
        )

    oanda_env = os.getenv("OANDA_ENVIRONMENT", "practice")
    if oanda_env == "live":
        warnings.append(
            "OANDA_ENVIRONMENT=live は禁止されています。'practice' のままにしてください。"
        )

    app_env = os.getenv("APP_ENV", "development")
    if app_env == "production":
        auth_user = os.getenv("AUTH_USERNAME", "")
        auth_pass = os.getenv("AUTH_PASSWORD", "")
        if not auth_user or not auth_pass:
            warnings.append(
                "本番環境では AUTH_USERNAME と AUTH_PASSWORD の設定を強く推奨します。"
            )

    return warnings


def run_startup_checks(base_dir: Path | None = None) -> dict:
    """全起動チェックを実行し、サマリーを返す。

    この関数は app/main.py の startup_event から呼ばれる。
    """
    logger.info("=== 起動チェック開始（Phase 76）===")

    # 1. ディレクトリ確認
    ensure_directories(base_dir)

    # 2. CSV データ確認・生成
    try:
        csv_results = ensure_csv_data(base_dir)
        generated = [s for s, g in csv_results.items() if g]
        if generated:
            logger.info("ダミーCSV生成: %s", generated)
    except Exception as exc:
        logger.warning("CSV初期化エラー: %s", exc)
        csv_results = {}

    # 3. 安全環境変数チェック
    safety_warnings = check_safety_env()
    for w in safety_warnings:
        logger.warning("⚠️  安全警告: %s", w)

    summary = {
        "csv_initialized": csv_results,
        "safety_warnings": safety_warnings,
        "app_env": os.getenv("APP_ENV", "development"),
        "trading_mode": os.getenv("TRADING_MODE", "demo_only"),
    }

    logger.info("=== 起動チェック完了: %s ===", summary)
    return summary
