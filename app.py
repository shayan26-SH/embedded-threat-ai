"""Local dashboard for the read-only Edge Guard demonstration."""

from __future__ import annotations

from flask import Flask, jsonify, render_template

from edge_guard import EdgeMonitor


def create_app(monitor: EdgeMonitor | None = None, start_monitor: bool = True) -> Flask:
    app = Flask(__name__)
    edge_monitor = monitor or EdgeMonitor()
    app.extensions["edge_monitor"] = edge_monitor

    if start_monitor:
        edge_monitor.start()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        return jsonify(edge_monitor.snapshot())

    @app.post("/api/simulate")
    def simulate():
        try:
            return jsonify(edge_monitor.simulate_anomaly())
        except RuntimeError as error:
            return jsonify({"error": str(error)}), 409

    @app.delete("/api/alerts")
    def clear_alerts():
        edge_monitor.clear_alerts()
        return jsonify({"cleared": True})

    return app


if __name__ == "__main__":
    monitor = EdgeMonitor()
    try:
        create_app(monitor).run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    finally:
        monitor.stop()
