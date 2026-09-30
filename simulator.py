"""Device Fleet Simulator.

Simulates IoT devices sending periodic heartbeats with diagnostic metrics
to the Mini Device Fleet Monitor application.

Features:
- Automatically registers devices with POST /devices on start
- Automatically re-registers devices if a heartbeat returns 404 (e.g. after server restart or DB wipe)
- Supports single-device mode (--device <id>) to run one process per device and Ctrl+C individually
- Simulates offline failure by stopping one device after a configurable duration (--stop <id> --stop-after <sec>)
- Responsive shutdown: breaks immediately on Ctrl+C without waiting out the sleep interval

Usage examples:
    python simulator.py                                     # 5 devices, device-03 stops after 15s
    python simulator.py --stop-after 15                     # explicit 15s stop for quick review
    python simulator.py --interval 3                        # 3-second heartbeat interval
    python simulator.py --device device-03                  # run only device-03 in this process
    python simulator.py --stop none                         # keep all devices running indefinitely
    python simulator.py --url http://127.0.0.1:8000         # custom server URL
"""

import argparse
import random
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List

import httpx

ALL_DEVICES = [
    {"id": "device-01", "name": "Lab Device 01"},
    {"id": "device-02", "name": "Lab Device 02"},
    {"id": "device-03", "name": "Lab Device 03"},
    {"id": "device-04", "name": "Lab Device 04"},
    {"id": "device-05", "name": "Lab Device 05"},
]

running = True


def handle_shutdown(sig, frame):
    """Graceful exit on SIGINT or SIGTERM."""
    global running
    print("\nShutting down simulator cleanly...")
    running = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate IoT devices sending periodic heartbeats to Mini Device Fleet Monitor."
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="Base URL of the fleet monitor server (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between heartbeat transmissions (default: 5.0)",
    )
    parser.add_argument(
        "--stop",
        default="device-03",
        help="Device ID that will intentionally stop sending heartbeats (default: device-03, use 'none' to disable)",
    )
    parser.add_argument(
        "--stop-after",
        type=float,
        default=15.0,
        help="Seconds elapsed before the stopped device ceases transmission (default: 15.0)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Simulate only this specific device ID (enables one process per device testing)",
    )
    return parser.parse_args()


def register_single_device(client: httpx.Client, base_url: str, dev: Dict[str, str]) -> bool:
    """Register a device via POST /devices. Returns True if registered or already exists."""
    try:
        resp = client.post(f"{base_url}/devices", json=dev, timeout=5.0)
        if resp.status_code == 201:
            print(f"  [+] Registered {dev['id']} ({dev['name']})")
            return True
        elif resp.status_code == 409:
            # Device already registered
            return True
        else:
            print(f"  [!] Failed to register {dev['id']}: HTTP {resp.status_code} {resp.text}")
            return False
    except httpx.RequestError as exc:
        print(f"  [!] Registration error for {dev['id']}: {exc}")
        return False


def send_heartbeat(
    client: httpx.Client,
    base_url: str,
    dev: Dict[str, str],
) -> None:
    """Send a heartbeat for a device. If 404 is encountered (e.g. wiped DB), re-registers and retries."""
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "timestamp": now_iso,
        "status": "OK",
        "cpu_usage": round(random.uniform(15.0, 65.0), 1),
        "signal_strength": round(random.uniform(-85.0, -50.0), 1),
    }

    try:
        resp = client.post(
            f"{base_url}/devices/{dev['id']}/heartbeat",
            json=payload,
            timeout=5.0,
        )

        if resp.status_code == 200:
            print(
                f"  [{dev['id']}] Heartbeat OK | CPU: {payload['cpu_usage']}% | "
                f"Signal: {payload['signal_strength']} dBm"
            )
        elif resp.status_code == 404:
            # Server restarted or database wiped – automatically re-register and retry
            print(f"  [{dev['id']}] Device not found (404). Re-registering...")
            if register_single_device(client, base_url, dev):
                retry_resp = client.post(
                    f"{base_url}/devices/{dev['id']}/heartbeat",
                    json=payload,
                    timeout=5.0,
                )
                if retry_resp.status_code == 200:
                    print(f"  [{dev['id']}] Re-registered and heartbeat OK")
                else:
                    print(f"  [{dev['id']}] Retry failed: HTTP {retry_resp.status_code}")
        else:
            print(f"  [{dev['id']}] Heartbeat rejected: HTTP {resp.status_code} {resp.text}")

    except httpx.RequestError as exc:
        print(f"  [{dev['id']}] Connection error: {exc}")


def interruptible_sleep(seconds: float) -> None:
    """Sleep in short 0.1-second slices so Ctrl+C is handled immediately."""
    end = time.monotonic() + seconds
    while running and time.monotonic() < end:
        time.sleep(min(0.1, max(0.0, end - time.monotonic())))


def main() -> None:
    args = parse_args()

    # Determine device list to simulate
    if args.device:
        target_devs = [d for d in ALL_DEVICES if d["id"] == args.device]
        if not target_devs:
            # Custom device ID
            target_devs = [{"id": args.device, "name": f"Custom Device {args.device}"}]
    else:
        target_devs = ALL_DEVICES

    stop_target = None if (args.stop and args.stop.lower() == "none") else args.stop

    print("=" * 60)
    print("MINI DEVICE FLEET SIMULATOR")
    print("=" * 60)
    print(f"Target Server   : {args.url}")
    print(f"Active Devices  : {[d['id'] for d in target_devs]}")
    print(f"Interval        : {args.interval}s")
    if stop_target:
        print(f"Stop Simulation : '{stop_target}' stops after {args.stop_after}s (goes OFFLINE at ~{args.stop_after + 30}s)")
    else:
        print("Stop Simulation : None (all devices send continuously)")
    print("=" * 60)
    print("\nInitialising device registration...")

    with httpx.Client() as client:
        for dev in target_devs:
            register_single_device(client, args.url, dev)

        print("\nStarting periodic heartbeats (Press Ctrl+C to terminate)...\n")
        start_time = time.monotonic()

        while running:
            elapsed = time.monotonic() - start_time
            print(f"--- [Elapsed: {elapsed:5.1f}s] ---")

            for dev in target_devs:
                if not running:
                    break

                # Check if this device should intentionally stop transmitting
                if stop_target and dev["id"] == stop_target and elapsed >= args.stop_after:
                    print(
                        f"  [{dev['id']}] STOPPED sending heartbeats (simulating failure: "
                        f"will timeout to OFFLINE at ~{args.stop_after + 30:.0f}s)"
                    )
                    continue

                send_heartbeat(client, args.url, dev)

            interruptible_sleep(args.interval)

    print("\nSimulator terminated cleanly.")


if __name__ == "__main__":
    main()
