"""
backend/digital_twin.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Digital Twin Engine — the Python virtual replica of the physical ESP32
industrial machine.

Every time a real sensor reading arrives via MQTT, the twin updates its
internal state, evaluates health metrics, scores anomaly probability,
and emits structured events. REST API and WebSocket clients query the
twin rather than the physical device — decoupling observation from
hardware availability.

OOP Concepts:
  • Abstract Base Class  : BaseTwin defines the synchronisation contract
  • Encapsulation        : Private sensor buffers, public health API
  • Observer Pattern     : EventBus for real-time dashboard delivery
  • Strategy Pattern     : Pluggable AnomalyDetector implementations
  • Dataclasses          : Immutable TelemetryPacket, MachineHealth
  • Enum                 : MachineState, AlertLevel

Author : Kushagra Bansal — Project Lab India
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from datetime import datetime
from typing import Callable, Optional
import threading
import statistics
import json
import time
import logging

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# DOMAIN ENUMS
# ══════════════════════════════════════════════════════════════════════════

class MachineState(Enum):
    INITIALISING = "INITIALISING"
    RUNNING      = "RUNNING"
    WARNING      = "WARNING"
    CRITICAL     = "CRITICAL"
    OFFLINE      = "OFFLINE"
    MAINTENANCE  = "MAINTENANCE"


class AlertLevel(Enum):
    OK       = 0
    WARNING  = 1
    CRITICAL = 2


# ══════════════════════════════════════════════════════════════════════════
# IMMUTABLE DATA MODELS (Dataclasses)
# ══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TelemetryPacket:
    """Immutable snapshot of one sensor reading from the physical device."""
    machine_id     : str
    received_at    : datetime
    temperature_c  : float
    humidity_pct   : float
    vibration_g    : float
    current_a      : float
    sound_db       : float
    accel_x        : float
    accel_y        : float
    accel_z        : float
    alert_level    : int
    alert_reason   : str
    wifi_rssi_dbm  : int
    publish_count  : int

    @classmethod
    def from_mqtt_payload(cls, payload: dict) -> "TelemetryPacket":
        s = payload.get("sensors", {})
        return cls(
            machine_id    = payload.get("machine_id", "UNKNOWN"),
            received_at   = datetime.utcnow(),
            temperature_c = float(s.get("temperature_c",  0)),
            humidity_pct  = float(s.get("humidity_pct",   0)),
            vibration_g   = float(s.get("vibration_g_rms",0)),
            current_a     = float(s.get("current_a",      0)),
            sound_db      = float(s.get("sound_db",       0)),
            accel_x       = float(s.get("accel_x",        0)),
            accel_y       = float(s.get("accel_y",        0)),
            accel_z       = float(s.get("accel_z",        0)),
            alert_level   = int(payload.get("alert_level",  0)),
            alert_reason  = str(payload.get("alert_reason", "NORMAL")),
            wifi_rssi_dbm = int(payload.get("wifi_rssi_dbm",-99)),
            publish_count = int(payload.get("publish_count",  0)),
        )

    def to_dict(self) -> dict:
        return {
            "machine_id":    self.machine_id,
            "received_at":   self.received_at.isoformat(),
            "temperature_c": self.temperature_c,
            "humidity_pct":  self.humidity_pct,
            "vibration_g":   self.vibration_g,
            "current_a":     self.current_a,
            "sound_db":      self.sound_db,
            "accel_x":       self.accel_x,
            "accel_y":       self.accel_y,
            "accel_z":       self.accel_z,
            "alert_level":   self.alert_level,
            "alert_reason":  self.alert_reason,
            "wifi_rssi_dbm": self.wifi_rssi_dbm,
            "publish_count": self.publish_count,
        }


@dataclass
class MachineHealth:
    """Aggregated health snapshot computed by the twin."""
    machine_id        : str
    state             : MachineState
    health_score      : float          # 0 (dead) → 100 (perfect)
    anomaly_probability: float         # 0.0 → 1.0
    last_seen         : datetime
    uptime_seconds    : float
    total_packets     : int
    alerts_last_hour  : int
    avg_temperature   : float
    avg_vibration     : float
    avg_current       : float
    peak_temperature  : float
    peak_vibration    : float
    peak_current      : float
    estimated_rul_hours: float         # Remaining Useful Life (heuristic)

    def to_dict(self) -> dict:
        return {
            "machine_id":          self.machine_id,
            "state":               self.state.value,
            "health_score":        round(self.health_score, 2),
            "anomaly_probability": round(self.anomaly_probability, 4),
            "last_seen":           self.last_seen.isoformat(),
            "uptime_seconds":      round(self.uptime_seconds, 1),
            "total_packets":       self.total_packets,
            "alerts_last_hour":    self.alerts_last_hour,
            "avg_temperature_c":   round(self.avg_temperature, 2),
            "avg_vibration_g":     round(self.avg_vibration, 4),
            "avg_current_a":       round(self.avg_current, 2),
            "peak_temperature_c":  round(self.peak_temperature, 2),
            "peak_vibration_g":    round(self.peak_vibration, 4),
            "peak_current_a":      round(self.peak_current, 2),
            "estimated_rul_hours": round(self.estimated_rul_hours, 1),
        }


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY PATTERN — Anomaly Detection
# ══════════════════════════════════════════════════════════════════════════

class AnomalyDetector(ABC):
    """Abstract strategy — different detection algorithms are swappable."""

    @abstractmethod
    def score(self, history: list[TelemetryPacket]) -> float:
        """Returns anomaly probability [0.0, 1.0] given recent history."""
        raise NotImplementedError

    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError


class StatisticalZScoreDetector(AnomalyDetector):
    """
    Computes a composite anomaly score from per-feature Z-scores.
    A reading is anomalous if any feature deviates > N standard deviations
    from its rolling window mean.

    Time : O(W) per score call, where W = window length
    Space: O(W)
    """

    def __init__(self, window: int = 30, z_threshold: float = 2.5):
        self.window      = window
        self.z_threshold = z_threshold

    def score(self, history: list[TelemetryPacket]) -> float:
        if len(history) < 5:
            return 0.0

        window = history[-self.window:]
        features = {
            "temperature": [p.temperature_c for p in window],
            "vibration":   [p.vibration_g   for p in window],
            "current":     [p.current_a     for p in window],
            "sound":       [p.sound_db      for p in window],
        }

        max_z = 0.0
        latest = history[-1]
        vals = {
            "temperature": latest.temperature_c,
            "vibration":   latest.vibration_g,
            "current":     latest.current_a,
            "sound":       latest.sound_db,
        }

        for feat, series in features.items():
            if len(series) < 3:
                continue
            mu  = statistics.mean(series)
            sig = statistics.stdev(series)
            if sig < 1e-6:
                continue
            z = abs(vals[feat] - mu) / sig
            max_z = max(max_z, z)

        # Map Z-score to [0, 1] probability using sigmoid-like mapping
        probability = 1.0 - (1.0 / (1.0 + max(0, max_z - self.z_threshold) / 2.0))
        return round(min(1.0, max(0.0, 1.0 - probability if max_z < self.z_threshold else probability)), 4)

    def name(self) -> str:
        return f"ZScore(window={self.window}, z_thresh={self.z_threshold})"


class ThresholdDetector(AnomalyDetector):
    """
    Hard-threshold detector matching the firmware's own logic.
    Used as a baseline to compare against statistical detection.
    """

    THRESHOLDS = {
        "temperature_c": (65.0, 80.0),    # (warn, critical)
        "vibration_g":   (1.8,  3.0),
        "current_a":     (18.0, 25.0),
    }

    def score(self, history: list[TelemetryPacket]) -> float:
        if not history:
            return 0.0
        latest = history[-1]
        readings = {
            "temperature_c": latest.temperature_c,
            "vibration_g":   latest.vibration_g,
            "current_a":     latest.current_a,
        }
        max_score = 0.0
        for feat, (warn, crit) in self.THRESHOLDS.items():
            val = readings[feat]
            if val >= crit:
                max_score = max(max_score, 1.0)
            elif val >= warn:
                ratio = (val - warn) / (crit - warn)
                max_score = max(max_score, 0.3 + 0.6 * ratio)
        return round(max_score, 4)

    def name(self) -> str:
        return "ThresholdDetector"


# ══════════════════════════════════════════════════════════════════════════
# OBSERVER PATTERN — EventBus
# ══════════════════════════════════════════════════════════════════════════

class EventBus:
    """Thread-safe pub/sub hub for real-time WebSocket delivery."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    cb for cb in self._subscribers[event_type] if cb != callback
                ]

    def publish(self, event_type: str, data: dict) -> None:
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))
        for callback in callbacks:
            try:
                callback(event_type, data)
            except Exception as exc:
                logger.error("EventBus callback error: %s", exc)

    def subscriber_count(self, event_type: str) -> int:
        with self._lock:
            return len(self._subscribers.get(event_type, []))


