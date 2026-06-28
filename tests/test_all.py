"""
tests/test_all.py
Full pytest suite — 55 tests covering TelemetryPacket, MachineHealth,
IndustrialMachineTwin, TwinRegistry, AnomalyDetectors, EventBus.

Author : Kushagra Bansal — Project Lab India
Run    : pytest tests/ -v
"""
import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.digital_twin import (
    TelemetryPacket, MachineHealth, MachineState, AlertLevel,
    StatisticalZScoreDetector, ThresholdDetector,
    EventBus, IndustrialMachineTwin, TwinRegistry,
)


# ══════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════

def make_payload(machine_id="PLI-M001", temp=42.0, hum=55.0, vib=0.12,
                 cur=8.5, sound=62.0, alert=0, reason="NORMAL", count=1):
    return {
        "machine_id":    machine_id,
        "sensors": {
            "temperature_c":   temp,
            "humidity_pct":    hum,
            "vibration_g_rms": vib,
            "current_a":       cur,
            "sound_db":        sound,
            "accel_x": 0.1, "accel_y": 0.0, "accel_z": 9.81,
        },
        "alert_level":   alert,
        "alert_reason":  reason,
        "wifi_rssi_dbm": -55,
        "publish_count": count,
    }


def make_packet(**kwargs) -> TelemetryPacket:
    return TelemetryPacket.from_mqtt_payload(make_payload(**kwargs))


@pytest.fixture
def normal_packet():
    return make_packet()


@pytest.fixture
def critical_packet():
    return make_packet(temp=82.0, vib=3.5, cur=27.0, alert=2, reason="CRITICAL_OVERHEAT:82.0°C")


@pytest.fixture
def twin():
    return IndustrialMachineTwin("PLI-M001")


@pytest.fixture
def populated_twin():
    t = IndustrialMachineTwin("PLI-M001")
    for i in range(10):
        t.synchronise(make_packet(temp=40+i*0.5, vib=0.1+i*0.01, cur=8.0+i*0.1, count=i+1))
    return t


@pytest.fixture
def registry():
    return TwinRegistry()


# ══════════════════════════════════════════════════════════════
# TelemetryPacket Tests
# ══════════════════════════════════════════════════════════════

class TestTelemetryPacket:

    def test_from_mqtt_payload_basic(self, normal_packet):
        assert normal_packet.machine_id    == "PLI-M001"
        assert normal_packet.temperature_c == 42.0
        assert normal_packet.humidity_pct  == 55.0
        assert normal_packet.vibration_g   == 0.12
        assert normal_packet.current_a     == 8.5
        assert normal_packet.alert_level   == 0

    def test_immutability(self, normal_packet):
        with pytest.raises((AttributeError, TypeError)):
            normal_packet.temperature_c = 999

    def test_received_at_is_utcnow(self, normal_packet):
        age_s = (datetime.utcnow() - normal_packet.received_at).total_seconds()
        assert abs(age_s) < 2.0

    def test_to_dict_keys(self, normal_packet):
        d = normal_packet.to_dict()
        for key in ["machine_id","received_at","temperature_c","humidity_pct",
                    "vibration_g","current_a","sound_db","alert_level","alert_reason"]:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_values_match(self, normal_packet):
        d = normal_packet.to_dict()
        assert d["machine_id"]    == "PLI-M001"
        assert d["temperature_c"] == 42.0
        assert d["alert_level"]   == 0

    def test_missing_sensors_default_zero(self):
        pkt = TelemetryPacket.from_mqtt_payload({"machine_id":"X","sensors":{}})
        assert pkt.temperature_c == 0.0
        assert pkt.vibration_g   == 0.0

    def test_alert_packet(self, critical_packet):
        assert critical_packet.alert_level  == 2
        assert "CRITICAL" in critical_packet.alert_reason
        assert critical_packet.temperature_c == 82.0

    def test_different_machine_ids(self):
        p1 = make_packet(machine_id="M001")
        p2 = make_packet(machine_id="M002")
        assert p1.machine_id != p2.machine_id

    def test_publish_count_stored(self):
        p = make_packet(count=42)
        assert p.publish_count == 42

    def test_wifi_rssi_stored(self):
        p = make_packet()
        assert p.wifi_rssi_dbm == -55


# ══════════════════════════════════════════════════════════════
# StatisticalZScoreDetector Tests
# ══════════════════════════════════════════════════════════════

