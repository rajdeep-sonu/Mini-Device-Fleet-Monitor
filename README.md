# Mini Device Fleet Monitor

A lightweight, robust web application for real-time IoT device fleet monitoring. Devices send periodic heartbeats, and their status (**ONLINE** / **OFFLINE**) is calculated dynamically using a **30-second timeout rule**.

Includes a FastAPI backend, live operator dashboard, standalone multi-device simulator, and comprehensive automated test suite.

---

## Features

- **Dynamic Status Evaluation**: Evaluated in real time: `ONLINE` if the last heartbeat was received within 30s, otherwise `OFFLINE`. Status is computed dynamically on query rather than stored as stale state.
- **Server Reception Authority**: Device status uses the server's reception time, preventing client clock skew or historical replays from causing false offline states. Client timestamps are retained for diagnostics.
- **Clean Fleet Initialization**: The database starts empty; devices register dynamically via `POST /devices`.
- **Concurrency & Race Safety**: SQLite in WAL mode with connection management and primary key integrity handling against simultaneous registration races.
- **Live Operator Dashboard**: Browser UI (`/`) with auto-refreshing telemetry, device status badges, summary metrics, and status filters.
- **Interactive Documentation**: Auto-generated OpenAPI / Swagger UI at `/docs`.

---

## Architecture & Project Structure

```
mini-device-fleet-monitor/
├── app/
│   ├── config.py         # Configuration constants & environment variable overrides
│   ├── database.py       # SQLite connection manager & WAL configuration
│   ├── main.py           # FastAPI routes, Pydantic validation, static dashboard
│   └── services.py       # Fleet business logic, dynamic status calculation
├── static/               # Operator dashboard (HTML, CSS, JS)
├── tests/
│   └── test_api.py       # 21 automated API, concurrency, and lifecycle tests
├── simulator.py          # Standalone multi-device simulator CLI
├── run.py                # Server entry point (Uvicorn)
└── requirements.txt      # Pinned dependencies
```

---

## Quickstart

### 1. Setup

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows (PowerShell / cmd):
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python run.py
```
- **Operator Dashboard**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 3. Run the Device Simulator

In a second terminal with the virtual environment activated:

```bash
python simulator.py
```

**Demonstration timeline (45s total)**:
1. Simulator registers 5 devices (`device-01` to `device-05`) and sends heartbeats every 5 seconds (all **ONLINE**).
2. At $t = 15\text{s}$, `device-03` ceases heartbeats while others continue.
3. At $t = 45\text{s}$ (30s timeout elapsed), `device-03` automatically transitions to **OFFLINE** on the dashboard and summary counters.

*Helpful CLI options:*
- `--interval <sec>`: Heartbeat frequency (default: `5.0`).
- `--stop <device_id>`: Target device to stop (default: `device-03`).
- `--stop-after <sec>`: Time before stopping target device (default: `15.0`).
- `--device <device_id>`: Run only a single device process (useful for manual Ctrl+C testing).

---

## API Summary

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/devices` | Register a new device (`{"id": "dev-01", "name": "Lab Device"}`) |
| `GET` | `/devices` | List all devices (supports optional `?status=ONLINE` or `?status=OFFLINE`) |
| `GET` | `/devices/{id}` | Retrieve details and status for a single device |
| `POST` | `/devices/{id}/heartbeat` | Ingest device heartbeat with status and optional metrics (`cpu_usage`, `signal_strength`) |
| `GET` | `/summary` | Return aggregate counts: `{"total": N, "online": N, "offline": N}` |
| `GET` | `/` | Serve operator dashboard |

### Example Heartbeat Request

```bash
curl -X POST http://127.0.0.1:8000/devices/device-01/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"timestamp": "2026-09-21T10:30:00Z", "status": "OK", "cpu_usage": 35.2, "signal_strength": -68.0}'
```

---

## Running Tests

Run the test suite using pytest:

```bash
pytest -v
```

The test suite in `tests/test_api.py` contains **21 automated tests** covering:
- **Clean start & registration**: Verifies fleet starts empty, validates payload constraints (HTTP 422), and prevents duplicate IDs (HTTP 409).
- **Heartbeat ingestion**: Unknown device rejection (HTTP 404), optional metrics storage (`cpu_usage`, `signal_strength`), and ISO-8601 timezone parsing.
- **30-second timeout precision**: Exact boundary testing ($\le 30.0\text{s}$ ONLINE, $> 30.0\text{s}$ OFFLINE) tested deterministically without artificial `sleep()` delays.
- **Lifecycle transitions & aging**: Offline devices recover to ONLINE on new heartbeat; `/summary` dynamically decrements online counts when heartbeats age past 30s.
- **Concurrency & race safety**: Multi-threaded heartbeat ingestion and concurrent duplicate registrations returning clean 201/409 responses with zero 500 errors.

---

## Configuration

Settings can be customized via environment variables:

| Variable | Default | Description |
|---|---|---|
| `HEARTBEAT_TIMEOUT_SECONDS` | `30` | Timeout threshold in seconds for ONLINE status |
| `DATABASE_PATH` | `fleet_monitor.db` | SQLite database file location |
| `HOST` | `127.0.0.1` | Network interface to bind |
| `PORT` | `8000` | Port to listen on |

---

## AI Usage Disclosure

- **Scaffolding & Review**: Used Google Gemini and Claude within Antigravity for initial boilerplate drafting and specification alignment review.
- **Key Iterations**: Identified and corrected the 30s timeout rule, enforced server reception timestamp authority over client clocks, and normalized Python 3.10 ISO-8601 timestamp handling.
- **Verification**: All implementation logic, concurrency handling, test suite validation (21 tests), and end-to-end server/simulator behavior were directly verified and refined.
