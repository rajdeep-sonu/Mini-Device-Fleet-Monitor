# Mini Device Fleet Monitor

A lightweight web application for monitoring a fleet of simulated devices. Devices send periodic heartbeats, and their status (**ONLINE** / **OFFLINE**) is calculated dynamically using a **30-second timeout rule**.

Includes a FastAPI backend, operator dashboard, standalone multi-device simulator, and automated test suite.

---

## Features

* **Dynamic Status Evaluation**: A device is `ONLINE` if its latest heartbeat was received within 30 seconds; otherwise it is `OFFLINE`. Status is calculated dynamically rather than stored as potentially stale state.
* **Server Reception Authority**: The server's heartbeat reception time is authoritative for liveness, avoiding client clock skew or historical timestamps affecting the 30-second timeout. Client timestamps are retained for diagnostics.
* **Clean Fleet Initialization**: The database starts empty; devices register dynamically through `POST /devices`.
* **Concurrency & Race Safety**: SQLite uses WAL mode and connection management, while database constraints prevent duplicate device registrations during concurrent requests.
* **Operator Dashboard**: Browser UI at `/` provides automatically refreshed fleet status, summary metrics, device information, and status filtering.
* **Interactive API Documentation**: FastAPI provides OpenAPI/Swagger documentation at `/docs`.

---

## Architecture & Project Structure

```text
mini-device-fleet-monitor/
├── app/
│   ├── config.py         # Configuration constants & environment overrides
│   ├── database.py       # SQLite connection manager & WAL configuration
│   ├── main.py           # FastAPI routes, validation, static dashboard
│   └── services.py       # Fleet business logic & dynamic status calculation
├── static/               # Operator dashboard (HTML, CSS, JS)
├── tests/
│   └── test_api.py       # 21 automated API, concurrency, and lifecycle tests
├── simulator.py          # Standalone multi-device simulator
├── run.py                # Uvicorn server entry point
└── requirements.txt      # Python dependencies
```

---

## Server

When running locally, the application is available at:

* **Operator Dashboard:** http://127.0.0.1:8000/
* **API Documentation:** http://127.0.0.1:8000/docs

> `127.0.0.1:8000` is a local development server address. It is accessible only from the machine running the application.

---

## Quickstart

### 1. Setup

```bash
# Create a virtual environment
python -m venv .venv

# Windows (PowerShell / cmd)
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python run.py
```

The server will start on:

```text
http://127.0.0.1:8000
```

Open the following in a browser:

```text
http://127.0.0.1:8000/
```

Swagger API documentation:

```text
http://127.0.0.1:8000/docs
```

### 3. Run the Device Simulator

Open a second terminal with the virtual environment activated:

```bash
python simulator.py
```

The simulator registers five devices and sends heartbeats every 5 seconds.

### Demonstration Timeline

The default simulator demonstrates the timeout behavior automatically:

1. Five devices (`device-01` to `device-05`) register and begin sending heartbeats.
2. All five devices initially appear as **ONLINE**.
3. After 15 seconds, `device-03` stops sending heartbeats.
4. The other four devices continue sending heartbeats.
5. After more than 30 seconds without a heartbeat from `device-03`, it becomes **OFFLINE**.
6. The dashboard and `/summary` endpoint reflect the updated fleet state.

### Simulator Options

```bash
python simulator.py --interval 5
python simulator.py --stop device-03
python simulator.py --stop-after 15
python simulator.py --device device-01
```

* `--interval <sec>`: Heartbeat frequency. Default: `5.0`
* `--stop <device_id>`: Device to stop. Default: `device-03`
* `--stop-after <sec>`: Time before stopping the target device. Default: `15.0`
* `--device <device_id>`: Run a single simulated device for manual testing.

---

## API Summary

| Method | Endpoint                  | Description                         |
| ------ | ------------------------- | ----------------------------------- |
| `POST` | `/devices`                | Register a new device               |
| `GET`  | `/devices`                | List all devices and current status |
| `GET`  | `/devices/{id}`           | Retrieve a single device            |
| `POST` | `/devices/{id}/heartbeat` | Receive a device heartbeat          |
| `GET`  | `/summary`                | Return fleet status counts          |
| `GET`  | `/`                       | Serve the operator dashboard        |

### Register a Device

```bash
curl -X POST http://127.0.0.1:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"id": "device-01", "name": "Lab Device 01"}'
```

### Send a Heartbeat

