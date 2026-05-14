"""データモデル定義（SQLiteスキーマ）"""
from __future__ import annotations

CREATE_APPROVAL_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS approval_history (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at            TEXT NOT NULL,
    symbol                TEXT NOT NULL,
    current_price         REAL,
    signal                TEXT NOT NULL,
    score                 INTEGER,
    daily_trend           TEXT,
    h4_trend              TEXT,
    h1_status             TEXT,
    rsi                   REAL,
    atr_value             REAL,
    atr_status            TEXT,
    recent_high           REAL,
    recent_low            REAL,
    entry_price           REAL,
    stop_loss             REAL,
    take_profit           REAL,
    risk_reward           REAL,
    economic_event_warning INTEGER DEFAULT 0,
    economic_event_name   TEXT,
    ai_comment            TEXT,
    human_action          TEXT NOT NULL,
    notes                 TEXT,
    is_dummy_data         INTEGER DEFAULT 0,
    skip_reasons          TEXT,
    outcome               TEXT,
    exit_price            REAL,
    closed_at             TEXT,
    pnl_pips              REAL
);
"""

# Phase 12: デモ注文履歴テーブル（approval_historyとは完全に独立）
CREATE_DEMO_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS demo_orders (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at            TEXT NOT NULL,
    approval_id           INTEGER NOT NULL,
    symbol                TEXT NOT NULL,
    direction             TEXT NOT NULL,
    units                 INTEGER NOT NULL,
    entry_price           REAL,
    stop_loss             REAL,
    take_profit           REAL,
    oanda_trade_id        TEXT,
    oanda_order_id        TEXT,
    filled_price          REAL,
    status                TEXT DEFAULT 'open',
    notes                 TEXT,
    exit_price            REAL,
    pnl_pips              REAL,
    closed_at             TEXT,
    FOREIGN KEY (approval_id) REFERENCES approval_history(id)
);
"""

# Phase 13: 既存demo_ordersへの損益追跡列マイグレーション
MIGRATE_ADD_DEMO_ORDER_PNL_COLUMNS = [
    "ALTER TABLE demo_orders ADD COLUMN exit_price REAL",
    "ALTER TABLE demo_orders ADD COLUMN pnl_pips REAL",
    "ALTER TABLE demo_orders ADD COLUMN closed_at TEXT",
]

# Phase 10: 既存DBへのマイグレーション（列が既に存在する場合はエラーを無視）
MIGRATE_ADD_OUTCOME_COLUMNS = [
    "ALTER TABLE approval_history ADD COLUMN outcome TEXT",
    "ALTER TABLE approval_history ADD COLUMN exit_price REAL",
    "ALTER TABLE approval_history ADD COLUMN closed_at TEXT",
    "ALTER TABLE approval_history ADD COLUMN pnl_pips REAL",
]

# 将来の価格追跡テーブル（拡張用）
CREATE_PRICE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS price_tracking (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id           INTEGER NOT NULL,
    tracked_at            TEXT NOT NULL,
    price                 REAL NOT NULL,
    pnl_pips              REAL,
    FOREIGN KEY (approval_id) REFERENCES approval_history(id)
);
"""
