# Mini Device Fleet Monitor

A lightweight, robust web application that monitors a fleet of IoT devices sending periodic heartbeats. Device status (**ONLINE** / **OFFLINE**) is calculated dynamically using a configurable **30-second timeout rule**. Includes an operator dashboard, a standalone multi-device simulator, and automated test coverage.

---

## 1. What the Project Does

- **Device Registration (`POST /devices`)**: Registers devices with unique IDs, names, and ISO-8601 timestamps. The fleet starts empty—devices register themselves on connection.
- **Heartbeat Ingestion (`POST /devices/{id}/heartbeat`)**: Ingests periodic heartbeats containing device timestamps, status (`OK`), and diagnostic metrics (`cpu_usage`, `signal_strength`).
- **Dynamic Status Evaluation**: A device is **ONLINE** if its last heartbeat was received within **30 seconds**; otherwise, it is **OFFLINE** (including unregistered devices or devices that have never sent a heartbeat).
- **Fleet Inspection (`GET /devices`, `GET /devices/{id}`)**: Returns real-time device health, elapsed time since last heartbeat, and diagnostic metrics. Supports filtering via `?status=ONLINE` or `?status=OFFLINE`.
- **Fleet Summary (`GET /summary`)**: Returns aggregate device counts (`total`, `online`, `offline`).
- **Interactive Operator Dashboard (`/`)**: Web UI polling every 2.5 seconds with live status badges, summary counters, metrics display, and status filters.
- **Interactive API Documentation (`/docs`)**: Interactive OpenAPI/Swagger UI served automatically by FastAPI at `http://127.0.0.1:8000/docs`.

---

## 2. Design & Architecture

```
┌────────────────────────────────────────────────────────┐
│               Standalone Device Simulator              │
│                     (simulator.py)                     │
│  - POST /devices (auto-registration & recovery)        │
│  - POST /devices/{id}/heartbeat (periodic telemetry)   │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTP / JSON
                           ▼
┌────────────────────────────────────────────────────────┐
│                 FastAPI Web Application                │
│                                                        │
│  Routes:                                               │
│    POST /devices                 GET /devices          │
│    POST /devices/{id}/heartbeat  GET /devices/{id}     │
│    GET  /summary                 GET  /                │
│                                                        │
│  Services (Business Logic):                            │
│    - Dynamic status evaluation (≤30s ONLINE, >30s OFFLINE)│
│    - Server-side receive timestamp tracking            │
│    - Client timestamp preserved for diagnostics        │
└────────────┬───────────────────────────────▲───────────┘
             │                               │
             ▼                               │ Polling (2.5s)
┌─────────────────────────┐     ┌────────────┴───────────┐
│     SQLite Database     │     │   Operator Dashboard   │
│   (fleet_monitor.db)    │     │      (static/)         │
│   - WAL journal mode    │     │  - Live summary cards  │
│   - Per-request conn    │     │  - Device telemetry    │
└─────────────────────────┘     │  - Status filtering    │
                                └────────────────────────┘
```

### Key Engineering Decisions

