"""SQLite database setup and helpers."""
import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "warehouse.db"


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15.0)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db_cursor():
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    supplier TEXT,
    location TEXT,
    physical_stock INTEGER DEFAULT 0,
    reserved_stock INTEGER DEFAULT 0,
    damaged_stock INTEGER DEFAULT 0,
    min_stock INTEGER DEFAULT 0,
    safety_stock INTEGER DEFAULT 0,
    reorder_level INTEGER DEFAULT 0,
    avg_daily_demand REAL DEFAULT 0,
    unit_price REAL DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS inventory_history (
    id TEXT PRIMARY KEY,
    product_id TEXT,
    type TEXT,
    delta INTEGER,
    reason TEXT,
    location TEXT,
    at TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    order_no TEXT UNIQUE,
    customer_name TEXT,
    customer_email TEXT,
    customer_priority TEXT DEFAULT 'NORMAL',
    required_by TEXT,
    order_value REAL DEFAULT 0,
    status TEXT DEFAULT 'CREATED',
    priority TEXT DEFAULT 'MEDIUM',
    priority_score INTEGER DEFAULT 0,
    priority_reasons TEXT,
    risk_score INTEGER DEFAULT 0,
    risk_reasons TEXT,
    created_at TEXT,
    dispatched_at TEXT,
    on_hold INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS order_items (
    id TEXT PRIMARY KEY,
    order_id TEXT,
    product_id TEXT,
    quantity INTEGER,
    allocated INTEGER DEFAULT 0,
    picked INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    name TEXT,
    role TEXT,
    available INTEGER DEFAULT 1,
    workload INTEGER DEFAULT 0,
    efficiency INTEGER DEFAULT 90,
    current_task TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    order_id TEXT,
    stage TEXT,
    worker_id TEXT,
    status TEXT DEFAULT 'QUEUED',
    started_at TEXT,
    completed_at TEXT,
    route TEXT
);

CREATE TABLE IF NOT EXISTS exceptions (
    id TEXT PRIMARY KEY,
    type TEXT,
    severity TEXT,
    order_id TEXT,
    product_id TEXT,
    description TEXT,
    resolution TEXT,
    status TEXT DEFAULT 'OPEN',
    created_at TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    problem TEXT,
    severity TEXT,
    recommendation TEXT,
    reason TEXT,
    confidence INTEGER,
    impact TEXT,
    alternatives TEXT,
    status TEXT DEFAULT 'PENDING',
    result TEXT,
    predicted TEXT,
    actual TEXT,
    created_at TEXT,
    applied_at TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    event_key TEXT,
    type TEXT,
    severity TEXT,
    title TEXT,
    body TEXT,
    entity_type TEXT,
    entity_id TEXT,
    meta TEXT,
    recommended_action TEXT,
    status TEXT DEFAULT 'ACTIVE',
    desktop_status TEXT DEFAULT '-',
    email_status TEXT DEFAULT '-',
    whatsapp_status TEXT DEFAULT '-',
    channel TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS activity (
    id TEXT PRIMARY KEY,
    kind TEXT,
    message TEXT,
    entity_type TEXT,
    entity_id TEXT,
    meta TEXT,
    at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    who TEXT,
    action TEXT,
    entity_type TEXT,
    entity_id TEXT,
    old_value TEXT,
    new_value TEXT,
    at TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
    id TEXT PRIMARY KEY,
    alert_id TEXT,
    channel TEXT,
    recipient TEXT,
    subject TEXT,
    body TEXT,
    severity TEXT,
    status TEXT,
    provider_message_id TEXT,
    error_message TEXT,
    created_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS product_qr_snapshots (
    product_id TEXT PRIMARY KEY,
    snapshot_version INTEGER DEFAULT 1,
    generated_at TEXT,
    snapshot_payload TEXT,
    snapshot_usable_stock INTEGER DEFAULT 0,
    snapshot_status TEXT,
    snapshot_location TEXT,
    snapshot_action TEXT,
    is_stale INTEGER DEFAULT 0,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# Columns added after the initial release — applied via ALTER TABLE so
# existing SQLite files (like a warehouse.db already on disk) get migrated
# forward instead of silently missing the new fields.
_MIGRATIONS = {
    "orders": [
        ("customer_email", "TEXT"),
    ],
    "alerts": [
        ("event_key", "TEXT"),
        ("entity_type", "TEXT"),
        ("meta", "TEXT"),
        ("recommended_action", "TEXT"),
        ("status", "TEXT DEFAULT 'ACTIVE'"),
        ("desktop_status", "TEXT DEFAULT '-'"),
        ("email_status", "TEXT DEFAULT '-'"),
        ("whatsapp_status", "TEXT DEFAULT '-'"),
        ("updated_at", "TEXT"),
        ("resolved_at", "TEXT"),
    ],
    "outbox": [
        ("alert_id", "TEXT"),
        ("provider_message_id", "TEXT"),
        ("error_message", "TEXT"),
        ("sent_at", "TEXT"),
    ],
}


def _run_migrations(cur):
    for table, cols in _MIGRATIONS.items():
        cur.execute(f"PRAGMA table_info({table})")
        existing = {r["name"] for r in cur.fetchall()}
        for name, coltype in cols:
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")


DEFAULT_SETTINGS = {
    # general
    "warehouse_name": "Central DC — Mumbai",
    "automation_enabled": "true",
    "user_active": "true",
    "user_inactivity_threshold_minutes": "5",
    "desktop_notifications_enabled": "true",
    # email & company contact (Supports Twilio Comms Email API, SendGrid & SMTP)
    "automatic_email_enabled": "true",
    "email_provider": "twilio_email",
    "twilio_email_from": "AC0a3b0b783c383ace8cb92e43b98a7696@twilio.email",
    "twilio_sendgrid_api_key": "",
    "company_name": "ABC Warehouse",
    "company_email": "manager@warehouse.com",
    "sender_email": "operations@warehouse-autopilot.internal",
    "email_recipient": "manager@warehouse.com",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_username": "",
    "smtp_password": "",
    "email_rule_critical_shortage": "true",
    "email_rule_critical_order_risk": "true",
    "email_rule_oos_order": "true",
    "email_rule_projected_stockout": "true",
    "email_rule_high_value_risk": "true",
    "email_rule_major_loss": "true",
    "email_rule_low_stock": "false",
    "email_rule_startup_digest": "true",
    # automatic order & supplier po settings
    "auto_reorder_email_enabled": "true",
    "supplier_po_recipient": "supplier-orders@logistics-hub.com",
    "supplier_po_template_subject": "AUTOMATED PURCHASE ORDER: Urgent Restock Request",
    "supplier_po_template_body": "Automated reorder request triggered by Warehouse Autopilot due to low/critical inventory.",
    # whatsapp
    "automatic_whatsapp_enabled": "true",
    "whatsapp_number": "+918019753996",
    "twilio_account_sid": "",
    "twilio_auth_token": "",
    "twilio_whatsapp_from": "whatsapp:+17372508034",
    "twilio_content_sid": "HXfe5ab5f00277942d4d4200328b4d403c",
    "whatsapp_rule_critical_shortage": "true",
    "whatsapp_rule_cannot_fulfill": "true",
    "whatsapp_rule_critical_order_risk": "true",
    "whatsapp_rule_high_value_risk": "true",
    "whatsapp_rule_major_loss": "true",
    "whatsapp_rule_low_stock": "false",
    "whatsapp_rule_startup_digest": "true",
    "whatsapp_rule_demo_reset": "true",
}


def init_db():
    with db_cursor() as cur:
        cur.executescript(SCHEMA)
        _run_migrations(cur)
        for k, v in DEFAULT_SETTINGS.items():
            cur.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?,?)", (k, v)
            )


def get_setting(key: str, default=None):
    with db_cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default


def env_or_setting(env_key: str, setting_key: str, default=None):
    """Prefer an environment variable (secure) over a value stored in SQLite."""
    v = os.environ.get(env_key)
    if v:
        return v
    return get_setting(setting_key, default)


def set_setting(key: str, value: str):
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
