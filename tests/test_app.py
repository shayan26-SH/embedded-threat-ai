from app import create_app


class ReadyMonitor:
    def __init__(self):
        self.cleared = False

    def start(self):
        pass

    def stop(self):
        pass

    def snapshot(self):
        return {
            "state": "monitoring",
            "baseline_samples": 20,
            "baseline_size": 20,
            "latest": {"cpu_percent": 5.0},
            "alerts": [],
        }

    def simulate_anomaly(self):
        return {"detected": True, "event": {"source": "simulated"}}

    def clear_alerts(self):
        self.cleared = True


def test_dashboard_status_and_simulated_response():
    app = create_app(ReadyMonitor(), start_monitor=False)
    client = app.test_client()

    assert client.get("/").status_code == 200
    assert client.get("/api/status").json["state"] == "monitoring"
    assert client.post("/api/simulate").json["detected"] is True
    assert client.delete("/api/alerts").json == {"cleared": True}
    assert app.extensions["edge_monitor"].cleared
