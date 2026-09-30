"""Configuration constants for the fleet monitor."""

# Heartbeat timeout in seconds. A device is ONLINE if its last heartbeat
# was received within this window; otherwise it is OFFLINE.
HEARTBEAT_TIMEOUT_SECONDS = 30

# Database file path (relative to working directory)
DATABASE_PATH = "fleet_monitor.db"

# Default sample devices created on first run
DEFAULT_DEVICES = [
    {"id": "device-001", "name": "Device 001"},
    {"id": "device-002", "name": "Device 002"},
    {"id": "device-003", "name": "Device 003"},
    {"id": "device-004", "name": "Device 004"},
    {"id": "device-005", "name": "Device 005"},
]

# Simulator settings
SIMULATOR_HEARTBEAT_INTERVAL = 5  # seconds between heartbeats
SIMULATOR_OFFLINE_DEVICE_ID = "device-003"  # this device will stop sending heartbeats
SIMULATOR_OFFLINE_AFTER_SECONDS = 30  # stop heartbeats after this many seconds
