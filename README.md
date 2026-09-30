# Mini Device Fleet Monitor

A lightweight application that monitors a fleet of simulated IoT devices. Devices register themselves, send periodic heartbeats, and the system tracks their status (ONLINE / OFFLINE) based on a configurable timeout. An operator dashboard provides live fleet visibility.

## Design / Architecture

```
┌──────────────────┐       POST /devices/{id}/heartbeat
│  Device Simulator│──────────────────────────────────────┐
│  (standalone      │       POST /devices (register)       │
│   Python script)  │──────────────────────────────────────┤
└──────────────────┘                                      │
                                                          ▼
                                                   ┌────────────┐
                                                   │  FastAPI    │
                                                   │  Backend    │──── SQLite
                                                   └────────────┘     (fleet_monitor.db)
                                                          │
                                                          │ GET /devices
                                                          │ GET /summary
                                                          ▼
                                                   ┌────────────┐
                                                   │  Operator   │
                                                   │  Dashboard  │
                                                   │  (HTML/JS)  │
                                                   └────────────┘
```

**Key design decisions:**

- **Status computed at query time** — no background worker needed. Each API call compares `last_heartbeat` against `now - 30s`.
- **Single timeout constant** — `HEARTBEAT_TIMEOUT_SECONDS = 30` defined once in `app/config.py`.
- **SQLite with WAL mode** — allows concurrent reads from the API while the simulator writes heartbeats.
- **No ORM** — direct `sqlite3` keeps it simple and dependency-free for the database layer.
- **Built-in simulator** — runs as an asyncio background task inside the FastAPI process *and* available as a standalone script.

## Prerequisites

- **Python 3.10+** (tested with Python 3.14)
- **uv** (recommended) or `pip` for package management

## How to Build

