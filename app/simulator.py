"""Background device simulator that sends periodic heartbeats."""

import asyncio
import logging
import time

import httpx

from app.config import (
    DEFAULT_DEVICES,
    SIMULATOR_HEARTBEAT_INTERVAL,
    SIMULATOR_OFFLINE_AFTER_SECONDS,
    SIMULATOR_OFFLINE_DEVICE_ID,
)

logger = logging.getLogger("simulator")

_task: asyncio.Task | None = None

BASE_URL = "http://127.0.0.1:8000"


async def _send_heartbeat(client: httpx.AsyncClient, device_id: str) -> None:
    """POST a heartbeat for a single device."""
    try:
        resp = await client.post(
            f"{BASE_URL}/devices/{device_id}/heartbeat",
            json={"status": "OK"},
        )
        if resp.status_code == 200:
            logger.debug("Heartbeat OK: %s", device_id)
        else:
            logger.warning("Heartbeat failed for %s: %s", device_id, resp.status_code)
    except httpx.RequestError as exc:
        logger.warning("Heartbeat request error for %s: %s", device_id, exc)


async def _run_simulator() -> None:
    """Main simulator loop.

    All devices send heartbeats periodically.  After
    SIMULATOR_OFFLINE_AFTER_SECONDS, the designated offline device stops
    sending so an operator can observe the ONLINE → OFFLINE transition.
    """
    start = time.monotonic()
    device_ids = [d["id"] for d in DEFAULT_DEVICES]

    # Brief delay to let the server finish starting up
    await asyncio.sleep(2)

    logger.info("Simulator started – sending heartbeats every %ss", SIMULATOR_HEARTBEAT_INTERVAL)
    logger.info(
        "Device %s will stop heartbeats after %ss",
        SIMULATOR_OFFLINE_DEVICE_ID,
        SIMULATOR_OFFLINE_AFTER_SECONDS,
    )

    async with httpx.AsyncClient() as client:
        while True:
            elapsed = time.monotonic() - start
            for device_id in device_ids:
                # After the configured time, stop heartbeats for the offline device
                if device_id == SIMULATOR_OFFLINE_DEVICE_ID and elapsed > SIMULATOR_OFFLINE_AFTER_SECONDS:
                    continue
                await _send_heartbeat(client, device_id)
            await asyncio.sleep(SIMULATOR_HEARTBEAT_INTERVAL)


def start(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Schedule the simulator as a background asyncio task."""
    global _task
    if _task is not None and not _task.done():
        logger.info("Simulator already running")
        return
    _task = asyncio.ensure_future(_run_simulator())
    logger.info("Simulator task scheduled")


def stop() -> None:
    """Cancel the simulator task if running."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        logger.info("Simulator task cancelled")
    _task = None
