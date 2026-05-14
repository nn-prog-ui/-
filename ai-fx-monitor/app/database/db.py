"""SQLiteデータベース接続・初期化"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import DB_PATH
from app.database.models import (
    CREATE_APPROVAL_HISTORY_TABLE,
    CREATE_DEMO_ORDERS_TABLE,
    CREATE_PRICE_TRACKING_TABLE,
    MIGRATE_ADD_OUTCOME_COLUMNS,
)


def init_db(db_path: Path | None = None) -> None:
    """DBを初期化してテーブルを作成する。"""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.execute(CREATE_APPROVAL_HISTORY_TABLE)
        conn.execute(CREATE_PRICE_TRACKING_TABLE)
        conn.execute(CREATE_DEMO_ORDERS_TABLE)  # Phase 12
        # Phase 10 migration: outcome列などを追加（既存列は無視）
        for sql in MIGRATE_ADD_OUTCOME_COLUMNS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # 列が既に存在する場合は無視
        conn.commit()


@contextmanager
def get_db(db_path: Path | None = None):
    """DB接続のコンテキストマネージャー。"""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
