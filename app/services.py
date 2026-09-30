"""Business logic for device registration, heartbeat recording, and status evaluation."""

from datetime import datetime, timezone
from typing import Any, Optional

from app.config import HEARTBEAT_TIMEOUT_SECONDS
from app.database import get_db


def _utc_now() -> str:
    """Return current UTC time as an ISO-8601 string with UTC indicator."""
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(iso_str: str) -> datetime:
    """Parse an ISO-8601 string reliably across all Python versions (including 3.10)."""
    clean_str = iso_str.strip()
    if clean_str.endswith("Z") or clean_str.endswith("z"):
        clean_str = clean_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(clean_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _seconds_since(iso_timestamp: str | None) -> float | None:
    """Return seconds elapsed since the given ISO-8601 timestamp, or None."""
    if iso_timestamp is None:
        return None
    try:
        dt = _parse_iso(iso_timestamp)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return None


def _compute_status(last_heartbeat: str | None) -> str:
    """Determine ONLINE / OFFLINE based on recency of the latest received heartbeat.

    A device is:
    - ONLINE if its last heartbeat was received within HEARTBEAT_TIMEOUT_SECONDS (30s)
    - OFFLINE if no heartbeat has been received for more than 30s or never
    """
    elapsed = _seconds_since(last_heartbeat)
    if elapsed is None:
        return "OFFLINE"
    return "ONLINE" if elapsed <= HEARTBEAT_TIMEOUT_SECONDS else "OFFLINE"


def _device_row_to_dict(row: Any) -> dict:
    """Convert a sqlite3.Row to a dictionary with computed status and elapsed time."""
    keys = row.keys() if hasattr(row, "keys") else []
    last_hb = row["last_heartbeat"] if "last_heartbeat" in keys else None
    elapsed = _seconds_since(last_hb)
    return {
        "id": row["id"],
        "name": row["name"],
        "status": _compute_status(last_hb),
        "last_heartbeat": last_hb,
        "seconds_since_heartbeat": round(elapsed, 1) if elapsed is not None else None,
        "device_timestamp": row["device_timestamp"] if "device_timestamp" in keys else None,
        "device_status": row["device_status"] if "device_status" in keys else None,
        "cpu_usage": row["cpu_usage"] if "cpu_usage" in keys else None,
        "signal_strength": row["signal_strength"] if "signal_strength" in keys else None,
        "created_at": row["created_at"],
    }


# ── Public API ──────────────────────────────────────────────────────────


def register_device(device_id: str, name: str) -> dict | None:
    """Register a new device.

    Returns the device dict, or None if the device ID is already registered.
    """
    now = _utc_now()
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM devices WHERE id = ?", (device_id,)).fetchone()
        if existing is not None:
            return None  # duplicate ID
        conn.execute(
            """
            INSERT INTO devices (id, name, created_at)
            VALUES (?, ?, ?)
            """,
            (device_id, name, now),
        )
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return _device_row_to_dict(row)


def list_devices(status_filter: Optional[str] = None) -> list[dict]:
    """Return all devices with computed status.

    Optionally filters by status ('ONLINE' or 'OFFLINE').
    """
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY id").fetchall()
    devices = [_device_row_to_dict(r) for r in rows]

    if status_filter:
        norm = status_filter.upper()
        devices = [d for d in devices if d["status"] == norm]

    return devices


def get_device(device_id: str) -> dict | None:
    """Return a single device by ID, or None if not found."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if row is None:
        return None
    return _device_row_to_dict(row)


def record_heartbeat(
    device_id: str,
    device_timestamp: Optional[str] = None,
    device_status: Optional[str] = None,
    cpu_usage: Optional[float] = None,
    signal_strength: Optional[float] = None,
) -> dict | None:
    """Record a heartbeat for the given device.

    IMPORTANT: To ensure accurate fleet monitoring, `last_heartbeat` is ALWAYS set
    to the server's current reception time. The client-provided `timestamp` is stored
    separately in `device_timestamp` for diagnostics, preventing device clock skew
    or stale historical timestamps from falsely marking a fresh device as OFFLINE.

    Returns updated device dict, or None if device ID is unknown.
    """
    server_now = _utc_now()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM devices WHERE id = ?", (device_id,)).fetchone()
        if row is None:
            return None

        conn.execute(
            """
            UPDATE devices
            SET last_heartbeat = ?,
                device_timestamp = COALESCE(?, device_timestamp),
                device_status = COALESCE(?, device_status),
                cpu_usage = COALESCE(?, cpu_usage),
                signal_strength = COALESCE(?, signal_strength)
            WHERE id = ?
            """,
            (server_now, device_timestamp, device_status, cpu_usage, signal_strength, device_id),
        )
        updated = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return _device_row_to_dict(updated)


def fleet_summary() -> dict:
    """Return aggregate counts: total, online, offline."""
    devices = list_devices()
    online = sum(1 for d in devices if d["status"] == "ONLINE")
    return {
        "total": len(devices),
        "online": online,
        "offline": len(devices) - online,
    }
