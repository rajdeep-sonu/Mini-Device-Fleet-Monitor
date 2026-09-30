"""Comprehensive API test suite for Mini Device Fleet Monitor.

Each test executes against an isolated temporary SQLite database.
Validates all functional requirements, 30s timeout boundary, validation,
error codes, and concurrent execution.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

import app.database as database
from app.main import app


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Provide a fresh SQLite database for every single test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    database.init_db()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ── 1. Initial State & Seeding Verification ───────────────────────────


def test_fleet_initially_empty(client):
    """Fleet must start empty without pre-seeded devices."""
    resp = client.get("/devices")
    assert resp.status_code == 200
    assert resp.json() == []

    summary = client.get("/summary").json()
    assert summary == {"total": 0, "online": 0, "offline": 0}


# ── 2. Device Registration ────────────────────────────────────────────


def test_register_device_success(client):
    resp = client.post("/devices", json={"id": "device-01", "name": "Lab Device 01"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "device-01"
    assert data["name"] == "Lab Device 01"
    assert data["status"] == "OFFLINE"
    assert data["last_heartbeat"] is None
    assert data["seconds_since_heartbeat"] is None
    assert "T" in data["created_at"]  # ISO-8601 formatted


def test_register_duplicate_device_returns_409(client):
    client.post("/devices", json={"id": "device-dup", "name": "Initial Device"})
    resp = client.post("/devices", json={"id": "device-dup", "name": "Duplicate ID"})
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"].lower()


def test_register_invalid_id_characters_returns_422(client):
    # IDs with spaces or illegal symbols are rejected
    resp = client.post("/devices", json={"id": "dev 01!", "name": "Invalid ID Device"})
    assert resp.status_code == 422


def test_register_empty_name_returns_422(client):
    resp = client.post("/devices", json={"id": "dev-empty", "name": "   "})
    assert resp.status_code == 422


# ── 3. Heartbeat Processing & Brief Exact Example ─────────────────────


def test_heartbeat_unknown_device_returns_404(client):
    resp = client.post("/devices/unknown-device/heartbeat", json={"status": "OK"})
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_heartbeat_brief_exact_example_shows_online(client):
    """Sending the brief's exact example body MUST show ONLINE.

    The brief specifies:
        POST /devices/{id}/heartbeat
        {"timestamp": "2026-09-21T10:30:00Z", "status": "OK"}
    Even though 2026-09-21 is in the past, the server MUST track reception time
    for status, keeping the reported timestamp in device_timestamp.
    """
    client.post("/devices", json={"id": "device-brief", "name": "Brief Device"})

    resp = client.post(
        "/devices/device-brief/heartbeat",
        json={"timestamp": "2026-09-21T10:30:00Z", "status": "OK"},
    )
    assert resp.status_code == 200
    device = resp.json()["device"]

    # Status must be ONLINE right after receipt
    assert device["status"] == "ONLINE"
    assert device["device_timestamp"] == "2026-09-21T10:30:00Z"
    assert device["device_status"] == "OK"
    assert device["seconds_since_heartbeat"] is not None
    assert device["seconds_since_heartbeat"] < 2.0

    # GET /devices should also show ONLINE
    get_resp = client.get("/devices/device-brief")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "ONLINE"


def test_heartbeat_with_diagnostic_metrics(client):
    """Heartbeat supports cpu_usage and signal_strength, saving them to DB."""
    client.post("/devices", json={"id": "device-metrics", "name": "Metrics Device"})

    resp = client.post(
        "/devices/device-metrics/heartbeat",
        json={
            "status": "OK",
            "cpu_usage": 42.5,
            "signal_strength": -71.0,
            "extra_field": "allowed",
        },
    )
    assert resp.status_code == 200
    device = resp.json()["device"]
    assert device["cpu_usage"] == 42.5
    assert device["signal_strength"] == -71.0


def test_heartbeat_malformed_timestamp_returns_422(client):
    client.post("/devices", json={"id": "dev-ts", "name": "TS Device"})
    resp = client.post(
        "/devices/dev-ts/heartbeat",
        json={"timestamp": "not-a-valid-date", "status": "OK"},
    )
    assert resp.status_code == 422


def test_heartbeat_timezoneless_timestamp_returns_422(client):
    """Timestamps without timezone information must be rejected with 422, not 500."""
    client.post("/devices", json={"id": "dev-ts2", "name": "TS Device 2"})
    resp = client.post(
        "/devices/dev-ts2/heartbeat",
        json={"timestamp": "2026-09-21 10:30:00", "status": "OK"},
    )
    assert resp.status_code == 422


def test_heartbeat_invalid_cpu_usage_returns_422(client):
    client.post("/devices", json={"id": "dev-cpu", "name": "CPU Device"})
    # CPU usage > 100
    resp = client.post("/devices/dev-cpu/heartbeat", json={"cpu_usage": 150.0})
    assert resp.status_code == 422


def test_heartbeat_invalid_signal_strength_returns_422(client):
    client.post("/devices", json={"id": "dev-sig", "name": "Sig Device"})
    # Positive signal strength is invalid (dBm is negative)
    resp = client.post("/devices/dev-sig/heartbeat", json={"signal_strength": 10.0})
    assert resp.status_code == 422


# ── 4. 30-Second Timeout Rule & Status Transitions ────────────────────


def test_30_second_timeout_boundary_without_sleeping(client):
    """Validate ONLINE vs OFFLINE rule at the exact 30s threshold without sleeping.

    - within 30s (e.g. 29.5s ago) -> ONLINE
    - exceeding 30s (e.g. 30.5s ago) -> OFFLINE
    """
    client.post("/devices", json={"id": "dev-boundary", "name": "Boundary Device"})

    # 1. Heartbeat 29.5s ago -> within 30s -> ONLINE
    inside_time = (datetime.now(timezone.utc) - timedelta(seconds=29.5)).isoformat()
    with database.get_db() as conn:
        conn.execute("UPDATE devices SET last_heartbeat = ? WHERE id = ?", (inside_time, "dev-boundary"))

    resp = client.get("/devices/dev-boundary")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ONLINE"

    # 2. Heartbeat 30.5s ago -> exceeds 30s -> OFFLINE
    outside_time = (datetime.now(timezone.utc) - timedelta(seconds=30.5)).isoformat()
    with database.get_db() as conn:
        conn.execute("UPDATE devices SET last_heartbeat = ? WHERE id = ?", (outside_time, "dev-boundary"))

    resp = client.get("/devices/dev-boundary")
    assert resp.status_code == 200
    assert resp.json()["status"] == "OFFLINE"


def test_offline_transitions_to_online_on_heartbeat(client):
    """Device without heartbeat is OFFLINE; becomes ONLINE immediately on heartbeat."""
    client.post("/devices", json={"id": "dev-trans", "name": "Transition Device"})
    assert client.get("/devices/dev-trans").json()["status"] == "OFFLINE"

    client.post("/devices/dev-trans/heartbeat", json={"status": "OK"})
    assert client.get("/devices/dev-trans").json()["status"] == "ONLINE"


def test_aged_device_transitions_to_online_on_new_heartbeat(client):
    """A device whose heartbeat has aged past 30s transitions from OFFLINE back to ONLINE on a new heartbeat."""
    client.post("/devices", json={"id": "dev-reconnect", "name": "Reconnect Device"})
    client.post("/devices/dev-reconnect/heartbeat", json={"status": "OK"})
    assert client.get("/devices/dev-reconnect").json()["status"] == "ONLINE"

    # Age heartbeat past 30s (e.g. 45s ago)
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=45.0)).isoformat()
    with database.get_db() as conn:
        conn.execute("UPDATE devices SET last_heartbeat = ? WHERE id = ?", (past_time, "dev-reconnect"))

    assert client.get("/devices/dev-reconnect").json()["status"] == "OFFLINE"

    # New heartbeat arrives -> device transitions back to ONLINE
    resp = client.post("/devices/dev-reconnect/heartbeat", json={"status": "OK"})
    assert resp.status_code == 200
    assert client.get("/devices/dev-reconnect").json()["status"] == "ONLINE"


def test_multiple_devices_independent_status(client):
    """Each device maintains its own heartbeat status independently."""
    client.post("/devices", json={"id": "dev-a", "name": "Device A"})
    client.post("/devices", json={"id": "dev-b", "name": "Device B"})

    # dev-a receives heartbeat, dev-b does not
    client.post("/devices/dev-a/heartbeat", json={"status": "OK"})

    devs = {d["id"]: d for d in client.get("/devices").json()}
    assert devs["dev-a"]["status"] == "ONLINE"
    assert devs["dev-b"]["status"] == "OFFLINE"


# ── 5. Filtering and Summary APIs ─────────────────────────────────────


def test_fleet_summary_counts(client):
    client.post("/devices", json={"id": "d1", "name": "Device 1"})
    client.post("/devices", json={"id": "d2", "name": "Device 2"})
    client.post("/devices", json={"id": "d3", "name": "Device 3"})

    client.post("/devices/d1/heartbeat", json={"status": "OK"})
    client.post("/devices/d2/heartbeat", json={"status": "OK"})

    resp = client.get("/summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total"] == 3
    assert summary["online"] == 2
    assert summary["offline"] == 1


def test_summary_counts_device_offline_after_aging(client):
    """GET /summary dynamically reflects a device transitioning from ONLINE to OFFLINE after its heartbeat ages past 30s."""
    client.post("/devices", json={"id": "sum-1", "name": "Device Sum 1"})
    client.post("/devices", json={"id": "sum-2", "name": "Device Sum 2"})

    client.post("/devices/sum-1/heartbeat", json={"status": "OK"})
    client.post("/devices/sum-2/heartbeat", json={"status": "OK"})

    summary_before = client.get("/summary").json()
    assert summary_before == {"total": 2, "online": 2, "offline": 0}

    # Age sum-1 past 30s (e.g. 35s ago)
    aged_time = (datetime.now(timezone.utc) - timedelta(seconds=35.0)).isoformat()
    with database.get_db() as conn:
        conn.execute("UPDATE devices SET last_heartbeat = ? WHERE id = ?", (aged_time, "sum-1"))

    summary_after = client.get("/summary").json()
    assert summary_after == {"total": 2, "online": 1, "offline": 1}


def test_filter_devices_by_status(client):
    """GET /devices?status=ONLINE and ?status=OFFLINE filter results correctly."""
    client.post("/devices", json={"id": "on-1", "name": "Online 1"})
    client.post("/devices", json={"id": "off-1", "name": "Offline 1"})

    client.post("/devices/on-1/heartbeat", json={"status": "OK"})

    # Filter ONLINE
    online_resp = client.get("/devices?status=ONLINE")
    assert online_resp.status_code == 200
    online_list = online_resp.json()
    assert len(online_list) == 1
    assert online_list[0]["id"] == "on-1"

    # Filter OFFLINE (case insensitive)
    offline_resp = client.get("/devices?status=offline")
    assert offline_resp.status_code == 200
    offline_list = offline_resp.json()
    assert len(offline_list) == 1
    assert offline_list[0]["id"] == "off-1"

    # Invalid status filter
    bad_resp = client.get("/devices?status=UNKNOWN")
    assert bad_resp.status_code == 400


# ── 6. Concurrency Safety Test ────────────────────────────────────────


def test_concurrent_heartbeats(client):
    """Multiple threads sending heartbeats concurrently must succeed without SQLite lock errors."""
    # Register 5 devices
    for i in range(5):
        client.post("/devices", json={"id": f"conc-{i}", "name": f"Concurrent Device {i}"})

    def send_hb(dev_id: str):
        return client.post(f"/devices/{dev_id}/heartbeat", json={"status": "OK"})

    with ThreadPoolExecutor(max_workers=5) as executor:
        # 20 concurrent heartbeat requests distributed across devices
        tasks = [f"conc-{i % 5}" for i in range(20)]
        results = list(executor.map(send_hb, tasks))

    for r in results:
        assert r.status_code == 200

    summary = client.get("/summary").json()
    assert summary["total"] == 5
    assert summary["online"] == 5


def test_concurrent_duplicate_registration_returns_201_and_409(client):
    """Concurrent registrations for the same device ID must return only 201 (exactly once) and 409 (conflicts), never 500."""
    def register():
        return client.post("/devices", json={"id": "race-device", "name": "Race Device"})

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(register) for _ in range(32)]
        results = [f.result() for f in futures]

    statuses = [r.status_code for r in results]
    assert 500 not in statuses
    assert statuses.count(201) == 1
    assert statuses.count(409) == 31
    assert set(statuses) == {201, 409}
