/*
 * ESP32 Digital Twin Industrial Monitor — Firmware
 * ═══════════════════════════════════════════════════════════════════════
 * Author      : Kushagra Bansal — Project Lab India
 * GitHub      : github.com/kushagrabansal-IOT
 * Repository  : ESP32-Digital-Twin-Industrial-Monitor
 *
 * Description :
 *   Industrial-grade firmware for ESP32 that continuously reads multi-sensor
 *   data from a physical machine and publishes JSON telemetry to an MQTT
 *   broker every 2 seconds. A Python Digital Twin Engine subscribes to this
 *   stream, maintains a real-time virtual replica of the physical machine,
 *   detects anomalies, and exposes REST + WebSocket APIs for dashboards.
 *
 * Hardware Required:
 *   • ESP32 DevKit V1 (any 38-pin or 30-pin variant)
 *   • ADXL345 3-axis accelerometer   → I2C: SDA=GPIO21, SCL=GPIO22
 *   • DHT22 temperature/humidity     → GPIO4
 *   • ACS712-30A current sensor      → GPIO34 (ADC1_CH6)
 *   • Sound level sensor (MAX4466)   → GPIO35 (ADC1_CH7)
 *   • WS2812B RGB LED (status)       → GPIO5
 *   • Active buzzer                  → GPIO18
 *
 * Libraries (install via Arduino IDE Library Manager):
 *   • PubSubClient v2.8.0            (MQTT)
 *   • ArduinoJson v6.21.3            (JSON serialisation)
 *   • Adafruit ADXL345 v1.3.2        (accelerometer)
 *   • DHT sensor library v1.4.4      (temperature/humidity)
 *   • Adafruit NeoPixel v1.11.0      (RGB LED)
 *
 * MQTT Topics Published:
 *   dt/machine/PLI-M001/telemetry    → full sensor JSON every 2s
 *   dt/machine/PLI-M001/heartbeat   → device health every 30s
 *   dt/machine/PLI-M001/alert       → anomaly alert (on detection)
 *
 * MQTT Topics Subscribed:
 *   dt/machine/PLI-M001/command     → commands from Digital Twin Engine
 *
 * Commands:
 *   git clone https://github.com/kushagrabansal-IOT/ESP32-Digital-Twin-Industrial-Monitor
 *   Open firmware/main.ino in Arduino IDE
 *   Set WIFI_SSID, WIFI_PASSWORD, MQTT_SERVER below
 *   Board: ESP32 Dev Module | Flash: 4MB | Upload Speed: 921600
 *   Upload → Open Serial Monitor @ 115200 baud
 * ═══════════════════════════════════════════════════════════════════════
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_ADXL345_U.h>
#include <DHT.h>
#include <Adafruit_NeoPixel.h>

// ── CONFIGURATION ──────────────────────────────────────────────────────
#define WIFI_SSID           "YOUR_WIFI_SSID"
#define WIFI_PASSWORD       "YOUR_WIFI_PASSWORD"
#define MQTT_SERVER         "192.168.1.100"     // IP of Raspberry Pi / server
#define MQTT_PORT           1883
#define MQTT_USER           ""                  // Leave empty if no auth
#define MQTT_PASS           ""
#define MACHINE_ID          "PLI-M001"
#define FIRMWARE_VERSION    "1.2.0"

// ── PIN DEFINITIONS ────────────────────────────────────────────────────
#define DHT_PIN             4
#define DHT_TYPE            DHT22
#define CURRENT_SENSOR_PIN  34
#define SOUND_SENSOR_PIN    35
#define LED_PIN             5
#define LED_COUNT           1
#define BUZZER_PIN          18
#define STATUS_LED_PIN      2     // Built-in LED

// ── MQTT TOPICS ────────────────────────────────────────────────────────
const char* TOPIC_TELEMETRY  = "dt/machine/PLI-M001/telemetry";
const char* TOPIC_HEARTBEAT  = "dt/machine/PLI-M001/heartbeat";
const char* TOPIC_ALERT      = "dt/machine/PLI-M001/alert";
const char* TOPIC_COMMAND    = "dt/machine/PLI-M001/command";

// ── THRESHOLDS (calibrate per machine) ─────────────────────────────────
const float TEMP_MAX         = 80.0;    // °C — critical overheat
const float TEMP_WARN        = 65.0;    // °C — warning
const float VIBRATION_MAX    = 3.0;     // g  — critical vibration
const float VIBRATION_WARN   = 1.8;     // g  — warning
const float CURRENT_MAX      = 25.0;    // A  — overload
const float CURRENT_WARN     = 18.0;    // A  — warning
const float HUMIDITY_MAX     = 90.0;    // %  — condensation risk
const unsigned long TELEMETRY_INTERVAL  = 2000;   // ms
const unsigned long HEARTBEAT_INTERVAL  = 30000;  // ms

// ── OBJECTS ────────────────────────────────────────────────────────────
WiFiClient          wifi_client;
PubSubClient        mqtt(wifi_client);
Adafruit_ADXL345_Unified accel(12345);
DHT                 dht(DHT_PIN, DHT_TYPE);
Adafruit_NeoPixel   status_led(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);

// ── STATE ──────────────────────────────────────────────────────────────
unsigned long last_telemetry  = 0;
unsigned long last_heartbeat  = 0;
unsigned long boot_time       = 0;
uint32_t      publish_count   = 0;
bool          accel_ok        = false;
bool          dht_ok          = false;

// ── SENSOR READINGS STRUCT ─────────────────────────────────────────────
struct SensorReading {
  float temperature;
  float humidity;
  float vibration_rms;
  float current_a;
  float sound_db;
  float accel_x, accel_y, accel_z;
  int   alert_level;         // 0=OK, 1=WARNING, 2=CRITICAL
  char  alert_reason[64];
};

// ── FUNCTION PROTOTYPES ─────────────────────────────────────────────────
void connect_wifi();
void connect_mqtt();
void on_mqtt_message(char* topic, byte* payload, unsigned int length);
SensorReading read_all_sensors();
float read_current_amps();
float read_sound_db();
float calculate_vibration_rms(int samples);
int   evaluate_alert(SensorReading& r);
void  publish_telemetry(SensorReading& r);
void  publish_heartbeat();
void  publish_alert(SensorReading& r);
void  set_status_led(int alert_level);
void  beep(int times, int duration_ms);

// ─────────────────────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n╔══════════════════════════════════════════════╗");
  Serial.println("║  ESP32 Digital Twin Industrial Monitor        ║");
  Serial.println("║  Project Lab India | Kushagra Bansal          ║");
  Serial.println("╚══════════════════════════════════════════════╝");
  Serial.printf("  Machine ID      : %s\n", MACHINE_ID);
  Serial.printf("  Firmware        : v%s\n", FIRMWARE_VERSION);

  // GPIO setup
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // NeoPixel
  status_led.begin();
  status_led.setBrightness(80);
  set_status_led(0);

  // DHT22
  dht.begin();
  dht_ok = !isnan(dht.readTemperature());
  Serial.printf("  DHT22           : %s\n", dht_ok ? "✓ OK" : "✗ FAIL");

  // ADXL345
  if (accel.begin()) {
    accel_ok = true;
    accel.setRange(ADXL345_RANGE_4_G);
    accel.setDataRate(ADXL345_DATARATE_100_HZ);
    Serial.println("  ADXL345         : ✓ OK (±4g, 100Hz)");
  } else {
    Serial.println("  ADXL345         : ✗ FAIL — check wiring");
  }

  // ADC
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  Serial.println("  ADC (Current)   : ✓ 12-bit, 11dB");

  connect_wifi();
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(on_mqtt_message);
  mqtt.setBufferSize(1024);
  connect_mqtt();

  boot_time = millis();
  beep(2, 100);
  Serial.println("\n  ✅ All systems GO — publishing telemetry...\n");
}

// ─────────────────────────────────────────────────────────────────────────
// LOOP
// ─────────────────────────────────────────────────────────────────────────
void loop() {
  if (!mqtt.connected()) connect_mqtt();
  mqtt.loop();

  unsigned long now = millis();

  // Telemetry every 2 seconds
  if (now - last_telemetry >= TELEMETRY_INTERVAL) {
    last_telemetry = now;
    SensorReading reading = read_all_sensors();
    evaluate_alert(reading);
    publish_telemetry(reading);
    set_status_led(reading.alert_level);

    if (reading.alert_level == 2) {
      publish_alert(reading);
      beep(3, 150);
    }
  }

  // Heartbeat every 30 seconds
  if (now - last_heartbeat >= HEARTBEAT_INTERVAL) {
    last_heartbeat = now;
    publish_heartbeat();
  }
}

// ─────────────────────────────────────────────────────────────────────────
// SENSOR READING
// ─────────────────────────────────────────────────────────────────────────
SensorReading read_all_sensors() {
  SensorReading r;
  memset(&r, 0, sizeof(r));

  // DHT22 — temperature and humidity
  r.temperature = dht.readTemperature();
  r.humidity    = dht.readHumidity();
  if (isnan(r.temperature)) r.temperature = -999;
  if (isnan(r.humidity))    r.humidity    = -999;

  // ADXL345 — vibration RMS
  r.vibration_rms = calculate_vibration_rms(50);
  if (accel_ok) {
    sensors_event_t event;
    accel.getEvent(&event);
    r.accel_x = event.acceleration.x;
    r.accel_y = event.acceleration.y;
    r.accel_z = event.acceleration.z;
  }

  // ACS712 — current draw
  r.current_a = read_current_amps();

  // MAX4466 — ambient sound level
  r.sound_db = read_sound_db();

  return r;
}

float calculate_vibration_rms(int samples) {
  if (!accel_ok) return 0.0;
  float sum_sq = 0;
  for (int i = 0; i < samples; i++) {
    sensors_event_t event;
    accel.getEvent(&event);
    float mag = sqrt(event.acceleration.x * event.acceleration.x +
                     event.acceleration.y * event.acceleration.y +
                     event.acceleration.z * event.acceleration.z) - 9.81;
    sum_sq += mag * mag;
    delayMicroseconds(500);  // 2kHz sampling → RMS window ≈ 25ms
  }
  return sqrt(sum_sq / samples) / 9.81;  // normalise to g
}

float read_current_amps() {
  // ACS712-30A: sensitivity = 66mV/A, Vref = VCC/2 = 1.65V at 3.3V supply
  const int SAMPLES = 500;
  float sum = 0;
  for (int i = 0; i < SAMPLES; i++) {
    float v = analogRead(CURRENT_SENSOR_PIN) * (3.3 / 4095.0);
    float i_raw = (v - 1.65) / 0.066;  // ACS712-30A: 66mV/A
    sum += i_raw * i_raw;
    delayMicroseconds(100);
  }
  return sqrt(sum / SAMPLES);  // RMS current
}

float read_sound_db() {
  const int SAMPLES = 200;
  float sum = 0;
  for (int i = 0; i < SAMPLES; i++) {
    float v = analogRead(SOUND_SENSOR_PIN) * (3.3 / 4095.0);
    sum += v * v;
    delayMicroseconds(200);
  }
  float vrms = sqrt(sum / SAMPLES);
  // Convert Vrms → dB SPL (approximate, sensor-dependent calibration)
  float db = 20.0 * log10(vrms / 0.006) + 94.0;
  return constrain(db, 30.0, 120.0);
}

// ─────────────────────────────────────────────────────────────────────────
// ALERT EVALUATION
// ─────────────────────────────────────────────────────────────────────────
int evaluate_alert(SensorReading& r) {
  r.alert_level = 0;
  strcpy(r.alert_reason, "NORMAL");

  if (r.temperature  >= TEMP_MAX  || r.vibration_rms >= VIBRATION_MAX || r.current_a >= CURRENT_MAX) {
    r.alert_level = 2;
    if (r.temperature  >= TEMP_MAX)     snprintf(r.alert_reason, 64, "CRITICAL_OVERHEAT:%.1f°C",    r.temperature);
    if (r.vibration_rms >= VIBRATION_MAX) snprintf(r.alert_reason, 64, "CRITICAL_VIBRATION:%.2fg",  r.vibration_rms);
    if (r.current_a    >= CURRENT_MAX)  snprintf(r.alert_reason, 64, "CRITICAL_OVERCURRENT:%.1fA",  r.current_a);
  } else if (r.temperature  >= TEMP_WARN || r.vibration_rms >= VIBRATION_WARN || r.current_a >= CURRENT_WARN) {
    r.alert_level = 1;
    if (r.temperature  >= TEMP_WARN)    snprintf(r.alert_reason, 64, "WARN_TEMP:%.1f°C",    r.temperature);
    if (r.vibration_rms >= VIBRATION_WARN) snprintf(r.alert_reason, 64, "WARN_VIBRATION:%.2fg", r.vibration_rms);
    if (r.current_a    >= CURRENT_WARN) snprintf(r.alert_reason, 64, "WARN_CURRENT:%.1fA",  r.current_a);
  }
  return r.alert_level;
}

// ─────────────────────────────────────────────────────────────────────────
// MQTT PUBLISH
// ─────────────────────────────────────────────────────────────────────────
void publish_telemetry(SensorReading& r) {
  StaticJsonDocument<512> doc;
  doc["machine_id"]     = MACHINE_ID;
  doc["firmware"]       = FIRMWARE_VERSION;
  doc["ts"]             = millis();
  doc["publish_count"]  = ++publish_count;

  JsonObject sensors = doc.createNestedObject("sensors");
  sensors["temperature_c"]   = round(r.temperature * 10.0) / 10.0;
  sensors["humidity_pct"]    = round(r.humidity * 10.0) / 10.0;
  sensors["vibration_g_rms"] = round(r.vibration_rms * 1000.0) / 1000.0;
  sensors["current_a"]       = round(r.current_a * 100.0) / 100.0;
  sensors["sound_db"]        = round(r.sound_db * 10.0) / 10.0;
  sensors["accel_x"]         = round(r.accel_x * 1000.0) / 1000.0;
  sensors["accel_y"]         = round(r.accel_y * 1000.0) / 1000.0;
  sensors["accel_z"]         = round(r.accel_z * 1000.0) / 1000.0;

  doc["alert_level"]    = r.alert_level;
  doc["alert_reason"]   = r.alert_reason;
  doc["wifi_rssi_dbm"]  = WiFi.RSSI();

  char buf[512];
  serializeJson(doc, buf);
  mqtt.publish(TOPIC_TELEMETRY, buf, true);  // retain=true

  Serial.printf("  [T+%lus] TEMP=%.1f°C VIB=%.3fg CUR=%.1fA SOUND=%.1fdB ALERT=%d\n",
    millis()/1000, r.temperature, r.vibration_rms, r.current_a, r.sound_db, r.alert_level);
}

void publish_heartbeat() {
  StaticJsonDocument<256> doc;
  doc["machine_id"]      = MACHINE_ID;
  doc["uptime_sec"]      = (millis() - boot_time) / 1000;
  doc["free_heap_bytes"] = ESP.getFreeHeap();
  doc["wifi_rssi_dbm"]   = WiFi.RSSI();
  doc["publish_count"]   = publish_count;
  doc["dht_ok"]          = dht_ok;
  doc["accel_ok"]        = accel_ok;
  doc["firmware"]        = FIRMWARE_VERSION;

  char buf[256];
  serializeJson(doc, buf);
  mqtt.publish(TOPIC_HEARTBEAT, buf, false);
  Serial.printf("  [HEARTBEAT] uptime=%lus heap=%u\n",
    (millis() - boot_time)/1000, ESP.getFreeHeap());
}

void publish_alert(SensorReading& r) {
  StaticJsonDocument<256> doc;
  doc["machine_id"]   = MACHINE_ID;
  doc["alert_level"]  = r.alert_level;
  doc["reason"]       = r.alert_reason;
  doc["temperature"]  = r.temperature;
  doc["vibration"]    = r.vibration_rms;
  doc["current"]      = r.current_a;
  doc["ts"]           = millis();

  char buf[256];
  serializeJson(doc, buf);
  mqtt.publish(TOPIC_ALERT, buf, false);
  Serial.printf("  🚨 ALERT published: %s\n", r.alert_reason);
}

// ─────────────────────────────────────────────────────────────────────────
// MQTT COMMAND HANDLER
// ─────────────────────────────────────────────────────────────────────────
void on_mqtt_message(char* topic, byte* payload, unsigned int length) {
  char msg[256]; length = min(length, (unsigned int)255);
  memcpy(msg, payload, length); msg[length] = '\0';

  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, msg) != DeserializationError::Ok) return;

  const char* cmd = doc["cmd"];
  if (!cmd) return;

  if (strcmp(cmd, "set_threshold") == 0) {
    Serial.printf("  [CMD] set_threshold received — implement per deployment\n");
  } else if (strcmp(cmd, "reboot") == 0) {
    Serial.println("  [CMD] Rebooting in 2s...");
    delay(2000); ESP.restart();
  } else if (strcmp(cmd, "led_test") == 0) {
    for (int i = 0; i < 3; i++) {
      set_status_led(i); delay(500);
    }
    set_status_led(0);
  } else if (strcmp(cmd, "beep") == 0) {
    beep(3, 200);
  }
}

// ─────────────────────────────────────────────────────────────────────────
// CONNECTIVITY
// ─────────────────────────────────────────────────────────────────────────
void connect_wifi() {
  Serial.printf("\n  Connecting to WiFi: %s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 30) {
    delay(500); Serial.print("."); tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n  ✅ WiFi OK | IP: %s | RSSI: %d dBm\n",
      WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("\n  ❌ WiFi FAILED — continuing offline");
  }
}

void connect_mqtt() {
  int tries = 0;
  while (!mqtt.connected() && tries < 5) {
    Serial.printf("  MQTT connecting to %s:%d ...", MQTT_SERVER, MQTT_PORT);
    String client_id = String("esp32-dt-") + MACHINE_ID + "-" + String(random(0xffff), HEX);
    bool ok = strlen(MQTT_USER) > 0
      ? mqtt.connect(client_id.c_str(), MQTT_USER, MQTT_PASS)
      : mqtt.connect(client_id.c_str());
    if (ok) {
      mqtt.subscribe(TOPIC_COMMAND);
      Serial.println(" ✅ connected");
      return;
    }
    Serial.printf(" ❌ rc=%d — retry in 3s\n", mqtt.state());
    delay(3000); tries++;
  }
}

// ─────────────────────────────────────────────────────────────────────────
// UTILITIES
// ─────────────────────────────────────────────────────────────────────────
void set_status_led(int alert_level) {
  switch (alert_level) {
    case 0: status_led.setPixelColor(0, status_led.Color(0, 50, 0));   break; // green  = OK
    case 1: status_led.setPixelColor(0, status_led.Color(50, 25, 0));  break; // orange = warning
    case 2: status_led.setPixelColor(0, status_led.Color(50, 0, 0));   break; // red    = critical
  }
  status_led.show();
  digitalWrite(STATUS_LED_PIN, alert_level == 0 ? LOW : HIGH);
}

void beep(int times, int duration_ms) {
  for (int i = 0; i < times; i++) {
    digitalWrite(BUZZER_PIN, HIGH); delay(duration_ms);
    digitalWrite(BUZZER_PIN, LOW);  delay(duration_ms);
  }
}
