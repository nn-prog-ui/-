"""SQLiteデータベース接続・初期化"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import DB_PATH
from app.database.models import (
    CREATE_ALERTS_TABLE,
    CREATE_APP_SETTINGS_TABLE,
    CREATE_APPROVAL_HISTORY_TABLE,
    CREATE_DEMO_ORDERS_TABLE,
    CREATE_ECONOMIC_EVENTS_TABLE,
    CREATE_GOALS_TABLE,
    CREATE_MACRO_EVENT_LOG_TABLE,
    CREATE_PRICE_TRACKING_TABLE,
    CREATE_PUSH_SUBSCRIPTIONS_TABLE,
    CREATE_TRADE_JOURNAL_TABLE,
    CREATE_WEEKLY_REPORT_TABLE,
    MIGRATE_ADD_DEMO_ORDER_PNL_COLUMNS,
    MIGRATE_ADD_OUTCOME_COLUMNS,
)


def init_db(db_path: Path | None = None) -> None:
    """DBを初期化してテーブルを作成する。"""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.execute(CREATE_APPROVAL_HISTORY_TABLE)
        conn.execute(CREATE_PRICE_TRACKING_TABLE)
        conn.execute(CREATE_DEMO_ORDERS_TABLE)   # Phase 12
        conn.execute(CREATE_APP_SETTINGS_TABLE)  # Phase 22
        conn.execute(CREATE_ALERTS_TABLE)          # Phase 33
        conn.execute(CREATE_TRADE_JOURNAL_TABLE)   # Phase 34
        conn.execute(CREATE_ECONOMIC_EVENTS_TABLE)    # Phase 39
        conn.execute(CREATE_PUSH_SUBSCRIPTIONS_TABLE) # Phase 41
        conn.execute(CREATE_GOALS_TABLE)               # Phase 54
        conn.execute(CREATE_MACRO_EVENT_LOG_TABLE)     # Phase 62
        conn.execute(CREATE_WEEKLY_REPORT_TABLE)       # Phase 65
        # Phase 10 migration: outcome列などを追加（既存列は無視）
        for sql in MIGRATE_ADD_OUTCOME_COLUMNS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
        # Phase 13 migration: demo_ordersへの損益追跡列を追加
        for sql in MIGRATE_ADD_DEMO_ORDER_PNL_COLUMNS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
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