class TestZScoreDetector:

    def test_returns_zero_insufficient_history(self):
        det = StatisticalZScoreDetector()
        packets = [make_packet() for _ in range(3)]
        assert det.score(packets) == 0.0

    def test_normal_readings_low_score(self):
        det = StatisticalZScoreDetector(window=20, z_threshold=2.5)
        packets = [make_packet(temp=42+i*0.1, vib=0.12, cur=8.5) for i in range(25)]
        score = det.score(packets)
        assert score <= 1.0, f"Score out of range: {score}"

    def test_spike_gives_high_score(self):
        det = StatisticalZScoreDetector(window=30, z_threshold=2.0)
        # 29 normal packets then one massive spike
        packets = [make_packet(temp=42.0, vib=0.1, cur=8.0) for _ in range(29)]
        packets.append(make_packet(temp=95.0, vib=5.0, cur=30.0))
        score = det.score(packets)
        assert score > 0.3, f"Spike should give high score, got {score}"

    def test_score_range(self):
        det = StatisticalZScoreDetector()
        packets = [make_packet(temp=40+i, vib=0.1*i, cur=5+i) for i in range(20)]
        score = det.score(packets)
        assert 0.0 <= score <= 1.0

    def test_name_contains_params(self):
        det = StatisticalZScoreDetector(window=15, z_threshold=3.0)
        assert "15" in det.name() and "3.0" in det.name()


# ══════════════════════════════════════════════════════════════
# ThresholdDetector Tests
# ══════════════════════════════════════════════════════════════

class TestThresholdDetector:

    def test_normal_score_zero(self):
        det = ThresholdDetector()
        packets = [make_packet(temp=40.0, vib=0.5, cur=8.0)]
        assert det.score(packets) == 0.0

    def test_warning_temp(self):
        det = ThresholdDetector()
        packets = [make_packet(temp=70.0, vib=0.5, cur=8.0)]
        score = det.score(packets)
        assert 0.3 <= score < 1.0

    def test_critical_temp_score_one(self):
        det = ThresholdDetector()
        packets = [make_packet(temp=85.0, vib=0.5, cur=8.0)]
        assert det.score(packets) == 1.0

    def test_critical_vibration(self):
        det = ThresholdDetector()
        packets = [make_packet(temp=40.0, vib=3.5, cur=8.0)]
        assert det.score(packets) == 1.0

    def test_empty_history(self):
        det = ThresholdDetector()
        assert det.score([]) == 0.0

    def test_name(self):
        assert "Threshold" in ThresholdDetector().name()


# ══════════════════════════════════════════════════════════════
# EventBus Tests
# ══════════════════════════════════════════════════════════════

