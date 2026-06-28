"""
backend/api.py
FastAPI REST + WebSocket API — exposes the Digital Twin Engine to any
HTTP client: the web dashboard, mobile apps, or external SCADA systems.

Endpoints:
  GET  /                            → API info
  GET  /machines                    → List all registered twins
  GET  /machines/{id}/health        → Full health report
  GET  /machines/{id}/latest        → Latest raw telemetry packet
  GET  /machines/{id}/history       → Recent sensor history (last N packets)
  POST /machines/{id}/command       → Send command to physical device
  GET  /fleet/summary               → Aggregated fleet overview
  GET  /bridge/status               → MQTT bridge connection status
  WS   /ws/{machine_id}             → WebSocket: real-time telemetry stream

Author: Kushagra Bansal — Project Lab India
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .digital_twin import TwinRegistry, IndustrialMachineTwin

logger = logging.getLogger(__name__)

# Injected by main.py at startup
_registry : Optional[TwinRegistry] = None
_bridge   : Optional[object]       = None


def create_app(registry: TwinRegistry, bridge) -> FastAPI:
    global _registry, _bridge
    _registry = registry
    _bridge   = bridge

    app = FastAPI(
        title       = "ESP32 Digital Twin Industrial Monitor — API",
        description = (
            "Real-time REST + WebSocket API for the Digital Twin Engine. "
            "Every ESP32 industrial sensor node has a virtual twin here "
            "that mirrors its state, evaluates health, and detects anomalies."
        ),
        version     = "1.0.0",
        contact     = {
            "name":  "Kushagra Bansal — Project Lab India",
            "url":   "https://github.com/kushagrabansal-IOT",
            "email": "kushagrabansal@gmail.com",
        },
        license_info= {"name": "MIT"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins     = ["*"],
        allow_credentials = True,
        allow_methods     = ["*"],
        allow_headers     = ["*"],
    )

    # ── WebSocket connection manager ──────────────────────────────────────
    class ConnectionManager:
        def __init__(self):
            self._connections: dict[str, list[WebSocket]] = {}

        async def connect(self, machine_id: str, ws: WebSocket):
            await ws.accept()
            self._connections.setdefault(machine_id, []).append(ws)
            logger.info("WS connected: machine=%s, total=%d",
                        machine_id, len(self._connections.get(machine_id, [])))

        def disconnect(self, machine_id: str, ws: WebSocket):
            if machine_id in self._connections:
                self._connections[machine_id] = [
                    c for c in self._connections[machine_id] if c != ws
                ]

        async def broadcast(self, machine_id: str, data: dict):
            dead = []
            for ws in self._connections.get(machine_id, []):
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(machine_id, ws)

    manager = ConnectionManager()

    # ── REST ENDPOINTS ────────────────────────────────────────────────────

    @app.get("/", tags=["Info"])
    async def root():
        return {
            "project":     "ESP32 Digital Twin Industrial Monitor",
            "author":      "Kushagra Bansal — Project Lab India",
            "github":      "github.com/kushagrabansal-IOT/ESP32-Digital-Twin-Industrial-Monitor",
            "version":     "1.0.0",
            "machines":    len(_registry),
            "mqtt_status": _bridge.status() if _bridge else "N/A",
        }

    @app.get("/machines", tags=["Machines"])
    async def list_machines():
        """Returns all registered Digital Twin IDs."""
        return {
            "count":    len(_registry),
            "machines": _registry.list_all(),
        }

    @app.get("/machines/{machine_id}/health", tags=["Machines"])
    async def get_health(machine_id: str):
        """Full health report: state, score, anomaly probability, RUL."""
        twin = _require_twin(machine_id)
        return twin.get_health().to_dict()

    @app.get("/machines/{machine_id}/latest", tags=["Machines"])
    async def get_latest(machine_id: str):
        """Most recent raw telemetry packet from the physical device."""
        twin   = _require_twin(machine_id)
        latest = twin.get_latest()
        if latest is None:
            raise HTTPException(status_code=404, detail="No data received yet")
        return latest.to_dict()

    @app.get("/machines/{machine_id}/history", tags=["Machines"])
    async def get_history(machine_id: str,
                          last_n: int = Query(60, ge=1, le=300,
                                              description="Number of packets (max 300)")):
        """Returns the last N telemetry packets for trend charts."""
        twin = _require_twin(machine_id)
        return {
            "machine_id": machine_id,
            "count":      last_n,
            "history":    twin.get_history(last_n),
        }

    @app.post("/machines/{machine_id}/command", tags=["Machines"])
    async def send_command(machine_id: str, body: dict):
        """
        Send a command to the physical ESP32 device.
        Supported commands: reboot, led_test, beep, set_threshold
        Body example: {"cmd": "led_test"}
        """
        if _bridge is None:
            raise HTTPException(status_code=503, detail="MQTT bridge not available")
        ok = _bridge.publish_command(machine_id, body)
        return {"sent": ok, "machine_id": machine_id, "command": body}

    @app.get("/fleet/summary", tags=["Fleet"])
    async def fleet_summary():
        """Aggregated health overview of every registered machine."""
        summaries = _registry.fleet_summary()
        online_count  = sum(1 for s in summaries if s["state"] not in ("OFFLINE", "INITIALISING"))
        critical_count= sum(1 for s in summaries if s["state"] == "CRITICAL")
        avg_health    = (sum(s["health_score"] for s in summaries) / len(summaries)
                         if summaries else 0)
        return {
            "total_machines":   len(summaries),
            "online":           online_count,
            "critical":         critical_count,
            "avg_health_score": round(avg_health, 2),
            "machines":         summaries,
        }

    @app.get("/bridge/status", tags=["Infrastructure"])
    async def bridge_status():
        """MQTT broker connection status and packet statistics."""
        if _bridge is None:
            return {"status": "not_configured"}
        return _bridge.status()

    # ── WEBSOCKET ─────────────────────────────────────────────────────────

    @app.websocket("/ws/{machine_id}")
    async def websocket_endpoint(machine_id: str, ws: WebSocket):
        """
        Real-time WebSocket stream for a specific machine.
        Pushes every telemetry packet within ~50ms of arrival.
        """
        await manager.connect(machine_id, ws)
        twin = _registry.get(machine_id)
        if twin is None:
            await ws.send_json({"error": f"Machine {machine_id} not registered"})
            await ws.close()
            return

        # Register twin event callback → forward to WebSocket
        async def forward(event_type: str, data: dict):
            await manager.broadcast(machine_id, {"type": event_type, "data": data})

        # Wrap async in sync callback for EventBus
        loop = asyncio.get_event_loop()
        def sync_forward(event_type, data):
            asyncio.run_coroutine_threadsafe(forward(event_type, data), loop)

        twin.subscribe("telemetry",    sync_forward)
        twin.subscribe("state_change", sync_forward)

        # Send current state immediately on connect
        await ws.send_json({"type": "connected", "data": twin.get_health().to_dict()})

        try:
            while True:
                await ws.receive_text()   # keep connection alive, ignore pings
        except WebSocketDisconnect:
            manager.disconnect(machine_id, ws)
            logger.info("WS disconnected: machine=%s", machine_id)

    # ── DASHBOARD HTML ────────────────────────────────────────────────────
    @app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
    async def dashboard():
        """Serve the built-in real-time dashboard."""
        try:
            with open("dashboard/index.html", "r") as f:
                return HTMLResponse(f.read())
        except FileNotFoundError:
            return HTMLResponse("<h1>Dashboard not found</h1>"
                                "<p>Run from project root directory.</p>")

    def _require_twin(machine_id: str) -> IndustrialMachineTwin:
        twin = _registry.get(machine_id)
        if twin is None:
            raise HTTPException(
                status_code=404,
                detail=f"Machine '{machine_id}' not registered. "
                       f"Known machines: {_registry.list_all()}"
            )
        return twin

    return app
