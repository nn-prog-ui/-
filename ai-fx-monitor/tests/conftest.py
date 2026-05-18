"""テスト共通フィクスチャ。

HTTPインテグレーションテストで FastAPI アプリが使うデフォルト DB を
セッション開始時に初期化する。
"""
import pytest
from app.database.db import init_db, DB_PATH


@pytest.fixture(scope="session", autouse=True)
def ensure_db_initialized():
    """デフォルトDBが初期化済みであることを保証する。

    on_event("startup") はテストでは実行されないため、
    明示的に init_db() を呼び出してスキーマとマイグレーションを適用する。
    """
    init_db(DB_PATH)