# ══════════════════════════════════════════════════════════════════════════
# ABSTRACT BASE TWIN
# ══════════════════════════════════════════════════════════════════════════

class BaseTwin(ABC):
    """
    Contract every Digital Twin must satisfy.
    Subclasses provide domain-specific synchronisation logic.
    """

    @abstractmethod
    def synchronise(self, packet: TelemetryPacket) -> None:
        """Update twin state from a real-world telemetry packet."""
        raise NotImplementedError

    @abstractmethod
    def get_health(self) -> MachineHealth:
        """Return current health assessment."""
        raise NotImplementedError

    @abstractmethod
    def get_latest(self) -> Optional[TelemetryPacket]:
        """Return the most recent packet received."""
        raise NotImplementedError

    @abstractmethod
    def is_online(self) -> bool:
        """True if a packet was received within the last 10 seconds."""
        raise NotImplementedError


# ══════════════════════════════════════════════════════════════════════════
# CONCRETE DIGITAL TWIN
# ══════════════════════════════════════════════════════════════════════════

class IndustrialMachineTwin(BaseTwin):
    """
    Full Digital Twin for one ESP32-monitored industrial machine.

    Maintains:
      • Rolling 300-packet sensor history (10 min at 2s interval)
      • Per-feature running statistics (mean, peak, stdev)
      • Anomaly score from a pluggable AnomalyDetector strategy
      • Alert event log for dashboard queries
      • Health score (0–100) using a weighted penalty model
      • Estimated Remaining Useful Life (heuristic regression)
    """

    HISTORY_SIZE      = 300     # rolling window: ~10 min at 2s/packet
    OFFLINE_TIMEOUT_S = 10.0    # seconds since last packet → offline
    ALERT_WINDOW_S    = 3600.0  # 1 hour alert counting window

    def __init__(self, machine_id: str,
                 detector: AnomalyDetector | None = None,
                 event_bus: EventBus | None = None):
        self.machine_id  = machine_id
        self._detector   = detector or StatisticalZScoreDetector()
        self._event_bus  = event_bus or EventBus()
        self._lock       = threading.RLock()

        # Internal state
        self._history    : deque[TelemetryPacket] = deque(maxlen=self.HISTORY_SIZE)
        self._alert_log  : list[tuple[datetime, int]] = []
        self._state      = MachineState.INITIALISING
        self._created_at = datetime.utcnow()
        self._packet_count = 0

    # ── PUBLIC API (thread-safe) ─────────────────────────────────────────

    def synchronise(self, packet: TelemetryPacket) -> None:
        """Called by MQTTBridge every time a new payload arrives."""
        with self._lock:
            self._history.append(packet)
            self._packet_count += 1

            if packet.alert_level > 0:
                self._alert_log.append((packet.received_at, packet.alert_level))

            old_state = self._state
            self._state = self._compute_state(packet)

        # Notify WebSocket listeners
        self._event_bus.publish("telemetry", packet.to_dict())

        if self._state != old_state:
            self._event_bus.publish("state_change", {
                "machine_id": self.machine_id,
                "old_state":  old_state.value,
                "new_state":  self._state.value,
                "ts":         datetime.utcnow().isoformat(),
            })
            logger.info("[%s] State: %s → %s", self.machine_id,
                        old_state.value, self._state.value)

    def get_health(self) -> MachineHealth:
        with self._lock:
            history = list(self._history)

        if not history:
            return MachineHealth(
                machine_id=self.machine_id, state=MachineState.INITIALISING,
                health_score=0, anomaly_probability=0,
                last_seen=self._created_at, uptime_seconds=0,
                total_packets=0, alerts_last_hour=0,
                avg_temperature=0, avg_vibration=0, avg_current=0,
                peak_temperature=0, peak_vibration=0, peak_current=0,
                estimated_rul_hours=0,
            )

        latest = history[-1]
        now    = datetime.utcnow()

        # Rolling averages
        avg_temp = statistics.mean(p.temperature_c for p in history)
        avg_vib  = statistics.mean(p.vibration_g   for p in history)
        avg_cur  = statistics.mean(p.current_a     for p in history)

        peak_temp = max(p.temperature_c for p in history)
        peak_vib  = max(p.vibration_g   for p in history)
        peak_cur  = max(p.current_a     for p in history)

        anomaly_prob = self._detector.score(history)

        # Health score: start at 100, penalise based on thresholds
        score = 100.0
        score -= max(0, (avg_temp - 45) * 0.5)      # -0.5/°C over 45°C
        score -= max(0, avg_vib * 15)                # -15/g RMS
        score -= max(0, (avg_cur - 10) * 0.8)        # -0.8/A over 10A
        score -= anomaly_prob * 20                    # -20 at full anomaly
        alerts_h = self._alerts_last_hour(now)
        score -= alerts_h * 3                         # -3 per alert
        score = round(max(0.0, min(100.0, score)), 2)

        # Heuristic RUL: linear degradation model
        rul = max(0.0, score / 100.0 * 8760)         # up to 1 year

        uptime = (latest.received_at - self._created_at).total_seconds()

        return MachineHealth(
            machine_id=self.machine_id,
            state=self._state,
            health_score=score,
            anomaly_probability=anomaly_prob,
            last_seen=latest.received_at,
            uptime_seconds=uptime,
            total_packets=self._packet_count,
            alerts_last_hour=alerts_h,
            avg_temperature=avg_temp,
            avg_vibration=avg_vib,
            avg_current=avg_cur,
            peak_temperature=peak_temp,
            peak_vibration=peak_vib,
            peak_current=peak_cur,
            estimated_rul_hours=rul,
        )

    def get_latest(self) -> Optional[TelemetryPacket]:
        with self._lock:
            return self._history[-1] if self._history else None

    def get_history(self, last_n: int = 60) -> list[dict]:
        with self._lock:
            return [p.to_dict() for p in list(self._history)[-last_n:]]

    def is_online(self) -> bool:
        latest = self.get_latest()
        if latest is None:
            return False
        age = (datetime.utcnow() - latest.received_at).total_seconds()
        return age < self.OFFLINE_TIMEOUT_S

    def subscribe(self, event_type: str, callback: Callable) -> None:
        self._event_bus.subscribe(event_type, callback)

    # ── PRIVATE HELPERS ─────────────────────────────────────────────────

    def _compute_state(self, packet: TelemetryPacket) -> MachineState:
        if not self.is_online():
            return MachineState.OFFLINE
        if packet.alert_level == 2:
            return MachineState.CRITICAL
        if packet.alert_level == 1:
            return MachineState.WARNING
        return MachineState.RUNNING

    def _alerts_last_hour(self, now: datetime) -> int:
        cutoff = now.timestamp() - self.ALERT_WINDOW_S
        self._alert_log = [
            (t, lvl) for t, lvl in self._alert_log
            if t.timestamp() > cutoff
        ]
        return len(self._alert_log)

    def __repr__(self) -> str:
        latest = self.get_latest()
        online = "🟢 ONLINE" if self.is_online() else "🔴 OFFLINE"
        return (f"IndustrialMachineTwin(id={self.machine_id!r}, "
                f"state={self._state.value}, {online}, "
                f"packets={self._packet_count})")


# ══════════════════════════════════════════════════════════════════════════
# TWIN REGISTRY — manages a fleet of twins
# ══════════════════════════════════════════════════════════════════════════

class TwinRegistry:
    """Singleton-like registry holding all active Digital Twin instances."""

    def __init__(self):
        self._twins : dict[str, IndustrialMachineTwin] = {}
        self._lock  = threading.Lock()

    def get_or_create(self, machine_id: str,
                      detector: AnomalyDetector | None = None) -> IndustrialMachineTwin:
        with self._lock:
            if machine_id not in self._twins:
                self._twins[machine_id] = IndustrialMachineTwin(
                    machine_id, detector=detector
                )
                logger.info("Created twin for machine: %s", machine_id)
            return self._twins[machine_id]

    def get(self, machine_id: str) -> Optional[IndustrialMachineTwin]:
        with self._lock:
            return self._twins.get(machine_id)

    def list_all(self) -> list[str]:
        with self._lock:
            return list(self._twins.keys())

    def fleet_summary(self) -> list[dict]:
        with self._lock:
            twins = list(self._twins.values())
        return [t.get_health().to_dict() for t in twins]

    def __len__(self) -> int:
        with self._lock:
            return len(self._twins)
