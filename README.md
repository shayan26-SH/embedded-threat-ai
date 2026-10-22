# Edge Guard

Edge Guard is a small Python demonstration of edge-based anomaly detection for an IoT/embedded security project. It reads aggregate host metrics, learns a local baseline with an Isolation Forest, and shows alerts in a browser dashboard.

## Safety and scope

- Telemetry is local and read-only: CPU use, memory use, process count, and aggregate network byte rates.
- The app does not inspect process arguments or contents, capture packets, or send telemetry to a server.
- No processes are paused or killed. No firewall or network configuration is changed.
- The response shown with an alert is a recommendation only; all containment is simulated.
- The detector is a course/demo prototype, not a production security control.

## Run

Requires Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>. The detector collects 20 one-second samples to learn the current host's baseline before enabling anomaly simulation. Use **Simulate anomaly** to send a synthetic extreme sample through the trained detector. The UI refreshes live metrics and alert history automatically.

To run tests:

```powershell
python -m pytest
```

## Components

- `edge_guard.py`: aggregate telemetry collector, Isolation Forest, and background monitor.
- `app.py`: local Flask dashboard and JSON endpoints.
- `templates/index.html`: responsive dashboard.
- `tests/`: detector and HTTP endpoint checks.
