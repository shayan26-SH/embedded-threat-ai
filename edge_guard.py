"""Read-only host telemetry collection and local anomaly detection."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import threading
import time
from typing import Any

import psutil
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


FEATURES = (
    "cpu_percent",
    "memory_percent",
    "process_count",
    "network_sent_bytes_per_sec",
    "network_recv_bytes_per_sec",
)
MINIMUM_FEATURE_SCALES = (5.0, 2.0, 10.0, 10_000.0, 10_000.0)


class SystemTelemetryCollector:
    """Collect aggregate system metrics without inspecting process contents."""

    def __init__(self) -> None:
        self._last_network = psutil.net_io_counters()
        self._last_sample_time = time.monotonic()

    def sample(self) -> dict[str, float]:
        now = time.monotonic()
        elapsed = max(now - self._last_sample_time, 0.001)
        network = psutil.net_io_counters()
        sent_rate = max(network.bytes_sent - self._last_network.bytes_sent, 0) / elapsed
        recv_rate = max(network.bytes_recv - self._last_network.bytes_recv, 0) / elapsed
        self._last_network = network
        self._last_sample_time = now

        return {
            "cpu_percent": float(psutil.cpu_percent(interval=None)),
            "memory_percent": float(psutil.virtual_memory().percent),
            "process_count": float(len(psutil.pids())),
            "network_sent_bytes_per_sec": sent_rate,
            "network_recv_bytes_per_sec": recv_rate,
        }


class AnomalyDetector:
    """Fit an Isolation Forest to a short, locally collected healthy baseline."""

    def __init__(self, baseline_size: int = 20) -> None:
        if baseline_size < 5:
            raise ValueError("baseline_size must be at least 5")
        self.baseline_size = baseline_size
        self._baseline: list[list[float]] = []
        self._scaler = StandardScaler()
        self._model = IsolationForest(
            n_estimators=100,
            contamination=0.08,
            random_state=42,
        )
        self._ready = False
        self._baseline_center: list[float] = []
        self._feature_scales: list[float] = []

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def baseline_samples(self) -> int:
        return len(self._baseline)

    def observe(self, metrics: dict[str, float]) -> dict[str, Any] | None:
        values = [float(metrics[name]) for name in FEATURES]
        if not self._ready:
            self._baseline.append(values)
            if len(self._baseline) >= self.baseline_size:
                scaled = self._scaler.fit_transform(self._baseline)
                self._model.fit(scaled)
                self._baseline_center = self._scaler.mean_.tolist()
                self._feature_scales = [
                    max(float(scale), floor)
                    for scale, floor in zip(self._scaler.scale_, MINIMUM_FEATURE_SCALES)
                ]
                self._ready = True
            return None

        scaled = self._scaler.transform([values])
        prediction = int(self._model.predict(scaled)[0])
        score = float(self._model.decision_function(scaled)[0])
        deviation = max(
            abs(value - center) / scale
            for value, center, scale in zip(values, self._baseline_center, self._feature_scales)
        )
        return {
            "is_anomaly": prediction == -1 or deviation > 6.0,
            "score": score,
            "baseline_deviation": deviation,
        }


class EdgeMonitor:
    """Background sampler, detector, and in-memory alert history."""

    def __init__(
        self,
        interval_seconds: float = 1.0,
        baseline_size: int = 20,
        collector: SystemTelemetryCollector | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.interval_seconds = interval_seconds
        self.collector = collector or SystemTelemetryCollector()
        self.detector = AnomalyDetector(baseline_size)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: dict[str, Any] | None = None
        self._alerts: deque[dict[str, Any]] = deque(maxlen=100)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="edge-guard-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(self.interval_seconds * 2, 1.0))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latest = dict(self._latest) if self._latest else None
            alerts = [dict(alert) for alert in reversed(self._alerts)]
        return {
            "state": "monitoring" if self.detector.ready else "calibrating",
            "baseline_samples": self.detector.baseline_samples,
            "baseline_size": self.detector.baseline_size,
            "latest": latest,
            "alerts": alerts,
        }

    def simulate_anomaly(self) -> dict[str, Any]:
        if not self.detector.ready:
            raise RuntimeError("The baseline is still calibrating.")
        with self._lock:
            baseline = dict(self._latest or {})
        metrics = {
            "cpu_percent": 100.0,
            "memory_percent": 99.0,
            "process_count": max(float(baseline.get("process_count", 0)) + 500.0, 500.0),
            "network_sent_bytes_per_sec": 10_000_000.0,
            "network_recv_bytes_per_sec": 10_000_000.0,
        }
        result = self.detector.observe(metrics)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
            "score": result["score"] if result else None,
            "source": "simulated",
            "response": "SIMULATED ONLY: review the device and apply containment manually if needed.",
        }
        with self._lock:
            self._latest = {**metrics, "timestamp": event["timestamp"], "source": "simulated"}
            if result and result["is_anomaly"]:
                self._alerts.appendleft(event)
        return {
            "detected": bool(result and result["is_anomaly"]),
            "event": event,
        }

    def clear_alerts(self) -> None:
        with self._lock:
            self._alerts.clear()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            metrics = self.collector.sample()
            result = self.detector.observe(metrics)
            timestamp = datetime.now(timezone.utc).isoformat()
            latest = {**metrics, "timestamp": timestamp, "source": "live"}
            with self._lock:
                self._latest = latest
                if result and result["is_anomaly"]:
                    self._alerts.appendleft(
                        {
                            "timestamp": timestamp,
                            "metrics": metrics,
                            "score": result["score"],
                            "source": "live",
                            "response": (
                                "SIMULATED ONLY: review the device and apply containment manually if needed."
                            ),
                        }
                    )
            self._stop_event.wait(self.interval_seconds)
