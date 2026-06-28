# ESP32-Digital-Twin-Industrial-Monitor 🏭🤖

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![ESP32](https://img.shields.io/badge/Hardware-ESP32-red?style=for-the-badge&logo=espressif&logoColor=white)](https://espressif.com)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![MQTT](https://img.shields.io/badge/Protocol-MQTT-orange?style=for-the-badge&logo=eclipse-mosquitto&logoColor=white)](https://mqtt.org)
[![Tests](https://img.shields.io/badge/Tests-57%20Passed-22c55e?style=for-the-badge&logo=pytest)](tests/)
[![License](https://img.shields.io/badge/License-MIT-f59e0b?style=for-the-badge)](LICENSE)
[![IoT](https://img.shields.io/badge/Domain-Industry_4.0-7c3aed?style=for-the-badge)](#)
[![Stars](https://img.shields.io/github/stars/kushagrabansal-IOT/ESP32-Digital-Twin-Industrial-Monitor?style=for-the-badge&logo=github)](https://github.com/kushagrabansal-IOT/ESP32-Digital-Twin-Industrial-Monitor)

**Real-Time Digital Twin Engine for Industrial IoT Machines**

*Complete Industry 4.0 system: ESP32 multi-sensor node → MQTT telemetry → Python Digital Twin Engine → REST/WebSocket API → Live Dashboard. Every physical machine gets a virtual replica that mirrors its state, evaluates health, detects anomalies, and predicts Remaining Useful Life — in real time.*

**Built by [Kushagra Bansal](https://github.com/kushagrabansal-IOT) | Founder @ [Project Lab India](https://radiomarket.in) | Jaipur, India**

---

[📖 Overview](#-project-overview) • [🏗️ Architecture](#️-system-architecture) • [📐 UML Diagram](#-uml-class-diagram) • [⚡ Quick Start](#-quick-start) • [📡 Hardware](#-hardware-setup) • [🔬 How It Works](#-how-it-works) • [📊 API Reference](#-api-reference) • [🎯 Interview Q&A](#-interview-questions--answers) • [🚀 Future Work](#-future-enhancements)

</div>

---

## 📖 Project Overview

### What is a Digital Twin?

A **Digital Twin** is a virtual replica of a physical object that:
- Mirrors the physical object's state in **real time**
- Enables **simulation** without touching real hardware
- Provides **historical analysis** when the device is offline
- Runs **predictive algorithms** (anomaly detection, RUL estimation) on the digital copy
- Acts as the **single source of truth** for dashboards, alerts, and control systems

> Originally coined by Dr. Michael Grieves (University of Michigan, 2002), Digital Twins are now the cornerstone of Industry 4.0 — the fourth industrial revolution. The global Digital Twin market is projected to reach **$110 billion by 2028** (MarketsandMarkets, 2023).

### Why This Project Matters

Traditional industrial monitoring systems have three fatal flaws:
1. **Tight coupling** — dashboards query physical sensors directly; if a device goes offline, all visibility is lost
2. **No intelligence** — raw sensor values are displayed but not interpreted
3. **No history** — only current state is available; trends are invisible

This project solves all three by inserting a **Digital Twin Engine** between hardware and consumers:

```
Without Digital Twin:    Dashboard → ESP32 (direct, fragile, no intelligence)
With Digital Twin:       ESP32 → Twin Engine → Dashboard (decoupled, intelligent, always-on)
```

### Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Hardware** | ESP32 DevKit V1 | Multi-sensor data acquisition |
| **Sensors** | ADXL345, DHT22, ACS712, MAX4466 | Vibration, Temp, Current, Sound |
| **Firmware** | Arduino C++ | Real-time sensor reading + MQTT publish |
| **Protocol** | MQTT (Mosquitto broker) | Lightweight IoT messaging |
| **Twin Engine** | Python 3.11 | State synchronisation + anomaly detection |
| **API** | FastAPI + WebSocket | REST + real-time streaming |
| **Dashboard** | HTML5 + Chart.js | Live sensor charts |
| **Tests** | pytest (57 tests) | Full unit + integration coverage |

---

## 🏗️ System Architecture

### End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PHYSICAL LAYER                                                                  │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐               │
│  │  ESP32 DevKit V1                                             │               │
│  │                                                              │               │
│  │  ADXL345 ──→ Vibration RMS (g)  ─┐                         │               │
│  │  DHT22   ──→ Temp (°C) + RH (%) ─┤                         │               │
│  │  ACS712  ──→ Current RMS (A)    ─┼──→ JSON Telemetry       │               │
│  │  MAX4466 ──→ Sound Level (dB)   ─┘    every 2 seconds      │               │
│  └──────────────────────┬───────────────────────────────────────┘               │
│                         │ WiFi 802.11n / MQTT QoS=1                             │
└─────────────────────────┼───────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PROTOCOL LAYER                                                                  │
│                                                                                  │
│  Mosquitto MQTT Broker  (topic: dt/machine/{id}/telemetry)                      │
│                                                                                  │
└─────────────────────────┬───────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  DIGITAL TWIN ENGINE (Python)                                                    │
│                                                                                  │
│  MQTTBridge ──→ TelemetryPacket ──→ TwinRegistry ──→ IndustrialMachineTwin     │
│                                                            │                     │
│                                              ┌─────────────┼──────────────┐     │
│                                              ▼             ▼              ▼     │
│                                       StatZScore    ThresholdDet    EventBus    │
│                                       Detector       (baseline)    (Observer)   │
│                                              │             │              │     │
│                                              └─────────────┼──────────────┘     │
│                                                            ▼                     │
│                                                      MachineHealth               │
│                                         (score, anomaly_prob, RUL, state)       │
└─────────────────────────┬───────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  API LAYER (FastAPI)                                                             │
│                                                                                  │
│  REST  GET  /machines/{id}/health    → health report                            │
│        GET  /machines/{id}/history   → sensor history (up to 300 packets)       │
│        GET  /fleet/summary           → all machines overview                     │
│        POST /machines/{id}/command   → send command to ESP32                    │
│  WS    ws://host/ws/{machine_id}     → real-time push (< 50ms latency)          │
└─────────────────────────┬───────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                                              │
│  Live Dashboard (Chart.js) • Mobile App • SCADA System • Third-party APIs       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📐 UML Class Diagram

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  <<dataclass, frozen=True>>                                                    │
│  TelemetryPacket                                                               │
│────────────────────────────────────────────────────────────────────────────────│
│  + machine_id      : str                                                       │
│  + received_at     : datetime                                                  │
│  + temperature_c   : float                                                     │
│  + humidity_pct    : float                                                     │
│  + vibration_g     : float     (RMS, g-units)                                 │
│  + current_a       : float     (RMS, Amperes)                                  │
│  + sound_db        : float     (dB SPL)                                        │
│  + accel_x/y/z     : float                                                     │
│  + alert_level     : int       (0=OK, 1=WARN, 2=CRIT)                         │
│  + alert_reason    : str                                                       │
│────────────────────────────────────────────────────────────────────────────────│
│  + from_mqtt_payload(payload) : TelemetryPacket   <<classmethod>>              │
│  + to_dict() : dict                                                            │
└──────────────────────────────────────────────────┬─────────────────────────────┘
                                                   │ used by
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  <<abstract>>                                                                 │
│  BaseTwin                                                                     │
│──────────────────────────────────────────────────────────────────────────────│
│  + synchronise(packet: TelemetryPacket) : None  {abstract}                   │
│  + get_health() : MachineHealth                 {abstract}                   │
│  + get_latest() : TelemetryPacket | None        {abstract}                   │
│  + is_online() : bool                           {abstract}                   │
└──────────────────────────────────────────────────┬───────────────────────────┘
                                                   │ inherits
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  IndustrialMachineTwin                                                        │
│──────────────────────────────────────────────────────────────────────────────│
│  - machine_id   : str                                                         │
│  - _history     : deque[TelemetryPacket]  (max 300)  [PRIVATE]               │
│  - _alert_log   : list[tuple]                         [PRIVATE]               │
│  - _state       : MachineState                                                │
│  - _detector    : AnomalyDetector          (injected — STRATEGY pattern)      │
│  - _event_bus   : EventBus                 (injected — OBSERVER hub)          │
│  - _lock        : RLock                    (thread-safe state mutations)       │
│──────────────────────────────────────────────────────────────────────────────│
│  + synchronise(packet) : None                                                 │
│  + get_health() : MachineHealth                                               │
│  + get_latest() : TelemetryPacket | None                                      │
│  + get_history(last_n) : list[dict]                                           │
│  + is_online() : bool                                                         │
│  + subscribe(event_type, callback) : None                                     │
│  - _compute_state(packet) : MachineState                                      │
│  - _alerts_last_hour(now) : int                                               │
└──────────────────┬───────────────────────────────────────────────────────────┘
                   │ has-a (composition)
         ┌─────────┴──────────┐
         ▼                    ▼
┌──────────────────┐  ┌──────────────────────────────────────────────┐
│  <<abstract>>    │  │  EventBus                                     │
│  AnomalyDetector │  │  (OBSERVER pattern — thread-safe pub/sub)    │
│──────────────────│  │──────────────────────────────────────────────│
│  + score(history)│  │  - _subscribers : dict[str, list[Callable]]  │
│    : float       │  │  + subscribe(event_type, callback) : None    │
│  + name() : str  │  │  + unsubscribe(event_type, callback) : None  │
└────────┬─────────┘  │  + publish(event_type, data) : None          │
         │ inherits   │  + subscriber_count(event_type) : int        │
    ┌────┴────┐        └──────────────────────────────────────────────┘
    ▼         ▼
┌──────────┐  ┌────────────────┐
│ ZScore   │  │ Threshold      │
│ Detector │  │ Detector       │
│ (default)│  │ (baseline)     │
└──────────┘  └────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│  TwinRegistry                          (manages entire machine fleet)         │
│──────────────────────────────────────────────────────────────────────────────│
│  - _twins : dict[str, IndustrialMachineTwin]                                 │
│  - _lock  : threading.Lock                                                    │
│──────────────────────────────────────────────────────────────────────────────│
│  + get_or_create(machine_id, detector) : IndustrialMachineTwin               │
│  + get(machine_id) : IndustrialMachineTwin | None                             │
│  + list_all() : list[str]                                                     │
│  + fleet_summary() : list[dict]                                               │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│  MQTTBridge                            (MQTT → TwinRegistry adapter)          │
│──────────────────────────────────────────────────────────────────────────────│
│  - _host, _port       : str / int       [PRIVATE]                            │
│  - _registry          : TwinRegistry                                          │
│  - _client            : paho.mqtt.Client                                      │
│  - _thread            : Thread          (daemon background loop)              │
│  + packets_received   : int             [PUBLIC counter]                      │
│──────────────────────────────────────────────────────────────────────────────│
│  + start() : None                                                             │
│  + stop() : None                                                              │
│  + publish_command(machine_id, cmd) : bool                                    │
│  + is_connected() : bool                                                      │
│  + status() : dict                                                            │
│  - _on_connect(...)   : None           [PRIVATE MQTT callback]                │
│  - _on_message(...)   : None           [PRIVATE MQTT callback]                │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧱 OOP Concepts Demonstrated

| Concept | Class / Module | Detail |
|---|---|---|
| **Abstraction** | `BaseTwin`, `AnomalyDetector` | ABCs define contracts; concrete details hidden |
| **Encapsulation** | `IndustrialMachineTwin`, `MQTTBridge` | `_history`, `_port`, `_pin_hash` private; public methods only |
| **Inheritance** | `IndustrialMachineTwin → BaseTwin`, `ThresholdDetector → AnomalyDetector` | Multi-level specialisation |
| **Polymorphism** | `StatisticalZScoreDetector` / `ThresholdDetector` | Same `.score()` call, completely different algorithm |
| **Strategy Pattern** | `AnomalyDetector` | Swap detection algorithm at runtime without changing `IndustrialMachineTwin` |
| **Observer Pattern** | `EventBus` in `IndustrialMachineTwin` | Dashboard WebSocket callbacks subscribe; twin notifies on every packet |
| **Dataclass (Immutable)** | `TelemetryPacket` (`frozen=True`) | Prevents accidental mutation of sensor records |
| **Dataclass (Mutable)** | `MachineHealth`, `RoundLog` | Clean structured return types |
| **Enum** | `MachineState`, `AlertLevel` | Type-safe machine lifecycle states |
| **Composition** | Twin has `EventBus` has subscribers | Flexible, avoids deep inheritance hierarchies |
| **Dependency Injection** | `IndustrialMachineTwin(detector=...)` | Detector and EventBus injected; enables unit testing with mocks |
| **Thread Safety** | `RLock` in twin, `Lock` in registry, `Lock` in EventBus | Concurrent MQTT + API access without race conditions |
| **Context Manager** | N/A — `with self._lock:` pattern throughout | RAII-style lock acquire/release |

---

## ✨ Features

### Hardware (ESP32 Firmware)
- ✅ 4-sensor simultaneous acquisition: vibration (ADXL345), temperature+humidity (DHT22), current (ACS712-30A), sound (MAX4466)
- ✅ Vibration RMS computed on-device over 50 ADXL345 samples at 2kHz
- ✅ Current RMS computed from 500 ADC samples at 10kHz
- ✅ 3-level alert system (OK / WARNING / CRITICAL) computed on-device against configurable thresholds
- ✅ MQTT publish every 2 seconds with full JSON telemetry
- ✅ Heartbeat every 30 seconds with uptime, free heap, WiFi RSSI
- ✅ MQTT command handler: `reboot`, `led_test`, `beep`, `set_threshold`
- ✅ WS2812B RGB LED: Green=OK, Orange=Warning, Red=Critical
- ✅ Active buzzer alarm: 3 beeps on CRITICAL alert
- ✅ Auto-reconnect to WiFi + MQTT on network drop

### Digital Twin Engine (Python Backend)
- ✅ `IndustrialMachineTwin` — virtual replica with 300-packet rolling history (~10 min)
- ✅ Statistical Z-Score anomaly detector (configurable window + threshold)
- ✅ Threshold-based baseline detector (matches firmware logic exactly)
- ✅ Health score (0–100) using weighted multi-metric penalty model
- ✅ Anomaly probability [0.0, 1.0] — composite statistical measure
- ✅ Heuristic Remaining Useful Life (RUL) estimation in hours
- ✅ Alert log with 1-hour rolling window for alert rate tracking
- ✅ Thread-safe state for concurrent MQTT + API access
- ✅ EventBus Observer pattern for real-time WebSocket delivery
- ✅ `TwinRegistry` — manages entire fleet of machines

### API (FastAPI)
- ✅ REST: 7 endpoints covering health, history, commands, fleet summary
- ✅ WebSocket: real-time stream per machine ID (<50ms latency from sensor to browser)
- ✅ CORS enabled for cross-origin dashboard access
- ✅ Auto-generated OpenAPI/Swagger docs at `/docs`
- ✅ Send commands to physical devices via `POST /machines/{id}/command`

### Dashboard
- ✅ Live line charts: Temperature, Vibration, Current (last 60 readings)
- ✅ 6 stat cards with traffic-light colour coding
- ✅ Health score + anomaly probability progress bars
- ✅ Machine state badge with live transition detection
- ✅ Real-time event log with timestamp and severity colour

---

## 📁 Project Structure

```
ESP32-Digital-Twin-Industrial-Monitor/
│
├── firmware/
│   └── main.ino                  ← Complete ESP32 Arduino firmware
│
├── backend/
│   ├── __init__.py               ← Public API surface
│   ├── digital_twin.py           ← Core Twin Engine (600 lines, fully documented)
│   ├── mqtt_bridge.py            ← MQTT → TwinRegistry adapter
│   └── api.py                    ← FastAPI REST + WebSocket server
│
├── dashboard/
│   └── index.html                ← Real-time dashboard (WebSocket + Chart.js)
│
├── tests/
│   └── test_all.py               ← 57 pytest unit + integration tests
│
├── notes/
│   └── digital_twin_theory.md    ← Digital Twin concept deep-dive
│
├── main.py                       ← Application entry point (DI wiring)
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

---

## ⚡ Quick Start

### Step 1 — Backend (Python)

```bash
# Clone
git clone https://github.com/kushagrabansal-IOT/ESP32-Digital-Twin-Industrial-Monitor.git
cd ESP32-Digital-Twin-Industrial-Monitor

# Install dependencies
pip install -r requirements.txt

# Start MQTT broker (Docker)
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto

# Start the Digital Twin Engine + API
python main.py

# API docs: http://localhost:8000/docs
# Dashboard: http://localhost:8000/dashboard
```

### Step 2 — ESP32 Firmware

```bash
# Open firmware/main.ino in Arduino IDE
# Configure:
#define WIFI_SSID    "your_wifi"
#define WIFI_PASSWORD "your_pass"
#define MQTT_SERVER   "192.168.x.x"   # your PC's local IP

# Board: ESP32 Dev Module
# Upload Speed: 921600
# Flash Size: 4MB
# Upload → Serial Monitor @ 115200 baud
```

### Step 3 — Run Tests

```bash
pytest tests/ -v
# 57 passed in 0.39s
```

### Step 4 — Use the API

```bash
# List registered machines
curl http://localhost:8000/machines

# Get machine health report
curl http://localhost:8000/machines/PLI-M001/health

# Get last 30 sensor readings
curl http://localhost:8000/machines/PLI-M001/history?last_n=30

# Send command to physical ESP32
curl -X POST http://localhost:8000/machines/PLI-M001/command \
     -H "Content-Type: application/json" \
     -d '{"cmd":"beep"}'

# Fleet overview
curl http://localhost:8000/fleet/summary

# WebSocket (JavaScript)
const ws = new WebSocket("ws://localhost:8000/ws/PLI-M001");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

---

## 📡 Hardware Setup

### Components Required

| Component | Qty | Role | Cost (approx) |
|---|---|---|---|
| ESP32 DevKit V1 | 1 | Main microcontroller | ₹350 |
| ADXL345 Accelerometer | 1 | Vibration measurement | ₹120 |
| DHT22 Sensor | 1 | Temperature + Humidity | ₹80 |
| ACS712-30A | 1 | AC/DC current measurement | ₹90 |
| MAX4466 Microphone | 1 | Sound level measurement | ₹75 |
| WS2812B RGB LED | 1 | Status indicator | ₹30 |
| Active Buzzer | 1 | Audio alert | ₹20 |
| 10kΩ Resistor | 1 | DHT22 pull-up | ₹1 |
| Breadboard + Wires | 1 set | Prototyping | ₹60 |
| **Total** | | | **~₹826** |

### Wiring Diagram

```
ESP32 GPIO        Sensor            Notes
─────────────     ────────────────  ──────────────────────────────
3.3V          →   ADXL345 VCC       3.3V only — DO NOT use 5V
GND           →   ADXL345 GND
GPIO21 (SDA)  →   ADXL345 SDA      I2C data
GPIO22 (SCL)  →   ADXL345 SCL      I2C clock

3.3V          →   DHT22 pin 1
GPIO4         →   DHT22 pin 2       Data + 10kΩ pull-up to 3.3V
GND           →   DHT22 pin 4

5V            →   ACS712 VCC        Must be 5V
GND           →   ACS712 GND
GPIO34 (ADC)  →   ACS712 OUT        ADC1_CH6 — no WiFi conflict

3.3V          →   MAX4466 VDD
GND           →   MAX4466 GND
GPIO35 (ADC)  →   MAX4466 OUT       ADC1_CH7

GPIO5         →   WS2812B DIN       NeoPixel data
GPIO18        →   Buzzer (+)        Active buzzer
GND           →   Buzzer (-)
```

### MQTT Telemetry Payload (published every 2s)

```json
{
  "machine_id": "PLI-M001",
  "firmware": "1.2.0",
  "ts": 34521,
  "publish_count": 17,
  "sensors": {
    "temperature_c":   47.3,
    "humidity_pct":    58.2,
    "vibration_g_rms": 0.143,
    "current_a":       8.72,
    "sound_db":        63.4,
    "accel_x": 0.12, "accel_y": -0.03, "accel_z": 9.77
  },
  "alert_level":   0,
  "alert_reason":  "NORMAL",
  "wifi_rssi_dbm": -58
}
```

---

## 🔬 How It Works

### 1. Firmware Sensor Fusion

The ESP32 firmware reads four sensors every 2 seconds and fuses them into a single JSON packet:

```
Vibration RMS = √( Σ(|accel_vector - 1g|²) / N )   over 50 ADXL345 samples
Current RMS   = √( Σ( ((Vadc - 1.65V) / 0.066)² ) / N )   over 500 ADC samples at 10kHz
Temperature   = DHT22 single reading with NaN guard
Sound dB      = 20·log₁₀(Vrms / 0.006) + 94   (approximate SPL)
```

### 2. Twin Synchronisation

Every incoming MQTT packet:
```
MQTTBridge._on_message()
    → TelemetryPacket.from_mqtt_payload(json)     # Parse + validate
    → TwinRegistry.get_or_create(machine_id)       # Get or create twin
    → twin.synchronise(packet)                     # Update virtual state
        → append to _history deque (O(1))
        → compute new MachineState
        → EventBus.publish("telemetry", data)      # Notify WebSocket clients
        → EventBus.publish("state_change", data)   # Only on transitions
```

### 3. Health Scoring Algorithm

```python
health_score = 100.0
health_score -= max(0, (avg_temp - 45) * 0.5)      # penalty: 0.5/°C above 45°C
health_score -= max(0, avg_vibration * 15)           # penalty: 15 points per g RMS
health_score -= max(0, (avg_current - 10) * 0.8)    # penalty: 0.8/A above 10A
health_score -= anomaly_probability * 20             # penalty: up to 20 at full anomaly
health_score -= alerts_last_hour * 3                 # penalty: 3 per alert in last hour
health_score = clamp(health_score, 0, 100)
```

### 4. Statistical Anomaly Detection (Z-Score)

```
For each feature f ∈ {temperature, vibration, current, sound}:
  μ_f  = mean(last W readings of f)
  σ_f  = stdev(last W readings of f)
  Z_f  = |latest_f - μ_f| / σ_f

max_Z = max(Z_temp, Z_vib, Z_cur, Z_sound)

If max_Z > z_threshold:
    anomaly_probability = sigmoid(max_Z - z_threshold)
Else:
    anomaly_probability ≈ 0
```

Default: W=30, z_threshold=2.5 — tunable per deployment.

### 5. WebSocket Real-Time Delivery

```
Twin.synchronise(packet)
    → EventBus.publish("telemetry", packet.to_dict())
        → for each subscriber callback:
              asyncio.run_coroutine_threadsafe(ws.send_json(data), loop)
```
End-to-end latency from physical sensor reading to browser chart update: **< 100ms** over LAN.

---

## ⏱️ Complexity Analysis

| Operation | Time | Space | Notes |
|---|---|---|---|
| `TelemetryPacket.from_mqtt_payload()` | O(1) | O(1) | Fixed-size struct creation |
| `IndustrialMachineTwin.synchronise()` | O(1) amortised | O(W) | deque append + evict |
| `IndustrialMachineTwin.get_health()` | O(W) | O(W) | Single pass over history |
| `StatisticalZScoreDetector.score()` | O(W) | O(W) | 4 feature passes over window |
| `ThresholdDetector.score()` | O(1) | O(1) | Single latest packet only |
| `TwinRegistry.get_or_create()` | O(1) avg | O(M) | HashMap lookup; M=machines |
| `TwinRegistry.fleet_summary()` | O(M·W) | O(M·W) | get_health() per machine |
| `EventBus.publish()` | O(S) | O(1) | S=subscribers per event type |
| `MQTTBridge._on_message()` | O(W) | O(W) | Dominated by synchronise() |
| WebSocket broadcast (K clients) | O(K) | O(1) | One send per connected client |

W = history window (max 300) | M = number of machines | S = subscribers | K = WS clients

### MQTT Payload Budget

| Field | Bytes | % of total |
|---|---|---|
| sensor values (6 floats) | ~100 bytes | 55% |
| metadata (machine_id, ts, etc.) | ~60 bytes | 33% |
| alert fields | ~22 bytes | 12% |
| **Total per packet** | **~182 bytes** | |
| **At 2s interval** | **91 bytes/sec** | LTE-M / NB-IoT compatible |

---

## 📊 API Reference

| Method | Endpoint | Response | Description |
|---|---|---|---|
| `GET` | `/` | JSON | API info + broker status |
| `GET` | `/machines` | JSON | All registered machine IDs |
| `GET` | `/machines/{id}/health` | JSON | Full health report: score, RUL, anomaly prob |
| `GET` | `/machines/{id}/latest` | JSON | Latest raw sensor packet |
| `GET` | `/machines/{id}/history?last_n=60` | JSON | Up to 300 historical packets |
| `POST` | `/machines/{id}/command` | JSON | Send command to ESP32 |
| `GET` | `/fleet/summary` | JSON | Aggregated fleet overview |
| `GET` | `/bridge/status` | JSON | MQTT broker connection stats |
| `WS` | `/ws/{machine_id}` | Stream | Real-time telemetry push |
| `GET` | `/dashboard` | HTML | Live web dashboard |
| `GET` | `/docs` | HTML | Auto-generated Swagger/OpenAPI |

### Sample Health Response

```json
{
  "machine_id":          "PLI-M001",
  "state":               "RUNNING",
  "health_score":        87.40,
  "anomaly_probability": 0.0320,
  "last_seen":           "2026-06-28T14:32:15.412Z",
  "uptime_seconds":      3614.2,
  "total_packets":       1807,
  "alerts_last_hour":    0,
  "avg_temperature_c":   46.30,
  "avg_vibration_g":     0.1440,
  "avg_current_a":       8.55,
  "peak_temperature_c":  54.20,
  "peak_vibration_g":    0.8320,
  "peak_current_a":      11.20,
  "estimated_rul_hours": 7659.8
}
```

---

## 🎯 Interview Questions & Answers

**Q1. What is a Digital Twin? How is it different from a simple sensor dashboard?**
> A dashboard displays raw sensor data; a Digital Twin maintains a stateful virtual model of the physical object. The twin persists state when the device is offline, can run simulations, executes predictive algorithms (anomaly detection, RUL), and decouples all consumers (dashboards, SCADA, APIs) from the physical hardware. If the machine goes offline for 2 hours, the twin still has 2 hours of history and can answer "what was the temperature at 3 PM?"

**Q2. Why MQTT instead of HTTP for IoT telemetry?**
> MQTT is a publish-subscribe protocol designed for constrained devices: (1) **Binary header** = 2 bytes vs HTTP's ~300-byte text headers — critical on NB-IoT links; (2) **Persistent sessions** — broker queues messages for offline clients; (3) **QoS levels** — 0=fire-and-forget, 1=at-least-once, 2=exactly-once; (4) **Topic wildcards** — `dt/machine/+/telemetry` subscribes to all machines simultaneously; (5) **Broker fan-out** — one publish reaches 1000 subscribers without device knowing how many exist.

**Q3. Explain the Strategy pattern used in AnomalyDetector.**
> `AnomalyDetector` is an abstract base class with a single `score(history) → float` method. `StatisticalZScoreDetector` and `ThresholdDetector` are two concrete implementations. `IndustrialMachineTwin` receives a detector via constructor injection. At runtime, the twin calls `self._detector.score(history)` without knowing which algorithm it's using — this is runtime polymorphism. To add a new algorithm (e.g. LSTM-based), I implement `AnomalyDetector`, inject it — zero changes to the twin.

**Q4. How does the Observer pattern enable real-time WebSocket delivery?**
> `IndustrialMachineTwin` has an internal `EventBus`. Dashboard WebSocket handlers call `twin.subscribe("telemetry", callback)`. When `synchronise()` processes a new packet, it calls `event_bus.publish("telemetry", data)`, which invokes every registered callback — including the FastAPI WebSocket sender — within the same thread. `asyncio.run_coroutine_threadsafe()` bridges from the paho-mqtt background thread to the FastAPI async event loop without blocking either.

**Q5. Why is TelemetryPacket a frozen dataclass?**
> Sensor readings are immutable facts — once a temperature reading says 47.3°C at 14:32:15 UTC, that fact should never change. Making `TelemetryPacket` frozen=True enforces this at the Python level: any attempt to mutate a field raises `FrozenInstanceError`. This prevents bugs where a processing step accidentally modifies a packet that's shared across multiple concurrent readers (the history deque is shared between the MQTT thread and API request handlers).

**Q6. How do you handle thread safety in TwinRegistry and IndustrialMachineTwin?**
> `TwinRegistry` uses `threading.Lock` around dict reads/writes — paho-mqtt callbacks run in a background thread while FastAPI serves HTTP requests on another. `IndustrialMachineTwin.synchronise()` acquires `threading.RLock` (reentrant) before modifying `_history` and `_state` — RLock because `synchronise()` calls `is_online()` which also acquires the same lock. `EventBus._lock` is a separate Lock protecting the subscriber list from concurrent subscribe/unsubscribe during publish.

**Q7. What is Remaining Useful Life (RUL) and how is it estimated here?**
> RUL is the time remaining before a machine requires maintenance or will fail. This implementation uses a simple linear model: `RUL = (health_score / 100) × 8760 hours` — a machine at 100% health has ~1 year of life; at 50% health, ~6 months. Production systems use more sophisticated approaches: Wiener process degradation models, LSTM sequence models trained on failure history, or Weibull survival analysis. The heuristic here is documented as such and listed as a Future Enhancement.

**Q8. How would you scale this system to 10,000 machines?**
> Single-process Python with in-memory state breaks at ~100 machines. To scale: (1) Shard twin instances across processes by machine_id hash; (2) Replace in-memory `TwinRegistry` with Redis — store serialised `MachineHealth` with TTL; (3) Kafka instead of Mosquitto — partitioned by machine_id, consumer groups for parallel processing; (4) TimescaleDB (PostgreSQL extension) for time-series telemetry history instead of in-memory deques; (5) FastAPI with multiple uvicorn workers behind nginx; (6) Deploy on Kubernetes with auto-scaling based on MQTT message lag.

**Q9. What is the difference between QoS 0, 1, and 2 in MQTT?**
> QoS 0 (at-most-once): fire-and-forget, no acknowledgement — lowest latency, possible data loss. QoS 1 (at-least-once): broker acknowledges; sender retries until ack — guaranteed delivery but possible duplicates. QoS 2 (exactly-once): four-way handshake (PUBLISH→PUBREC→PUBREL→PUBCOMP) — guaranteed exactly once but highest overhead. This system uses QoS 1 for telemetry (duplicates tolerable, loss is not) and QoS 1 for commands (must arrive, idempotent with machine-side deduplication).

**Q10. How does the firmware handle ADC noise for current measurement?**
> The ACS712 output is an AC signal centred at Vcc/2 (1.65V). Instantaneous readings are noisy. The firmware takes 500 ADC samples at ~10kHz (100μs intervals), computes the mean-square `Σ(V-1.65)²/500`, then takes the square root — this is RMS (Root Mean Square) which gives the true effective current regardless of waveform shape. The 500-sample window covers 25 full cycles at 50Hz mains frequency, averaging out mains ripple completely.

---

## 🚀 Future Enhancements

| Priority | Enhancement | Details |
|---|---|---|
| 🔴 High | **LSTM Anomaly Detection** | Replace Z-score with LSTM sequence model trained on normal operation; learns seasonal patterns and trend-based degradation |
| 🔴 High | **InfluxDB + Grafana** | Replace in-memory deque with InfluxDB time-series DB; Grafana dashboards with alerting rules |
| 🔴 High | **OTA Firmware Updates** | Implement ESP32 OTA via `Update.h`; backend posts new firmware binary via MQTT |
| 🟡 Medium | **Multi-Machine Dashboard** | Fleet overview showing all machines on a single map with colour-coded health circles |
| 🟡 Medium | **Email/WhatsApp Alerts** | Trigger Twilio/SendGrid notifications on CRITICAL state with health report PDF |
| 🟡 Medium | **LoRaWAN Support** | Replace WiFi+MQTT with LoRa SX1276 for deployments without WiFi coverage (factories, farms) |
| 🟡 Medium | **Predictive Maintenance Schedule** | Use RUL estimates to generate maintenance work orders in advance |
| 🟡 Medium | **REST Command Validation** | Add Pydantic models for `POST /command` with allowed command enumeration |
| 🟢 Low | **Docker Compose** | Single `docker-compose up` starts Mosquitto + Python backend + Grafana |
| 🟢 Low | **Wiener Process RUL** | Replace heuristic RUL with physics-based stochastic degradation model |
| 🟢 Low | **Authentication** | JWT-based API authentication + MQTT username/password or TLS client certificates |

---

## 📚 References

1. **Grieves, M. (2014).** *Digital twin: Manufacturing excellence through virtual factory replication.* White Paper, Florida Institute of Technology.

2. **Tao, F., Cheng, J., Qi, Q., Zhang, M., Zhang, H., & Sui, F. (2018).** *Digital twin-driven product design, manufacturing and service with big data.* The International Journal of Advanced Manufacturing Technology, 94, 3563–3576.

3. **Espressif Systems. (2023).** *ESP32 Technical Reference Manual v5.1.* Espressif Systems, Shanghai.

4. **Banks, A., & Gupta, R. (2014).** *MQTT Version 3.1.1.* OASIS Standard. OASIS Open.

5. **McKinsey & Company. (2021).** *The state of Industry 4.0: Digitizing the physical world.* McKinsey Digital.

---

## 🤝 Contributing

Pull requests welcome. Please:
1. Open an Issue first describing the proposed change
2. All tests must pass: `pytest tests/ -v`
3. Follow the existing docstring + type annotation style
4. Add tests for new functionality

---

## 📄 License

MIT License — Copyright (c) 2026 Kushagra Bansal — Project Lab India

See [LICENSE](LICENSE) for full terms.

---

<div align="center">

## 👨‍💻 Author

**Kushagra Bansal**
*Founder @ Project Lab India | Jaipur, Rajasthan, India*

IoT & Embedded Systems • Digital Twins • Industry 4.0 • Python Backend • ESP32

🏆 Innovation Award — MNIT Jaipur | IEEE Member | RTU B.Tech IT (2024–28)

[![GitHub](https://img.shields.io/badge/GitHub-kushagrabansal--IOT-181717?style=flat&logo=github)](https://github.com/kushagrabansal-IOT)
[![Website](https://img.shields.io/badge/Website-radiomarket.in-00C853?style=flat&logo=google-chrome)](https://radiomarket.in)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-kushagrabansal123-0077B5?style=flat&logo=linkedin)](https://linkedin.com/in/kushagrabansal123)

---

⭐ **Star this repo** if it helped you understand Digital Twins or IoT architecture!

**Karte raho. Seekhte raho. Build karte raho. 🚀**

</div>
