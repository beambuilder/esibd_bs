#include <OneWire.h>
#include <DallasTemperature.h>

// ---------- Pin Definitions ----------
#define ONE_WIRE_BUS 14   // DS18B20 temperature sensor
#define FAN_PWM       9   // Fan MOSFET (PWM)
#define FLOW_PIN_1    2   // Flow sensor 1 (INT0)
#define FLOW_PIN_2    3   // Flow sensor 2 (INT1)

// ---------- Temperature / Fan ----------
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

const float minTemp = 20.0;  // Fan off below this
const float maxTemp = 25.0;  // Fan 100% at/above this
int currentSpeed = 0;
unsigned int lineCount = 0;

// ---------- Flow Sensors ----------
// 552 pulses per litre (from supplier datasheet)
const float pulsesPerLitre = 552.0;

volatile unsigned int flowPulses1 = 0;
volatile unsigned int flowPulses2 = 0;

float flowRate1 = 0.0;  // L/min
float flowRate2 = 0.0;  // L/min

unsigned long lastFlowCalc = 0;
const unsigned long flowInterval = 2000;  // recalculate every 2 seconds

// ---------- Interrupt Handlers ----------
void flowISR1() {
    flowPulses1++;
}

void flowISR2() {
    flowPulses2++;
}

// ---------- Setup ----------
void setup() {
    pinMode(FAN_PWM, OUTPUT);
    pinMode(FLOW_PIN_1, INPUT_PULLUP);
    pinMode(FLOW_PIN_2, INPUT_PULLUP);

    Serial.begin(9600);

    /* Warten, bis der USB-CDC-Port enumeriert ist.
       -  Bei direkter Verbindung zum PC genuegt < 1 s.
       -  Timeout sorgt dafuer, dass das Programm auch ohne offenen
          Terminal weiterlaeuft (z. B. nach Stromausfall im Stand-Alone-Betrieb). */
    unsigned long t0 = millis();
    while (!Serial && millis() - t0 < 3000) { }   // max. 3 s warten

    sensors.begin();



    attachInterrupt(digitalPinToInterrupt(FLOW_PIN_1), flowISR1, FALLING);
    attachInterrupt(digitalPinToInterrupt(FLOW_PIN_2), flowISR2, FALLING);

    lastFlowCalc = millis();
}

// ---------- Read Temperature ----------
float readTemperature() {
    sensors.requestTemperatures();
    return sensors.getTempCByIndex(0);
}

// ---------- Calculate Fan Speed (linear curve) ----------
int calculateFanSpeed(float temperature) {
    if (temperature <= minTemp)      return 0;
    else if (temperature >= maxTemp)  return 255;
    else return map(temperature * 10, minTemp * 10, maxTemp * 10, 0, 255);
}

// ---------- Soft-ramp Fan Speed ----------
void updateFanSpeed(int targetSpeed) {
    if (currentSpeed < targetSpeed) {
        currentSpeed += 5;
        if (currentSpeed > targetSpeed) currentSpeed = targetSpeed;
    } else if (currentSpeed > targetSpeed) {
        currentSpeed -= 5;
        if (currentSpeed < targetSpeed) currentSpeed = targetSpeed;
    }
    analogWrite(FAN_PWM, currentSpeed);
}

// ---------- Calculate Flow Rates ----------
void calculateFlowRates() {
    unsigned long now = millis();
    if (now - lastFlowCalc < flowInterval) return;

    // Disable interrupts briefly to read and reset pulse counters safely
    noInterrupts();
    unsigned int pulses1 = flowPulses1;
    unsigned int pulses2 = flowPulses2;
    flowPulses1 = 0;
    flowPulses2 = 0;
    interrupts();

    // Convert pulses to L/min:
    // litres = pulses / 552
    // L/min  = litres * (60000 / elapsed_ms)
    unsigned long elapsed = now - lastFlowCalc;
    float factor = 60000.0 / (pulsesPerLitre * (float)elapsed);
    flowRate1 = pulses1 * factor;
    flowRate2 = pulses2 * factor;

    lastFlowCalc = now;
}

// ---------- Serial Output (CSV) ----------
void printStatus(float temperature) {
    if (!Serial) return;

    if (lineCount % 20 == 0) {
        Serial.println("Temperature[degC],Fan_PWR[percnt],Flow1[L/min],Flow2[L/min]");
    }
    Serial.print(temperature, 2);
    Serial.print(",");
    Serial.print(map(currentSpeed, 0, 255, 0, 100));
    Serial.print(",");
    Serial.print(flowRate1, 2);
    Serial.print(",");
    Serial.println(flowRate2, 2);
    lineCount++;
}

// ---------- Main Loop ----------
void loop() {
    float temperature = readTemperature();
    int targetSpeed = calculateFanSpeed(temperature);

    updateFanSpeed(targetSpeed);
    calculateFlowRates();
    printStatus(temperature);

    delay(500);
}
