"""FastAPI application – routes and lifecycle."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.database import init_db
from app import services, simulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-12s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("app")


# ── Request / response models ──────────────────────────────────────────


class DeviceRegisterRequest(BaseModel):
    id: str
    name: str


class HeartbeatRequest(BaseModel):
    timestamp: Optional[str] = None
    status: Optional[str] = None
    # Allow arbitrary extra fields (cpu_usage, signal_strength, etc.)
    model_config = {"extra": "allow"}


# ── Lifecycle ───────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB + start simulator. Shutdown: stop simulator."""
    init_db()
    logger.info("Database initialised")
    simulator.start()
    yield
    simulator.stop()
    logger.info("Shutdown complete")


app = FastAPI(title="Mini Device Fleet Monitor", lifespan=lifespan)

# ── API routes ──────────────────────────────────────────────────────────


@app.post("/devices", status_code=201)
def api_register_device(body: DeviceRegisterRequest):
    """Register a new device."""
    if not body.id or not body.id.strip():
        raise HTTPException(status_code=400, detail="Device ID must not be empty")
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=400, detail="Device name must not be empty")
    device = services.register_device(body.id.strip(), body.name.strip())
    if device is None:
        raise HTTPException(status_code=409, detail=f"Device '{body.id}' already exists")
    return device


@app.get("/devices")
def api_list_devices():
    """Return all devices with computed status."""
    return services.list_devices()


@app.get("/devices/{device_id}")
def api_get_device(device_id: str):
    """Return a single device by ID."""
    device = services.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return device


@app.post("/devices/{device_id}/heartbeat")
def api_heartbeat(device_id: str, body: HeartbeatRequest | None = None):
    """Record a heartbeat for a device."""
    timestamp = body.timestamp if body else None
    status = body.status if body else None
    device = services.record_heartbeat(device_id, timestamp=timestamp, status=status)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return {"message": "Heartbeat recorded", "device": device}


@app.get("/summary")
def api_summary():
    """Return fleet summary: total, online, offline counts."""
    return services.fleet_summary()


# ── Static files / dashboard ───────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def dashboard():
    """Serve the operator dashboard."""
    return FileResponse("static/index.html")
