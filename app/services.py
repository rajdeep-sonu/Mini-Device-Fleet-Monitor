"""Business logic for device status and heartbeat processing."""

from datetime import datetime, timezone
from typing import Any

from app.config import HEARTBEAT_TIMEOUT_SECONDS
from app.database import get_db


def _utc_now() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _seconds_since(iso_timestamp: str | None) -> float | None:
    """Return seconds elapsed since the given ISO-8601 timestamp, or None."""
    if iso_timestamp is None:
        return None
    dt = datetime.fromisoformat(iso_timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _compute_status(last_heartbeat: str | None) -> str:
    """Determine ONLINE / OFFLINE based on heartbeat recency."""
    elapsed = _seconds_since(last_heartbeat)
    if elapsed is None:
        return "OFFLINE"
    return "ONLINE" if elapsed <= HEARTBEAT_TIMEOUT_SECONDS else "OFFLINE"


def _device_row_to_dict(row: Any) -> dict:
    """Convert a sqlite3.Row to a rich device dict with computed fields."""
    last_hb = row["last_heartbeat"]
    elapsed = _seconds_since(last_hb)
    return {
        "id": row["id"],
        "name": row["name"],
        "status": _compute_status(last_hb),
        "last_heartbeat": last_hb,
        "seconds_since_heartbeat": round(elapsed, 1) if elapsed is not None else None,
        "created_at": row["created_at"],
    }


# ── Public API ──────────────────────────────────────────────────────────


def register_device(device_id: str, name: str) -> dict | None:
    """Register a new device. Returns the device dict, or None if ID already exists."""
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM devices WHERE id = ?", (device_id,)).fetchone()
        if existing is not None:
            return None  # duplicate
        conn.execute(
            "INSERT INTO devices (id, name) VALUES (?, ?)",
            (device_id, name),
        )
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return _device_row_to_dict(row)


def list_devices() -> list[dict]:
    """Return all devices with computed status."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY id").fetchall()
    return [_device_row_to_dict(r) for r in rows]


def get_device(device_id: str) -> dict | None:
    """Return a single device or None if not found."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if row is None:
        return None
    return _device_row_to_dict(row)


def record_heartbeat(device_id: str, timestamp: str | None = None, status: str | None = None) -> dict | None:
    """Record a heartbeat for the given device.

    If timestamp is provided (ISO-8601), it is used as the heartbeat time.
    Otherwise the current UTC time is used.
    Returns updated device dict, or None if device not found.
    """
    hb_time = timestamp if timestamp else _utc_now()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE devices SET last_heartbeat = ? WHERE id = ?",
            (hb_time, device_id),
        )
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return _device_row_to_dict(row)


def fleet_summary() -> dict:
    """Return aggregate counts: total, online, offline."""
    devices = list_devices()
    online = sum(1 for d in devices if d["status"] == "ONLINE")
    return {
        "total": len(devices),
        "online": online,
        "offline": len(devices) - online,
    }
