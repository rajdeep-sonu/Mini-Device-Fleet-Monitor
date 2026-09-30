"""Tests for the Mini Device Fleet Monitor API.

Each test uses a fresh temporary SQLite database so tests are isolated.
"""

import time
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

import app.config as config
import app.database as database
from app.main import app


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Point the app at a temporary SQLite DB and initialise it."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    import app.services as svc
    monkeypatch.setattr(svc, "get_db", database.get_db)
    database.init_db()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ── Device registration ────────────────────────────────────────────────


def test_register_device(client):
    resp = client.post("/devices", json={"id": "dev-new", "name": "New Device"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "dev-new"
    assert data["name"] == "New Device"
    assert data["status"] == "OFFLINE"  # no heartbeat yet


def test_register_duplicate_device(client):
    client.post("/devices", json={"id": "dup-01", "name": "First"})
    resp = client.post("/devices", json={"id": "dup-01", "name": "Second"})
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_register_device_empty_id(client):
    resp = client.post("/devices", json={"id": "", "name": "No ID"})
    assert resp.status_code == 400


def test_register_device_missing_fields(client):
    resp = client.post("/devices", json={"id": "x"})
    assert resp.status_code == 422  # Pydantic validation


# ── Device listing ─────────────────────────────────────────────────────


def test_list_devices_returns_all_sample_devices(client):
    resp = client.get("/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    ids = [d["id"] for d in data]
    assert "device-001" in ids


# ── Heartbeat ──────────────────────────────────────────────────────────


def test_heartbeat_success(client):
    resp = client.post("/devices/device-001/heartbeat", json={"status": "OK"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Heartbeat recorded"
    assert body["device"]["id"] == "device-001"
    assert body["device"]["last_heartbeat"] is not None


def test_heartbeat_with_timestamp(client):
    ts = "2026-09-21T10:30:00Z"
    resp = client.post("/devices/device-001/heartbeat", json={"timestamp": ts, "status": "OK"})
    assert resp.status_code == 200
    assert resp.json()["device"]["last_heartbeat"] == ts


def test_heartbeat_with_extra_fields(client):
    """The spec says extra fields like cpu_usage are allowed."""
    resp = client.post(
        "/devices/device-001/heartbeat",
        json={"status": "OK", "cpu_usage": 42, "signal_strength": -71},
    )
    assert resp.status_code == 200


def test_heartbeat_unknown_device(client):
    resp = client.post("/devices/unknown-999/heartbeat", json={"status": "OK"})
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ── Device status (ONLINE / OFFLINE) ───────────────────────────────────


def test_fresh_heartbeat_is_online(client):
    client.post("/devices/device-002/heartbeat", json={"status": "OK"})
    resp = client.get("/devices/device-002")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ONLINE"


def test_stale_heartbeat_is_offline(client):
    """A heartbeat older than the timeout should result in OFFLINE."""
    stale_time = (
        datetime.now(timezone.utc) - timedelta(seconds=config.HEARTBEAT_TIMEOUT_SECONDS + 5)
    ).isoformat()
    with database.get_db() as conn:
        conn.execute("UPDATE devices SET last_heartbeat = ? WHERE id = ?", (stale_time, "device-001"))
    resp = client.get("/devices/device-001")
    assert resp.status_code == 200
    assert resp.json()["status"] == "OFFLINE"


def test_device_no_heartbeat_is_offline(client):
    resp = client.get("/devices/device-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "OFFLINE"
    assert data["last_heartbeat"] is None
    assert data["seconds_since_heartbeat"] is None


# ── Multiple devices ──────────────────────────────────────────────────


def test_multiple_devices_independent_status(client):
    client.post("/devices/device-001/heartbeat", json={"status": "OK"})
    resp = client.get("/devices")
    devices = {d["id"]: d for d in resp.json()}
    assert devices["device-001"]["status"] == "ONLINE"
    assert devices["device-002"]["status"] == "OFFLINE"


# ── Latest heartbeat tracking ─────────────────────────────────────────


def test_latest_heartbeat_tracked(client):
    client.post("/devices/device-003/heartbeat", json={"status": "OK"})
    time.sleep(0.1)
    client.post("/devices/device-003/heartbeat", json={"status": "OK"})
    resp = client.get("/devices/device-003")
    data = resp.json()
    assert data["seconds_since_heartbeat"] is not None
    assert data["seconds_since_heartbeat"] < 2


# ── Unknown device ────────────────────────────────────────────────────


def test_get_unknown_device_returns_404(client):
    resp = client.get("/devices/does-not-exist")
    assert resp.status_code == 404


# ── Fleet summary ─────────────────────────────────────────────────────


def test_fleet_summary_counts(client):
    for did in ("device-001", "device-002", "device-004"):
        client.post(f"/devices/{did}/heartbeat", json={"status": "OK"})
    resp = client.get("/summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total"] == 5
    assert summary["online"] == 3
    assert summary["offline"] == 2


# ── Status transitions ────────────────────────────────────────────────


def test_heartbeat_updates_status_from_offline_to_online(client):
    assert client.get("/devices/device-004").json()["status"] == "OFFLINE"
    client.post("/devices/device-004/heartbeat", json={"status": "OK"})
    assert client.get("/devices/device-004").json()["status"] == "ONLINE"


def test_30_second_timeout_boundary(client):
    """Heartbeat just inside the timeout should be ONLINE; just outside should be OFFLINE."""
    # 1 second inside the boundary → ONLINE
    inside = (
        datetime.now(timezone.utc) - timedelta(seconds=config.HEARTBEAT_TIMEOUT_SECONDS - 1)
    ).isoformat()
    with database.get_db() as conn:
        conn.execute("UPDATE devices SET last_heartbeat = ? WHERE id = ?", (inside, "device-001"))
    resp = client.get("/devices/device-001")
    assert resp.json()["status"] == "ONLINE"

    # 1 second outside the boundary → OFFLINE
    outside = (
        datetime.now(timezone.utc) - timedelta(seconds=config.HEARTBEAT_TIMEOUT_SECONDS + 1)
    ).isoformat()
    with database.get_db() as conn:
        conn.execute("UPDATE devices SET last_heartbeat = ? WHERE id = ?", (outside, "device-001"))
    resp = client.get("/devices/device-001")
    assert resp.json()["status"] == "OFFLINE"
