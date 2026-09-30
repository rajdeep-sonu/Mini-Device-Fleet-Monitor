"""SQLite database initialisation and connection management."""

import sqlite3
from contextlib import contextmanager
from typing import Generator

from app.config import DATABASE_PATH

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS devices (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    last_heartbeat   TEXT,
    device_timestamp TEXT,
    device_status    TEXT,
    cpu_usage        REAL,
    signal_strength  REAL,
    created_at       TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row-factory and WAL mode enabled.

    WAL (Write-Ahead Logging) mode enables concurrent reads without blocking writes,
    allowing the API to query status while heartbeats are recorded concurrently.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding a per-request SQLite connection with automatic commit/rollback."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create database tables if they do not exist and ensure all columns exist.

    Fleet starts empty. Devices are registered via POST /devices.
    """
    with get_db() as conn:
        conn.execute(_CREATE_TABLE)
        # Ensure schema migrations apply smoothly if database file pre-exists
        cols = {row[1] for row in conn.execute("PRAGMA table_info(devices)").fetchall()}
        required = {
            "device_timestamp": "TEXT",
            "device_status": "TEXT",
            "cpu_usage": "REAL",
            "signal_strength": "REAL",
        }
        for col, col_type in required.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE devices ADD COLUMN {col} {col_type};")
