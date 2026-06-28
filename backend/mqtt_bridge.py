"""
backend/mqtt_bridge.py
MQTT Bridge — subscribes to ESP32 telemetry topics and pipes every
incoming packet into the TwinRegistry for synchronisation.

Author: Kushagra Bansal — Project Lab India
"""
import json
import logging
import threading
import time
from datetime import datetime
from typing import Optional

import paho.mqtt.client as mqtt

from .digital_twin import TelemetryPacket, TwinRegistry, StatisticalZScoreDetector

logger = logging.getLogger(__name__)

TOPIC_TELEMETRY  = "dt/machine/+/telemetry"
TOPIC_HEARTBEAT  = "dt/machine/+/heartbeat"
TOPIC_ALERT      = "dt/machine/+/alert"


class MQTTBridge:
    """
    Thin adapter between the Mosquitto MQTT broker and the TwinRegistry.
    Runs the paho-mqtt network loop in a background daemon thread.

    Encapsulation:
      • Connection credentials stored as private attributes
      • Public interface: start(), stop(), publish_command()
    """

    def __init__(self, host: str, port: int, registry: TwinRegistry,
                 username: str = "", password: str = "",
                 client_id: str = "digital-twin-bridge"):
        self._host     = host
        self._port     = port
        self._registry = registry
        self._thread   : Optional[threading.Thread] = None
        self._running  = False

        self._client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if username:
            self._client.username_pw_set(username, password)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

        self.packets_received  = 0
        self.packets_failed    = 0
        self.last_message_at  : Optional[datetime] = None

    # ── Public Interface ──────────────────────────────────────────────────

    def start(self) -> None:
        """Connect to broker and start background network loop."""
        logger.info("MQTT bridge connecting to %s:%d", self._host, self._port)
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._running = True
        self._thread  = threading.Thread(target=self._client.loop_forever,
                                          daemon=True, name="mqtt-bridge")
        self._thread.start()
        logger.info("MQTT bridge started (thread: %s)", self._thread.name)

    def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        self._client.disconnect()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("MQTT bridge stopped")

    def publish_command(self, machine_id: str, cmd: dict) -> bool:
        """Send a command payload to a specific machine."""
        topic = f"dt/machine/{machine_id}/command"
        payload = json.dumps(cmd)
        result = self._client.publish(topic, payload, qos=1)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def is_connected(self) -> bool:
        return self._client.is_connected()

    def status(self) -> dict:
        return {
            "connected":        self.is_connected(),
            "broker":           f"{self._host}:{self._port}",
            "packets_received": self.packets_received,
            "packets_failed":   self.packets_failed,
            "last_message":     self.last_message_at.isoformat() if self.last_message_at else None,
        }

    # ── MQTT Callbacks (private) ──────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("MQTT connected — subscribing to telemetry topics")
            for topic in [TOPIC_TELEMETRY, TOPIC_HEARTBEAT, TOPIC_ALERT]:
                client.subscribe(topic, qos=1)
                logger.debug("Subscribed: %s", topic)
        else:
            logger.error("MQTT connection failed: rc=%d", rc)

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning("MQTT unexpected disconnect (rc=%d) — reconnecting", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("Malformed MQTT payload on %s: %s", msg.topic, exc)
            self.packets_failed += 1
            return

        # Only process full telemetry packets (not heartbeat / alert)
        if "/telemetry" not in msg.topic:
            return

        try:
            packet = TelemetryPacket.from_mqtt_payload(payload)
            twin   = self._registry.get_or_create(
                packet.machine_id,
                detector=StatisticalZScoreDetector(window=30, z_threshold=2.5),
            )
            twin.synchronise(packet)
            self.packets_received += 1
            self.last_message_at  = datetime.utcnow()

            logger.debug("[%s] pkt=%d temp=%.1f vib=%.3f cur=%.1f alert=%d",
                         packet.machine_id, packet.publish_count,
                         packet.temperature_c, packet.vibration_g,
                         packet.current_a, packet.alert_level)
        except Exception as exc:
            logger.error("Twin synchronisation error: %s", exc)
            self.packets_failed += 1