```bash
curl -X POST http://127.0.0.1:8000/devices/device-01/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"timestamp": "2026-09-21T10:30:00Z", "status": "OK", "cpu_usage": 35.2, "signal_strength": -68.0}'
```

The device-provided timestamp is retained for diagnostic purposes, but the **server reception time** is used for the 30-second liveness calculation.

### List Devices

```bash
curl http://127.0.0.1:8000/devices
```

### Get Device Details

```bash
curl http://127.0.0.1:8000/devices/device-01
```

### Fleet Summary

```bash
curl http://127.0.0.1:8000/summary
```

Example:

```json
{
  "total": 5,
  "online": 4,
  "offline": 1
}
```

---

## Heartbeat & Timeout Model

The application stores the latest server-side heartbeat reception time for each device.

```text
current_time - last_heartbeat <= 30 seconds
                ↓
             ONLINE

current_time - last_heartbeat > 30 seconds
                ↓
             OFFLINE
```

The boundary is therefore:

```text
29.0 seconds → ONLINE
30.0 seconds → ONLINE
30.1 seconds → OFFLINE
```

No background timeout worker is required. Status is calculated when the API or dashboard requests device information.

---

## Assumptions

* A device must be registered before it can send a heartbeat.
* Unknown devices sending heartbeats are rejected.
* The server's heartbeat reception time is authoritative for device liveness.
* The device-provided timestamp is informational and retained for diagnostics.
* A registered device that has never sent a heartbeat is considered `OFFLINE`.
* Only the latest heartbeat is required by the assignment; heartbeat history is not stored.
* SQLite is sufficient for the scale and scope of this engineering exercise.
* Authentication and authorization are outside the scope of the assignment.

---

## Running Tests

Run the automated test suite with:

```bash
pytest -v
```

The suite contains **21 automated tests** covering:

* Clean database start and device registration
* Required-field validation
* Duplicate device registration
* Unknown-device heartbeat rejection
* Heartbeat ingestion
* Optional heartbeat metrics
* ISO-8601 timestamp handling
* 30-second timeout boundary behavior
* Offline → ONLINE recovery
* Dynamic fleet summary calculation
* Concurrent heartbeat handling
* Concurrent duplicate registration handling

The timeout tests are deterministic and do not use artificial 30-second `sleep()` delays.

---

## Configuration

The following environment variables can be used to customize the application:

| Variable                    | Default            | Description                         |
| --------------------------- | ------------------ | ----------------------------------- |
| `HEARTBEAT_TIMEOUT_SECONDS` | `30`               | Timeout threshold for ONLINE status |
| `DATABASE_PATH`             | `fleet_monitor.db` | SQLite database path                |
| `HOST`                      | `127.0.0.1`        | Server network interface            |
| `PORT`                      | `8000`             | Server port                         |

Example:

```bash
HEARTBEAT_TIMEOUT_SECONDS=30
PORT=8000
```

---

## Known Limitations

* SQLite is intended for the small scale of this exercise rather than a distributed production deployment.
* Only the latest heartbeat is retained; historical heartbeat data is not stored.
* Authentication and authorization are not implemented because they are outside the task requirements.
* The simulator is intended for functional demonstration and testing rather than high-volume load testing.
* The application is designed as a single FastAPI service and does not use distributed infrastructure.

---

## What I Would Improve With One Additional Day

With additional development time, I would consider:

* Persistent heartbeat history and historical device metrics
* More structured application logging and observability
* CI-based automated testing
* Containerized deployment
* More extensive concurrency and load testing
* Authentication and authorization if the application were exposed beyond a trusted environment

These improvements were intentionally kept outside the core implementation because correctness and clarity are more important for the scope of this exercise.

---

## AI Usage

* **Tools Used:** Google Gemini and Claude.
* **Purpose:** Used for initial scaffolding, implementation assistance, test design, specification alignment, and code review.
* **Key Improvement:** AI-assisted review identified the importance of using the server heartbeat reception time rather than trusting device timestamps for the 30-second liveness calculation. The implementation was adjusted accordingly.
* **Verification:** Personally verified the API lifecycle, registration and heartbeat behavior, 30-second boundary conditions, concurrent requests, automated test suite, and end-to-end simulator behavior against the assignment requirements.

AI-generated suggestions were reviewed and modified where necessary rather than being accepted without validation.

---

## Submission

The project is intended to be submitted as a Git repository.

Before submission, verify:

```bash
pytest -v
git status
git log --oneline
```

The final repository should contain the complete source code, tests, simulator, and README, and should be reproducible from a clean checkout using the instructions above.
