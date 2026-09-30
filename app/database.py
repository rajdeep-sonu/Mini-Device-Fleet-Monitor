"""SQLite database initialisation and access."""

import sqlite3
from contextlib import contextmanager
from typing import Generator

from app.config import DATABASE_PATH, DEFAULT_DEVICES

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS devices (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    last_heartbeat TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection() -> sqlite3.Connection:
    """Return a new connection with row-factory enabled."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a connection and commits on success."""
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
    """Create tables and seed sample devices if the table is empty."""
    with get_db() as conn:
        conn.execute(_CREATE_TABLE)
        count = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO devices (id, name) VALUES (?, ?)",
                [(d["id"], d["name"]) for d in DEFAULT_DEVICES],
            )
