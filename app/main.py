"""FastAPI application – routes, validation, and lifecycle."""

import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.database import init_db
from app import services

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-12s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("fleet-monitor")


# ── Request validation models ──────────────────────────────────────────


class DeviceRegisterRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=64, description="Unique device identifier")
    name: str = Field(..., min_length=1, max_length=100, description="Device display name")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Device ID must not be empty or whitespace only")
        if not re.match(r"^[a-zA-Z0-9_\-]+$", trimmed):
            raise ValueError("Device ID must only contain letters, digits, underscores, or hyphens")
        return trimmed

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Device name must not be empty or whitespace only")
        return trimmed


class HeartbeatRequest(BaseModel):
    timestamp: Optional[str] = Field(None, description="ISO-8601 device timestamp with timezone")
    status: Optional[str] = Field(None, max_length=32, description="Device operational status (e.g. OK)")
    cpu_usage: Optional[float] = Field(None, ge=0.0, le=100.0, description="CPU utilisation percentage (0-100)")
    signal_strength: Optional[float] = Field(None, ge=-150.0, le=0.0, description="Signal strength in dBm (-150 to 0)")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            # Normalize trailing Z to +00:00 for Python 3.10 compatibility
            norm = trimmed[:-1] + "+00:00" if (trimmed.endswith("Z") or trimmed.endswith("z")) else trimmed
            try:
                dt = datetime.fromisoformat(norm)
            except Exception as e:
                raise ValueError(f"Invalid ISO-8601 timestamp '{v}': {e}")
            if dt.tzinfo is None:
                raise ValueError("Timestamp must be timezone-aware (e.g., end with 'Z' or '+00:00')")
            return trimmed
        return None

    # Allow extra fields (e.g. battery_level, firmware_version) per spec
    model_config = {"extra": "allow"}


# ── Lifecycle ───────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise database schema on startup."""
    init_db()
    logger.info("Database initialised. Fleet starts empty.")
    yield
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="Mini Device Fleet Monitor",
    description="Monitors a fleet of IoT devices via periodic heartbeats. Status (ONLINE / OFFLINE) evaluated dynamically with 30s timeout.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── API routes ──────────────────────────────────────────────────────────


@app.post("/devices", status_code=status.HTTP_201_CREATED)
def api_register_device(body: DeviceRegisterRequest):
    """Register a new device in the fleet."""
    device = services.register_device(body.id, body.name)
    if device is None:
        logger.warning("Registration conflict: device '%s' already exists", body.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device '{body.id}' already exists",
        )
    logger.info("Device registered: %s (%s)", body.id, body.name)
    return device


@app.get("/devices")
def api_list_devices(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter devices by status: ONLINE or OFFLINE",
    )
):
    """List all registered devices and their current status.

    Optionally filter by ?status=ONLINE or ?status=OFFLINE.
    """
    if status_filter is not None:
        norm = status_filter.strip().upper()
        if norm not in ("ONLINE", "OFFLINE"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter '{status_filter}'. Allowed values: ONLINE, OFFLINE",
            )
        return services.list_devices(status_filter=norm)
    return services.list_devices()


@app.get("/devices/{device_id}")
def api_get_device(device_id: str):
    """Retrieve details and current status for a single device."""
    device = services.get_device(device_id)
    if device is None:
        logger.warning("Device not found: %s", device_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found",
        )
    return device


@app.post("/devices/{device_id}/heartbeat")
def api_heartbeat(device_id: str, body: Optional[HeartbeatRequest] = None):
    """Record a heartbeat for a registered device."""
    dev_ts = body.timestamp if body else None
    dev_status = body.status if body else None
    cpu = body.cpu_usage if body else None
    sig = body.signal_strength if body else None

    device = services.record_heartbeat(
        device_id=device_id,
        device_timestamp=dev_ts,
        device_status=dev_status,
        cpu_usage=cpu,
        signal_strength=sig,
    )
    if device is None:
        logger.warning("Heartbeat rejected: device '%s' not registered", device_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found",
        )
    logger.info("Heartbeat recorded for %s (status=%s)", device_id, device["status"])
    return {"message": "Heartbeat recorded", "device": device}


@app.get("/summary")
def api_summary():
    """Return an aggregate fleet summary: total, online, and offline device counts."""
    return services.fleet_summary()


# ── Static dashboard ───────────────────────────────────────────────────

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def dashboard():
    """Serve the operator dashboard."""
    return FileResponse(STATIC_DIR / "index.html")
