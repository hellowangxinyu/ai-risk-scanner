"""SQLite 数据访问层：单文件库，WAL 模式，每次操作独立连接。"""
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL DEFAULT '本公司',
    name TEXT NOT NULL,
    ctype TEXT NOT NULL DEFAULT '公司',
    credit_code TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    last_scan_at TEXT NOT NULL DEFAULT '',
    last_risk_level TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(org, name)
);
CREATE TABLE IF NOT EXISTS scan_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    total INTEGER NOT NULL DEFAULT 0,
    risk_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT '待运行',
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    search_count INTEGER NOT NULL DEFAULT 0,
    price_in REAL NOT NULL DEFAULT 0,
    price_out REAL NOT NULL DEFAULT 0,
    price_search REAL NOT NULL DEFAULT 0,
    est_cost REAL NOT NULL DEFAULT 0,
    trigger_type TEXT NOT NULL DEFAULT '手动',
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS scan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    customer_id INTEGER,
    customer_name TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT '待处理',
    fail_reason TEXT NOT NULL DEFAULT '',
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    searched INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS risk_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    customer_id INTEGER,
    customer_name TEXT NOT NULL,
    risk_type TEXT NOT NULL,
    level TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    risk_date TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_scan_items_batch ON scan_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_risk_records_batch ON risk_records(batch_id);
CREATE INDEX IF NOT EXISTS idx_risk_records_customer ON risk_records(customer_id);
"""

DEFAULT_SETTINGS = {
    "default_org": "本公司",
    "ai_base_url": "https://api.deepseek.com/v1",
    "ai_api_key": "",
    "ai_model": "deepseek-chat",
    "search_enabled": "0",
    "search_api_key": "",
    "cycle_high": "3",
    "cycle_mid": "7",
    "cycle_low": "30",
    "auto_scan_enabled": "0",
    "auto_scan_time": "02:00",
    "price_in": "4",
    "price_out": "9",
    "price_search": "0.036",
    "datasource": "llm",
    "last_auto_scan_date": "",
}


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, str(v))
            )
        conn.commit()
    finally:
        conn.close()


def get_settings() -> dict:
    conn = connect()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    finally:
        conn.close()
    s = dict(DEFAULT_SETTINGS)
    for r in rows:
        s[r["key"]] = r["value"]
    return s


def update_settings(values: dict):
    conn = connect()
    try:
        for k, v in values.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, str(v)),
            )
        conn.commit()
    finally:
        conn.close()


def mark_interrupted():
    """启动时把上次进程遗留的未完成批次标记为中断。"""
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE scan_batches SET status='中断', "
            "note=note || '进程重启，扫描中断。' "
            "WHERE status IN ('待运行','运行中')"
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
