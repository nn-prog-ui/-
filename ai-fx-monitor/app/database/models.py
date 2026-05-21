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

# Phase 22: アプリ設定テーブル（Web画面から変更可能な設定）
CREATE_APP_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
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

# Phase 34: トレードジャーナルテーブル
CREATE_TRADE_JOURNAL_TABLE = """
CREATE TABLE IF NOT EXISTS trade_journal (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id   INTEGER NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    notes         TEXT,
    tags          TEXT,
    entry_type    TEXT DEFAULT 'その他',
    emotion_score INTEGER DEFAULT 3,
    FOREIGN KEY (approval_id) REFERENCES approval_history(id)
);
"""

# Phase 33: カスタムアラートテーブル
CREATE_ALERTS_TABLE = """
CREATE TABLE IF NOT EXISTS alerts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    label             TEXT NOT NULL,
    condition_type    TEXT NOT NULL,
    condition_value   TEXT NOT NULL,
    active            INTEGER DEFAULT 1,
    cooldown_minutes  INTEGER DEFAULT 60,
    last_triggered_at TEXT
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

# Phase 39: 経済指標カレンダー
CREATE_ECONOMIC_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS economic_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    event_dt    TEXT NOT NULL,
    currency    TEXT NOT NULL,
    importance  TEXT NOT NULL DEFAULT 'MEDIUM',
    event_name  TEXT NOT NULL,
    note        TEXT
);
"""

# Phase 41: Web Push 購読情報
CREATE_PUSH_SUBSCRIPTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    endpoint    TEXT NOT NULL UNIQUE,
    p256dh      TEXT NOT NULL,
    auth        TEXT NOT NULL,
    user_agent  TEXT
);
"""

# Phase 54: 月次・週次目標管理
CREATE_GOALS_TABLE = """
CREATE TABLE IF NOT EXISTS trade_goals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    period_type  TEXT NOT NULL,   -- 'monthly' or 'weekly'
    period_label TEXT NOT NULL,   -- '2026-01' or '2026-W03'
    target_pips  REAL NOT NULL,
    symbol       TEXT NOT NULL DEFAULT '',  -- '' = 全通貨ペア
    note         TEXT,
    UNIQUE(period_type, period_label, symbol)
);
"""

# Phase 62: 世界経済イベントログ
CREATE_MACRO_EVENT_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS macro_event_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    event_date     TEXT NOT NULL,
    event_type     TEXT NOT NULL,   -- FOMC / NFP / CPI / 政策発表 / 地政学リスク / その他
    title          TEXT NOT NULL,
    description    TEXT,
    usd_forecast   TEXT NOT NULL DEFAULT 'neutral',  -- bullish / bearish / neutral
    actual_result  TEXT,            -- 実際に起きたこと（後から記録）
    notes          TEXT
);
"""
