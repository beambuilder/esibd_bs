#include <OneWire.h>
#include <DallasTemperature.h>

#define ONE_WIRE_BUS 15   // DS18B20 an MISO (Pro Micro = Pin 14)
#define FAN_PWM      9   // Lüfter‑MOSFET an Pin 10 (OC1B)

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

const float minTemp = 15.0;
const float maxTemp = 20.0;
int currentSpeed    = 0;
unsigned int lineCount = 0;

void setup() {
    pinMode(FAN_PWM, OUTPUT);

    /* ----------  WICHTIGER TEIL  ---------- */
    Serial.begin(9600);
    /* Warten, bis der USB‑CDC‑Port enumeriert ist.
       –  Bei direkter Verbindung zum PC genügt < 1 s.
       –  Timeout sorgt dafür, dass das Programm auch ohne offenen
          Terminal weiterläuft (z. B. nach Stromausfall im Stand‑Alone‑Betrieb). */
    unsigned long t0 = millis();
    while (!Serial && millis() - t0 < 3000) { }   // max. 3 s warten
    /* -------------------------------------- */

    sensors.begin();
}

void loop() {
    sensors.requestTemperatures();
    float temperature = sensors.getTempCByIndex(0);

    int targetSpeed;
    if (temperature <= minTemp)         targetSpeed = 0;
    else if (temperature >= maxTemp)    targetSpeed = 255;
    else targetSpeed = map(temperature, minTemp, maxTemp, 0, 255);

    if (currentSpeed < targetSpeed) {
        currentSpeed += 5;
        if (currentSpeed > targetSpeed) currentSpeed = targetSpeed;
    } else if (currentSpeed > targetSpeed) {
        currentSpeed -= 5;
        if (currentSpeed < targetSpeed) currentSpeed = targetSpeed;
    }

    analogWrite(FAN_PWM, currentSpeed);

    if (Serial) {
        if (lineCount % 20 == 0) {
            Serial.println("Temperature[degC],Fan_PWR[percnt]");
        }
        Serial.print(temperature, 2);
        Serial.print(",");
        Serial.println(map(currentSpeed, 0, 255, 0, 100));
        lineCount++;
    }

    delay(500);
}
