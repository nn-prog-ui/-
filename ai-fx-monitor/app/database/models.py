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
    skip_reasons          TEXT
);
"""

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