1. **Server-Side Timestamp Authority**: Status evaluation uses the server's reception time (`_utc_now()`). The client's reported timestamp is stored separately in `device_timestamp` for diagnostics. This prevents device clock skew or historical replays (such as the brief's sample `2026-09-21T10:30:00Z`) from incorrectly marking a fresh device as OFFLINE.
2. **Evaluated Status, Never Stored**: The database does not persist static status strings. Status is evaluated dynamically at query time by comparing elapsed seconds against `HEARTBEAT_TIMEOUT_SECONDS` (30s). Status is guaranteed to be accurate even across server restarts or clock progression.
3. **Empty Fleet Initialization**: The database starts completely empty. There are no pre-seeded sample devices; all devices are created via the official registration API (`POST /devices`).
4. **Concurrency Safety with SQLite WAL**: The database uses SQLite in WAL (Write-Ahead Logging) mode (`PRAGMA journal_mode=WAL`). Reads from operator polls do not block heartbeat writes from concurrent devices. Each request context opens and closes its own connection.
5. **Robust ISO-8601 Parsing**: Implements compliant ISO parsing supporting both UTC `'Z'` offsets and `+00:00` across all Python versions (including Python 3.10, 3.11, 3.12, and 3.14).

---

## 3. Prerequisites

- **Python 3.10+** (tested on Python 3.11, 3.12, and 3.14)
- **uv** (recommended) or standard `pip` / `venv`

---

## 4. How to Build & Install

```bash
# Clone the repository
git clone <repo-url>
cd mini-device-fleet-monitor

# Option A: Using uv (fastest)
uv venv .venv
uv pip install -r requirements.txt

# Option B: Using standard python venv
python -m venv .venv

# Activate the virtual environment:
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Windows (cmd):
.venv\Scripts\activate.bat
# On macOS / Linux:
source .venv/bin/activate

# Install dependencies:
pip install -r requirements.txt
```

---

## 5. How to Run the Application

With your virtual environment activated:

```bash
python run.py
```

The server starts at **http://127.0.0.1:8000**.
- **Dashboard**: Open `http://127.0.0.1:8000/` in any browser.
- **Interactive API Docs**: Open `http://127.0.0.1:8000/docs` (Swagger UI) or `http://127.0.0.1:8000/redoc`.

### Environment Variable Configuration

All settings can be overridden via environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `HEARTBEAT_TIMEOUT_SECONDS` | `30` | Heartbeat timeout threshold in seconds |
| `DATABASE_PATH` | `fleet_monitor.db` | Path to SQLite database file |
| `HOST` | `127.0.0.1` | Network interface to bind |
| `PORT` | `8000` | Port to listen on |

Example:
```bash
HEARTBEAT_TIMEOUT_SECONDS=45 PORT=8080 python run.py
```

---

## 6. How to Run the Simulator

In a second terminal (with the server running and virtual environment activated):

```bash
python simulator.py
```

### Demonstration Timeline (Quick 45s Verification)

By default, the simulator runs with `--stop-after 15`:

1. **t = 0s**: The simulator registers 5 devices (`device-01` to `device-05`) via `POST /devices` and begins sending heartbeats every 5 seconds. All 5 devices appear as **ONLINE** on the dashboard.
2. **t = 15s**: `device-03` intentionally stops sending heartbeats. The remaining 4 devices continue sending.
3. **t = 45s**: Exactly 30 seconds have elapsed since `device-03`'s last heartbeat. The server transitions `device-03` to **OFFLINE**. The dashboard updates the badge to red and summary displays:
   - **Total**: 5
   - **Online**: 4
   - **Offline**: 1

Total reviewer wait time is approximately **45 seconds**.

### Simulator Command-Line Options

```bash
python simulator.py --help
```

- `--interval <sec>`: Interval between heartbeats (default: `5.0`).
- `--stop <device_id>`: Device ID that ceases transmission (default: `device-03`, set to `none` to disable).
- `--stop-after <sec>`: Seconds before stopping the selected device (default: `15.0`).
- `--device <device_id>`: Simulate **only one specific device** in this process (enables running multiple processes and testing manual Ctrl+C failures).
- `--url <url>`: Target server URL (default: `http://127.0.0.1:8000`).

#### Single-Device Process Example
You can run devices in separate terminals and stop one by pressing Ctrl+C:
```bash
# Terminal 1:
python simulator.py --device device-01

# Terminal 2:
python simulator.py --device device-02 --interval 3
```

#### Self-Healing on Server Restart
If the server is restarted and the database is wiped while the simulator is running, subsequent heartbeats return `404 Not Found`. The simulator automatically detects the 404, re-registers the device with `POST /devices`, and resumes normal heartbeat transmission.

---

## 7. How to Run the Tests

Execute pytest with your virtual environment activated:

```bash
python -m pytest -q
```

Output:
```text
..................                                                       [100%]
18 passed in 0.94s
```

### Test Coverage Highlights

The test suite in `tests/test_api.py` includes **18 focused tests** verifying:
1. **Clean initial state**: Confirms fleet starts empty with 0 devices.
2. **Device registration**: Valid registration, duplicate ID rejection (HTTP 409), ID pattern validation (HTTP 422), empty name rejection (HTTP 422).
3. **Heartbeat handling**: Unknown device rejection (HTTP 404), server reception timestamp tracking, storage of diagnostic telemetry (`cpu_usage`, `signal_strength`).
4. **Brief's exact example body**: Sends `{"timestamp": "2026-09-21T10:30:00Z", "status": "OK"}` and asserts device shows `ONLINE` immediately.
5. **Input validation**: Malformed timestamps and timezone-less timestamps return HTTP 422 (never 500). Out-of-bounds CPU (`>100%`) and signal strength return HTTP 422.
6. **30-second timeout rule**: Validated without artificial `sleep()` delays using millisecond-precision UTC offsets (tested at 29.5s -> ONLINE, 30.5s -> OFFLINE).
7. **Status transitions & independence**: Devices with no heartbeats are OFFLINE; become ONLINE on first heartbeat; multiple devices maintain status independently.
8. **Fleet summary & filtering**: Verifies aggregate counts, `?status=ONLINE`, `?status=OFFLINE`, and invalid status handling (HTTP 400).
9. **Concurrency safety**: `concurrent.futures.ThreadPoolExecutor` sending 20 simultaneous heartbeats across 5 devices without SQLite lock conflicts.

---

## 8. Example API Requests

### 1. Register a Device
```bash
curl -X POST http://127.0.0.1:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"id": "device-01", "name": "Lab Device 01"}'
```
Response (`201 Created`):
```json
{
  "id": "device-01",
  "name": "Lab Device 01",
  "status": "OFFLINE",
  "last_heartbeat": null,
  "seconds_since_heartbeat": null,
  "device_timestamp": null,
  "device_status": null,
  "cpu_usage": null,
  "signal_strength": null,
  "created_at": "2026-09-30T11:40:00.123456+00:00"
}
```

### 2. Send a Heartbeat (Brief's Exact Example)
```bash
curl -X POST http://127.0.0.1:8000/devices/device-01/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"timestamp": "2026-09-21T10:30:00Z", "status": "OK", "cpu_usage": 42.5, "signal_strength": -71.0}'
```
Response (`200 OK`):
```json
{
  "message": "Heartbeat recorded",
  "device": {
    "id": "device-01",
    "name": "Lab Device 01",
    "status": "ONLINE",
    "last_heartbeat": "2026-09-30T11:40:02.789123+00:00",
    "seconds_since_heartbeat": 0.1,
    "device_timestamp": "2026-09-21T10:30:00Z",
    "device_status": "OK",
    "cpu_usage": 42.5,
    "signal_strength": -71.0,
    "created_at": "2026-09-30T11:40:00.123456+00:00"
  }
}
```

### 3. List All Devices (or Filter by Status)
```bash
# All devices
curl http://127.0.0.1:8000/devices

# Only online devices
curl http://127.0.0.1:8000/devices?status=ONLINE

# Only offline devices
curl http://127.0.0.1:8000/devices?status=OFFLINE
```

### 4. Get Single Device Details
```bash
curl http://127.0.0.1:8000/devices/device-01
```

### 5. Fleet Summary
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

---

## 9. Assumptions Made

1. **Device ID Format**: Device IDs are non-empty strings up to 64 characters composed of alphanumeric characters, hyphens, and underscores (`^[a-zA-Z0-9_\-]+$`).
2. **Server-Side Health Tracking**: Device status is calculated against the time the server receives the heartbeat. The client's reported timestamp is recorded for auditing and latency diagnostics.
3. **Dynamic Status**: Status is never stored statically in the database. Calculating status upon query ensures correctness across server restarts, clock adjustments, and idle intervals.
4. **Target Fleet Scale**: Designed for edge gateways and lab fleets (tens to hundreds of devices). SQLite with WAL mode is used for simple zero-dependency deployment.

---

## 10. Known Limitations

1. **Heartbeat Telemetry History**: The database persists the latest heartbeat and latest diagnostic metrics (`cpu_usage`, `signal_strength`). Historical time-series telemetry points are not archived.
2. **Unpaginated Device Listing**: `GET /devices` returns all devices in a single response. For fleets scaling past several thousand devices, cursor-based pagination would be required.
3. **Local Storage**: Uses a local SQLite database file rather than a distributed database cluster.

---

## 11. What I Would Improve with One Additional Day

1. **Historical Telemetry Table**: Add a timeseries table (`device_telemetry_history`) to store metric samples over time for charting CPU/signal degradation.
2. **Pagination & Search**: Add `limit`, `offset`, and keyword search to `GET /devices`.
3. **Webhook Notifications**: Trigger webhooks or Slack/PagerDuty alerts when a device transitions from ONLINE to OFFLINE.
4. **WebSocket / SSE Stream**: Provide an optional Server-Sent Events (SSE) endpoint for sub-second push updates to the dashboard.
5. **Container Packaging**: Provide a verified multi-stage Dockerfile and `docker-compose.yml`.

---

## 12. Project Structure

```
mini-device-fleet-monitor/
├── app/
│   ├── __init__.py
│   ├── config.py         # Environment variables & constants
│   ├── database.py       # SQLite connection manager, WAL mode, migrations
│   ├── main.py           # FastAPI application, route handlers, validation
│   └── services.py       # Business logic: registration, status & metrics
├── static/
│   ├── index.html        # Operator dashboard HTML template
│   ├── style.css         # Dashboard styles & responsive layout
│   └── app.js            # Dashboard polling (2.5s), metrics & filter UI
├── tests/
│   ├── __init__.py
│   └── test_api.py       # 18 automated tests (isolated DB per test)
├── pytest.ini            # Pytest configuration
├── requirements.txt      # Minimal pinned dependencies
├── run.py                # Application entry point (uvicorn)
├── simulator.py          # Standalone multi-device simulator CLI
├── .gitignore            # Git ignore rules (.venv, *.db, __pycache__)
└── README.md             # Complete documentation
```

---

## 13. AI Usage

### Tools Used
- **Google Gemini** and **Claude** (within the Antigravity engineering environment) were used as pair programming and review assistants.

### How AI Was Used
- **Initial Scaffolding**: Generating initial boilerplate for FastAPI route signatures, SQLite database helpers, and basic HTML/CSS skeleton.
- **Specification Alignment Review**: I reviewed the project against the specification with Claude's help. Through this review, we identified that the initial draft had used a 10s timeout instead of the required 30s, had nested endpoints under `/api/`, had omitted the `POST /devices` registration and `GET /summary` endpoints, and had seeded mock devices rather than starting with an empty fleet. We systematically aligned all of these with the exam brief.
- **Bug Discovery & Rejection**:
  1. *Client Timestamp Bug*: The initial implementation trusted the client's reported timestamp for status calculation. When sending the brief's example (`2026-09-21T10:30:00Z`), the device was immediately treated as stale (OFFLINE). I corrected this design by enforcing server-side reception timestamp authority for status while storing the client timestamp separately in `device_timestamp`.
  2. *Python 3.10 ISO Compatibility*: Identified that `datetime.fromisoformat()` in Python 3.10 does not support trailing `'Z'`. Added `_parse_iso()` normalization so the brief's example works seamlessly across Python 3.10 through 3.14.
  3. *Unresponsive Simulator Sleep*: Rejected blocking `time.sleep(interval)` in `simulator.py` which delayed Ctrl+C handling by up to 5 seconds. Replaced it with an interruptible sleep loop for immediate shutdown.

### Verification Performed Personally
- Personally ran the full test suite (`python -m pytest -q`) and verified that all 18 tests pass in under 1 second.
- Personally tested the server and simulator end-to-end: verified device registration, confirmed 30s timeout transition on `device-03` after 15s of stopping, verified automatic re-registration on 404, and verified status filtering in both the API and browser UI.
