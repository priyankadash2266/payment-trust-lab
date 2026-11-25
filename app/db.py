"""Database access: deliberately small, SQLite-backed and dependency-free."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get('FRAUD_LAB_DB', ROOT / 'fraud_lab.sqlite3'))

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    member_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    product_flow TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('success','pending','failed')),
    device_new INTEGER NOT NULL CHECK(device_new IN (0,1)),
    payments_last_hour INTEGER NOT NULL CHECK(payments_last_hour >= 0),
    device_age_days INTEGER NOT NULL CHECK(device_age_days >= 0)
);
CREATE INDEX IF NOT EXISTS idx_payments_day ON payments(created_at);
CREATE INDEX IF NOT EXISTS idx_payments_member ON payments(member_id, created_at);
CREATE TABLE IF NOT EXISTS payment_events (
    event_id TEXT PRIMARY KEY,
    payment_id TEXT NOT NULL REFERENCES payments(payment_id),
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_payment ON payment_events(payment_id,occurred_at);
CREATE TABLE IF NOT EXISTS complaints (
    complaint_id TEXT PRIMARY KEY,
    payment_id TEXT NOT NULL REFERENCES payments(payment_id),
    member_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_complaints_payment ON complaints(payment_id);
CREATE INDEX IF NOT EXISTS idx_complaints_created ON complaints(created_at DESC);
CREATE TABLE IF NOT EXISTS outcomes (
    payment_id TEXT PRIMARY KEY REFERENCES payments(payment_id),
    outcome TEXT NOT NULL CHECK(outcome IN ('confirmed_fraud','genuine','unresolved')),
    available_at TEXT,
    confirmed_net_loss_paise INTEGER NOT NULL DEFAULT 0 CHECK(confirmed_net_loss_paise >= 0),
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dispositions (
    disposition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT NOT NULL REFERENCES complaints(complaint_id),
    status TEXT NOT NULL CHECK(status IN ('confirmed_fraud','genuine')),
    decided_at TEXT NOT NULL,
    rationale TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_disposition_case ON dispositions(complaint_id, disposition_id DESC);
"""

def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 5000')
    return connection

def initialize(connection):
    connection.executescript(SCHEMA)


@contextmanager
def session():
    """Short-lived SQLite unit of work; commits on success and always closes."""
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
