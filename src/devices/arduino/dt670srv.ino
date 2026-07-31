// dt670srv — main DT-670 temperature readout firmware.
//
// Reads the diode voltage differentially on ADS1115 A0−A1 (PGA ±2.048 V,
// 62.5 µV/LSB, 860 SPS), averages 64 samples (~75 ms per burst), converts to
// kelvin via the official Lake Shore Curve DT-670 breakpoint table (datasheet
// appendix, 50–440 K span) with linear interpolation, and serves the latest
// reading as JSON over HTTP on 192.168.2.2:80 (W5500 Ethernet Shield 2).
//
//   GET /  →  {"v":0.40123,"t_k":368.42,"t_c":95.27,"flag":"ok","age_ms":31}
//
// flag: "ok" | "open" (V near rail → broken wire / empty seat)
//     | "reversed" (negative V → diode polarity swapped)
//     | "out_of_range" (V valid but outside curve table)
// t_k/t_c are null when the flag is not "ok".
//
// Serial debug mirror at 115200 baud, one line per burst.

#include <SPI.h>
#include <Ethernet.h>
#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <avr/pgmspace.h>

byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0x67, 0x00 };
IPAddress ip(192, 168, 2, 2);
EthernetServer server(80);
Adafruit_ADS1115 ads;

// Lake Shore Curve DT-670 breakpoints (datasheet appendix), 50–440 K.
// Voltage falls monotonically with temperature.
struct CurvePoint { float t; float v; };
const CurvePoint CURVE[] PROGMEM = {
  {  50.00f, 1.073099f }, {  52.00f, 1.069881f }, {  54.00f, 1.066650f },
  {  56.00f, 1.063403f }, {  58.00f, 1.060141f }, {  60.00f, 1.056862f },
  {  65.00f, 1.048584f }, {  70.00f, 1.040183f }, {  75.00f, 1.031651f },
  {  77.35f, 1.027594f }, {  80.00f, 1.022984f }, {  85.00f, 1.014181f },
  {  90.00f, 1.005244f }, { 100.00f, 0.986974f }, { 110.00f, 0.968209f },
  { 120.00f, 0.949000f }, { 130.00f, 0.929390f }, { 140.00f, 0.909416f },
  { 150.00f, 0.889114f }, { 160.00f, 0.868518f }, { 170.00f, 0.847659f },
  { 180.00f, 0.826560f }, { 190.00f, 0.805242f }, { 200.00f, 0.783720f },
  { 210.00f, 0.762007f }, { 220.00f, 0.740115f }, { 230.00f, 0.718054f },
  { 240.00f, 0.695834f }, { 250.00f, 0.673462f }, { 260.00f, 0.650949f },
  { 270.00f, 0.628302f }, { 273.00f, 0.621141f }, { 280.00f, 0.605528f },
  { 290.00f, 0.582637f }, { 300.00f, 0.559639f }, { 310.00f, 0.536542f },
  { 320.00f, 0.513361f }, { 330.00f, 0.490106f }, { 340.00f, 0.466760f },
  { 350.00f, 0.443371f }, { 360.00f, 0.419960f }, { 370.00f, 0.396503f },
  { 380.00f, 0.373002f }, { 390.00f, 0.349453f }, { 400.00f, 0.325839f },
  { 410.00f, 0.302161f }, { 420.00f, 0.278416f }, { 430.00f, 0.254592f },
  { 440.00f, 0.230697f },
};
const uint8_t N_CURVE = sizeof(CURVE) / sizeof(CURVE[0]);

// Latest measurement, updated every burst, served on request.
float lastV = 0.0f;
float lastTk = NAN;
unsigned long lastMs = 0;
enum Flag : uint8_t { F_OK, F_OPEN, F_REVERSED, F_RANGE };
Flag lastFlag = F_RANGE;

float curveT(uint8_t i) { return pgm_read_float(&CURVE[i].t); }
float curveV(uint8_t i) { return pgm_read_float(&CURVE[i].v); }