```bash
# Clone the repository
git clone <repo-url>
cd mini-device-fleet-monitor

# Create virtual environment and install dependencies
uv venv .venv --python 3.14
uv pip install -r requirements.txt

# Or with pip:
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

## How to Run

```bash
# Start the server (database auto-initialises, built-in simulator starts)
.venv\Scripts\python.exe run.py       # Windows
# .venv/bin/python run.py             # macOS/Linux
```

Open **http://127.0.0.1:8000** to view the operator dashboard.

The application automatically:
1. Creates the SQLite database (`fleet_monitor.db`)
2. Seeds 5 sample devices
3. Starts a background simulator that sends heartbeats every 5 seconds

## How to Run the Simulator

The built-in simulator starts automatically with the server. You can also run the **standalone simulator** in a separate terminal:

```bash
# In a second terminal (server must be running)
.venv\Scripts\python.exe simulator.py
```

The standalone simulator:
- Registers 5 devices via `POST /devices`
- Sends heartbeats every 5 seconds
- Stops heartbeats for `device-03` after 30 seconds (to demonstrate OFFLINE transition)
- Handles Ctrl+C for graceful shutdown

You can also point it at a different server:

```bash
.venv\Scripts\python.exe simulator.py http://192.168.1.50:8000
```

## How to Run the Tests

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

All 18 tests should pass. Each test uses an isolated temporary database.

## Example API Requests

### Register a device

```bash
curl -X POST http://127.0.0.1:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"id": "device-01", "name": "Lab Device 01"}'
```

Response (201):
```json
{
  "id": "device-01",
  "name": "Lab Device 01",
  "status": "OFFLINE",
  "last_heartbeat": null,
  "seconds_since_heartbeat": null,
  "created_at": "2026-09-30 10:45:37"
}
```

### Send a heartbeat

```bash
curl -X POST http://127.0.0.1:8000/devices/device-01/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"timestamp": "2026-09-30T10:30:00Z", "status": "OK"}'
```

### List all devices

```bash
curl http://127.0.0.1:8000/devices
```

Response:
```json
[
  {
    "id": "device-001",
    "name": "Device 001",
    "status": "ONLINE",
    "last_heartbeat": "2026-09-30T10:45:54.702901+00:00",
    "seconds_since_heartbeat": 2.1,
    "created_at": "2026-09-30 10:45:37"
  }
]
```

### Get a single device

```bash
curl http://127.0.0.1:8000/devices/device-001
```

### Fleet summary

```bash
curl http://127.0.0.1:8000/summary
```

Response:
```json
{
  "total": 5,
  "online": 4,
  "offline": 1
}
```

## Assumptions

1. **Device IDs are unique strings** — the system rejects duplicate registration with HTTP 409.
2. **Heartbeat timestamps are optional** — if omitted, the server uses the current UTC time. If provided, the client-supplied timestamp is stored as-is (trusting the client).
3. **Status is computed, not stored** — there is no `status` column in the database. ONLINE/OFFLINE is derived from `last_heartbeat` vs the current time at query time. This means status is always accurate, even after a server restart.
4. **SQLite is sufficient** — the expected fleet size is small (5–50 devices). SQLite with WAL mode handles the concurrent read/write pattern well.
5. **No authentication** — this is a demonstration/assessment application, not production infrastructure.

## Known Limitations

1. **No persistent heartbeat history** — only the latest heartbeat per device is stored. Older heartbeats are overwritten.
2. **No filtering or pagination** — `GET /devices` returns all devices. Fine for small fleets, would need pagination for thousands.
3. **Client-supplied timestamps are trusted** — a misbehaving client could send a future timestamp and appear permanently ONLINE. Production systems would validate or ignore client timestamps.
4. **Single-process** — the built-in simulator runs in the same process as the server. The standalone `simulator.py` script addresses this for more realistic testing.
5. **No graceful handling of very large request bodies** — FastAPI/Pydantic handles basic validation, but there are no explicit size limits on extra heartbeat fields.

## What I Would Improve with One More Day

1. **Heartbeat history table** — store all heartbeats (not just the latest) for trend analysis and debugging.
2. **Filtering** — `GET /devices?status=OFFLINE` to filter the device list by status.
3. **Environment variable configuration** — make `HEARTBEAT_TIMEOUT_SECONDS`, port, and database path configurable via env vars.
4. **Structured logging** — use JSON-formatted log output for easier parsing in production.
5. **Docker support** — a Dockerfile and docker-compose.yml for one-command deployment.
6. **Concurrency tests** — verify correct behavior under parallel heartbeat writes.
7. **API documentation** — add OpenAPI descriptions to each endpoint for auto-generated docs.

## AI Usage

- **Tool used**: Google Gemini (Antigravity / Claude) — used as a pair programming assistant throughout the project.
- **What I used it for**: Initial project scaffolding, writing boilerplate (database init, FastAPI routes, test fixtures), CSS styling, and README structure.
- **Code I changed/rejected**: The AI initially set the heartbeat timeout to 10 seconds and used `/api/devices` route prefixes. I corrected both to match the exam specification (30 seconds, `/devices` routes). The AI also initially omitted the `POST /devices` registration endpoint and the `GET /summary` endpoint — I identified these gaps by comparing against the spec and had them added.
- **What I personally verified**: I ran all 18 tests and confirmed they pass. I started the server, verified the API responses via HTTP requests, and confirmed that Device 003 correctly transitions from ONLINE to OFFLINE after the timeout expires. I also verified the standalone simulator registers devices and sends heartbeats correctly.

## Project Structure

```
mini-device-fleet-monitor/
├── app/
│   ├── __init__.py
│   ├── config.py        # All constants (timeout, devices, simulator settings)
│   ├── database.py      # SQLite init, connection management, seeding
│   ├── main.py          # FastAPI app, routes, Pydantic models, lifecycle
│   ├── services.py      # Business logic (registration, status, heartbeat, summary)
│   └── simulator.py     # Background heartbeat simulator (asyncio task)
├── static/
│   ├── index.html       # Operator dashboard HTML
│   ├── style.css        # Dashboard styles
│   └── app.js           # Dashboard logic (polling, rendering)
├── tests/
│   ├── __init__.py
│   └── test_api.py      # 18 focused API tests
├── simulator.py         # Standalone simulator script
├── requirements.txt     # Python dependencies (5 packages)
├── run.py               # Entry point
└── README.md
```

## Dependencies

| Package | Purpose |
|---------|---------|
| fastapi | Web framework / API |
| uvicorn | ASGI server |
| httpx | HTTP client (simulator + tests) |
| pytest | Test framework |
| pytest-asyncio | Async test support |

SQLite is part of the Python standard library.