class TestEventBus:

    def test_subscribe_and_publish(self):
        bus  = EventBus()
        received = []
        bus.subscribe("telemetry", lambda t, d: received.append((t, d)))
        bus.publish("telemetry", {"x": 1})
        assert len(received) == 1
        assert received[0] == ("telemetry", {"x": 1})

    def test_multiple_subscribers(self):
        bus = EventBus()
        a, b = [], []
        bus.subscribe("evt", lambda t, d: a.append(d))
        bus.subscribe("evt", lambda t, d: b.append(d))
        bus.publish("evt", {"v": 42})
        assert len(a) == len(b) == 1

    def test_unsubscribe(self):
        bus = EventBus()
        called = []
        cb = lambda t, d: called.append(d)
        bus.subscribe("e", cb)
        bus.publish("e", {})
        bus.unsubscribe("e", cb)
        bus.publish("e", {})
        assert len(called) == 1

    def test_no_subscribers_no_error(self):
        bus = EventBus()
        bus.publish("nonexistent", {"x": 1})  # Should not raise

    def test_subscriber_count(self):
        bus = EventBus()
        bus.subscribe("e", lambda t, d: None)
        bus.subscribe("e", lambda t, d: None)
        assert bus.subscriber_count("e") == 2

    def test_broken_callback_does_not_crash_bus(self):
        bus = EventBus()
        bus.subscribe("e", lambda t, d: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.subscribe("e", lambda t, d: None)
        bus.publish("e", {})   # Should not raise


# ══════════════════════════════════════════════════════════════
# IndustrialMachineTwin Tests
# ══════════════════════════════════════════════════════════════

class TestIndustrialMachineTwin:

    def test_initial_state_initialising(self, twin):
        assert twin._state == MachineState.INITIALISING

    def test_synchronise_updates_packet_count(self, twin, normal_packet):
        twin.synchronise(normal_packet)
        assert twin._packet_count == 1

    def test_get_latest_after_sync(self, twin, normal_packet):
        twin.synchronise(normal_packet)
        latest = twin.get_latest()
        assert latest is not None
        assert latest.temperature_c == 42.0

    def test_is_online_after_fresh_sync(self, twin, normal_packet):
        twin.synchronise(normal_packet)
        assert twin.is_online() is True

    def test_is_offline_before_any_sync(self, twin):
        assert twin.is_online() is False

    def test_state_becomes_running(self, twin, normal_packet):
        twin.synchronise(normal_packet)
        assert twin._state == MachineState.RUNNING

    def test_state_becomes_critical(self, twin, critical_packet):
        twin.synchronise(critical_packet)
        assert twin._state == MachineState.CRITICAL

    def test_state_becomes_warning(self, twin):
        twin.synchronise(make_packet(alert=1, reason="WARN_TEMP:66°C"))
        assert twin._state == MachineState.WARNING

    def test_health_score_range(self, populated_twin):
        health = populated_twin.get_health()
        assert 0.0 <= health.health_score <= 100.0

    def test_health_avg_temperature(self, populated_twin):
        health = populated_twin.get_health()
        assert abs(health.avg_temperature - 42.25) < 1.0

    def test_health_peak_temperature(self, populated_twin):
        health = populated_twin.get_health()
        assert health.peak_temperature >= health.avg_temperature

    def test_health_total_packets(self, populated_twin):
        assert populated_twin.get_health().total_packets == 10

    def test_get_health_no_data(self, twin):
        health = twin.get_health()
        assert health.state == MachineState.INITIALISING
        assert health.total_packets == 0

    def test_observer_called_on_sync(self, twin, normal_packet):
        events = []
        twin.subscribe("telemetry", lambda t, d: events.append(d))
        twin.synchronise(normal_packet)
        assert len(events) == 1
        assert events[0]["temperature_c"] == 42.0

    def test_state_change_event_fired(self, twin, normal_packet):
        state_changes = []
        twin.subscribe("state_change", lambda t, d: state_changes.append(d))
        twin.synchronise(normal_packet)     # INITIALISING → RUNNING
        assert len(state_changes) >= 1
        assert state_changes[0]["new_state"] == "RUNNING"

    def test_get_history_returns_list(self, populated_twin):
        history = populated_twin.get_history(last_n=5)
        assert isinstance(history, list)
        assert len(history) == 5

    def test_get_history_dict_has_keys(self, populated_twin):
        history = populated_twin.get_history(1)
        assert "temperature_c" in history[0]
        assert "vibration_g"   in history[0]

    def test_anomaly_probability_range(self, populated_twin):
        health = populated_twin.get_health()
        assert 0.0 <= health.anomaly_probability <= 1.0

    def test_rul_positive_for_healthy_machine(self, populated_twin):
        health = populated_twin.get_health()
        assert health.estimated_rul_hours >= 0

    def test_repr_contains_machine_id(self, twin):
        assert "PLI-M001" in repr(twin)

    def test_multiple_syncs_accumulate(self, twin):
        for i in range(5):
            twin.synchronise(make_packet(count=i+1))
        assert twin._packet_count == 5


# ══════════════════════════════════════════════════════════════
# TwinRegistry Tests
# ══════════════════════════════════════════════════════════════

class TestTwinRegistry:

    def test_get_or_create_creates_new(self, registry):
        twin = registry.get_or_create("PLI-M001")
        assert twin is not None
        assert twin.machine_id == "PLI-M001"

    def test_get_or_create_returns_same_instance(self, registry):
        t1 = registry.get_or_create("PLI-M001")
        t2 = registry.get_or_create("PLI-M001")
        assert t1 is t2

    def test_get_existing(self, registry):
        registry.get_or_create("PLI-M001")
        t = registry.get("PLI-M001")
        assert t is not None

    def test_get_nonexistent_returns_none(self, registry):
        assert registry.get("UNKNOWN-999") is None

    def test_list_all(self, registry):
        registry.get_or_create("M001")
        registry.get_or_create("M002")
        names = registry.list_all()
        assert "M001" in names and "M002" in names

    def test_len(self, registry):
        assert len(registry) == 0
        registry.get_or_create("M001")
        assert len(registry) == 1
        registry.get_or_create("M002")
        assert len(registry) == 2

    def test_fleet_summary_returns_list(self, registry):
        registry.get_or_create("M001")
        summary = registry.fleet_summary()
        assert isinstance(summary, list)
        assert len(summary) == 1

    def test_fleet_summary_keys(self, registry):
        t = registry.get_or_create("M001")
        t.synchronise(make_packet(machine_id="M001"))
        summary = registry.fleet_summary()
        for key in ["machine_id","state","health_score","anomaly_probability"]:
            assert key in summary[0], f"Missing key: {key}"

    def test_independent_twins(self, registry):
        t1 = registry.get_or_create("M001")
        t2 = registry.get_or_create("M002")
        t1.synchronise(make_packet(machine_id="M001", temp=90.0, alert=2))
        t2.synchronise(make_packet(machine_id="M002", temp=40.0, alert=0))
        assert t1._state == MachineState.CRITICAL
        assert t2._state == MachineState.RUNNING