// Linear interpolation on the breakpoint table; NAN outside its span.
float voltsToKelvin(float v) {
  if (v > curveV(0) || v < curveV(N_CURVE - 1)) return NAN;
  for (uint8_t i = 1; i < N_CURVE; i++) {
    if (v >= curveV(i)) {
      float v0 = curveV(i - 1), v1 = curveV(i);
      float t0 = curveT(i - 1), t1 = curveT(i);
      return t0 + (t1 - t0) * (v - v0) / (v1 - v0);
    }
  }
  return NAN;
}

void measure() {
  long sum = 0;
  for (uint8_t i = 0; i < 64; i++) {
    sum += ads.readADC_Differential_0_1();
  }
  lastV = (sum / 64.0f) * 0.0000625f;  // 62.5 µV/LSB at GAIN_TWO
  lastMs = millis();

  if (lastV < -0.05f)      { lastFlag = F_REVERSED; lastTk = NAN; }
  else if (lastV > 1.5f)   { lastFlag = F_OPEN;     lastTk = NAN; }
  else {
    lastTk = voltsToKelvin(lastV);
    lastFlag = isnan(lastTk) ? F_RANGE : F_OK;
  }
}

const char* flagStr(Flag f) {
  switch (f) {
    case F_OK:       return "ok";
    case F_OPEN:     return "open";
    case F_REVERSED: return "reversed";
    default:         return "out_of_range";
  }
}

void sendJson(EthernetClient& client) {
  // Body assembled in RAM first so Content-Length is exact.
  char body[128];
  char vbuf[12], tkbuf[12], tcbuf[12];
  dtostrf(lastV, 1, 5, vbuf);
  if (lastFlag == F_OK) {
    dtostrf(lastTk, 1, 2, tkbuf);
    dtostrf(lastTk - 273.15f, 1, 2, tcbuf);
  } else {
    strcpy(tkbuf, "null");
    strcpy(tcbuf, "null");
  }
  snprintf(body, sizeof(body),
           "{\"v\":%s,\"t_k\":%s,\"t_c\":%s,\"flag\":\"%s\",\"age_ms\":%lu}",
           vbuf, tkbuf, tcbuf, flagStr(lastFlag), millis() - lastMs);

  client.print(F("HTTP/1.1 200 OK\r\n"
                 "Content-Type: application/json\r\n"
                 "Connection: close\r\n"
                 "Content-Length: "));
  client.print(strlen(body));
  client.print(F("\r\n\r\n"));
  client.print(body);
}

void serveClients() {
  EthernetClient client = server.available();
  if (!client) return;
  // Discard the request (only GET / is meaningful) up to the blank line.
  unsigned long t0 = millis();
  while (client.connected() && millis() - t0 < 500) {
    if (client.available()) {
      char c = client.read();
      static char prev = 0;
      if (c == '\n' && prev == '\n') break;  // end of headers (\r stripped below)
      if (c != '\r') prev = c;
    }
  }
  sendJson(client);
  client.flush();
  delay(1);
  client.stop();
}

void setup() {
  Serial.begin(115200);

  Ethernet.init(10);  // W5500 CS pin on Ethernet Shield 2
  Ethernet.begin(mac, ip);
  server.begin();
  if (Ethernet.hardwareStatus() == EthernetNoHardware) {
    Serial.println(F("ERROR: no W5500 detected (SPI problem?)"));
  }

  if (!ads.begin(0x48)) {
    Serial.println(F("ERROR: ADS1115 not found at 0x48 (check SDA->A4, SCL->A5, VDD, GND)"));
    while (true) delay(1000);
  }
  ads.setGain(GAIN_TWO);                    // ±2.048 V range
  ads.setDataRate(RATE_ADS1115_860SPS);     // 64-sample burst ≈ 75 ms

  Serial.print(F("dt670srv up, IP: "));
  Serial.println(Ethernet.localIP());
}

void loop() {
  measure();
  serveClients();

  Serial.print(F("V="));
  Serial.print(lastV, 5);
  Serial.print(F(" T_K="));
  Serial.print(lastTk, 2);
  Serial.print(F(" flag="));
  Serial.println(flagStr(lastFlag));
}
