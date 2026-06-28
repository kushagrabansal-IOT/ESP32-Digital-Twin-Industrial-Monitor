"""
main.py
Application entry point — wires MQTT Bridge, Twin Registry, and FastAPI
together and starts the server.

Author: Kushagra Bansal — Project Lab India

Commands:
    pip install -r requirements.txt
    # Start Mosquitto: docker run -d -p 1883:1883 eclipse-mosquitto
    python main.py
    # API docs: http://localhost:8000/docs
    # Dashboard: http://localhost:8000/dashboard
    # WebSocket: ws://localhost:8000/ws/PLI-M001
"""
import logging
import os
import sys
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))

from backend.digital_twin import TwinRegistry, StatisticalZScoreDetector
from backend.mqtt_bridge   import MQTTBridge
from backend.api           import create_app

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── CONFIGURATION (override with environment variables) ──────────────────
MQTT_HOST   = os.getenv("MQTT_HOST",   "localhost")
MQTT_PORT   = int(os.getenv("MQTT_PORT",   "1883"))
MQTT_USER   = os.getenv("MQTT_USER",   "")
MQTT_PASS   = os.getenv("MQTT_PASS",   "")
API_HOST    = os.getenv("API_HOST",    "0.0.0.0")
API_PORT    = int(os.getenv("API_PORT",    "8000"))

if __name__ == "__main__":
    print("═" * 65)
    print("  ESP32 Digital Twin Industrial Monitor")
    print("  Project Lab India | Kushagra Bansal")
    print("═" * 65)
    print(f"  MQTT Broker : {MQTT_HOST}:{MQTT_PORT}")
    print(f"  API Server  : http://{API_HOST}:{API_PORT}")
    print(f"  API Docs    : http://localhost:{API_PORT}/docs")
    print(f"  Dashboard   : http://localhost:{API_PORT}/dashboard")
    print("═" * 65)

    registry = TwinRegistry()
    bridge   = MQTTBridge(
        host      = MQTT_HOST,
        port      = MQTT_PORT,
        registry  = registry,
        username  = MQTT_USER,
        password  = MQTT_PASS,
    )
    bridge.start()

    app = create_app(registry, bridge)

    try:
        uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        bridge.stop()
