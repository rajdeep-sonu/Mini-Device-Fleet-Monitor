"""Configuration constants for the fleet monitor.

Supports configuration via environment variables with sensible defaults.
"""

import os

# Heartbeat timeout in seconds. A device is ONLINE if its last heartbeat
# was received within this window; otherwise it is OFFLINE.
HEARTBEAT_TIMEOUT_SECONDS = int(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "30"))

# Database file path (relative to working directory or absolute)
DATABASE_PATH = os.getenv("DATABASE_PATH", "fleet_monitor.db")

# Server host and port
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
