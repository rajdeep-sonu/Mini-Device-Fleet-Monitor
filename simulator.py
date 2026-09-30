"""Standalone device simulator.

Run this script separately from the server to register devices and send
periodic heartbeats.  One device intentionally stops sending heartbeats
so you can observe the ONLINE → OFFLINE transition.

Usage:
    python simulator.py                  # defaults to http://127.0.0.1:8000
    python simulator.py http://host:port # custom server URL
"""

import sys
import time
import signal
import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

DEVICES = [
    {"id": "device-01", "name": "Lab Device 01"},
    {"id": "device-02", "name": "Lab Device 02"},
    {"id": "device-03", "name": "Lab Device 03"},
    {"id": "device-04", "name": "Lab Device 04"},
    {"id": "device-05", "name": "Lab Device 05"},
]

HEARTBEAT_INTERVAL = 5   # seconds
STOP_DEVICE_ID = "device-03"
STOP_AFTER_SECONDS = 30  # device-03 stops heartbeating after this

running = True


def handle_signal(sig, frame):
    global running
    print("\nShutting down simulator...")
    running = False


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def register_devices(client: httpx.Client) -> None:
    """Register all devices with the server."""
    for dev in DEVICES:
        resp = client.post(f"{BASE_URL}/devices", json=dev)
        if resp.status_code == 201:
            print(f"  Registered {dev['id']}")
        elif resp.status_code == 409:
            print(f"  {dev['id']} already registered")
        else:
            print(f"  Failed to register {dev['id']}: {resp.status_code} {resp.text}")


def send_heartbeat(client: httpx.Client, device_id: str) -> None:
    """Send a heartbeat for one device."""
    try:
        resp = client.post(
            f"{BASE_URL}/devices/{device_id}/heartbeat",
            json={"status": "OK"},
        )
        if resp.status_code == 200:
            print(f"  {device_id} -> heartbeat OK")
        else:
            print(f"  {device_id} -> heartbeat FAILED ({resp.status_code})")
    except httpx.RequestError as exc:
        print(f"  {device_id} -> ERROR: {exc}")


def main() -> None:
    print(f"Simulator targeting: {BASE_URL}")
    print(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
    print(f"Device {STOP_DEVICE_ID} will stop after {STOP_AFTER_SECONDS}s\n")

    with httpx.Client() as client:
        print("Registering devices...")
        register_devices(client)

        start = time.monotonic()
        print(f"\nSending heartbeats (Ctrl+C to stop)...")

        while running:
            elapsed = time.monotonic() - start
            print(f"\n[{elapsed:.0f}s elapsed]")
            for dev in DEVICES:
                if dev["id"] == STOP_DEVICE_ID and elapsed > STOP_AFTER_SECONDS:
                    print(f"  {dev['id']} -> STOPPED (simulating offline)")
                    continue
                send_heartbeat(client, dev["id"])
            time.sleep(HEARTBEAT_INTERVAL)

    print("Simulator stopped.")


if __name__ == "__main__":
    main()
