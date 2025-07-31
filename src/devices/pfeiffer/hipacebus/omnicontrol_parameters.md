# OmniControl Parameter List

Based on the documentation provided, here are all the parameters for the OmniControl device:

## Control Parameters (Stellbefehle)

| Parameter # | Purpose | Data Type | Access |
|-------------|---------|-----------|---------|
| 040 | DeGas-Vorgang (DeGas cleaning process for measurement) | 6 | RW |
| 041 | BA/CC on/off (BA/CC on/off - switches cold cathode on/off) | 7 | RW |
| 070 | Dir DigOut (Digital output - reset/set/no change) | 1 | RW |
| 071 | Dir RelOut (Relay output - reset/set/no change) | 1 | RW |

## Status Query Parameters (Statusabfragen)

| Parameter # | Purpose | Data Type | Access |
|-------------|---------|-----------|---------|
| 303 | Error code (Fehlercode) | 4 | R |
| 312 | FW version (Firmware Version) | 4 | R |
| 349 | ElecName (Device designation) | 4 | R |
| 354 | HW Version (Hardware Version) | 4 | R |
| 355 | Serial No (Serial number) | 11 | R |
| 386 | Dir DigInp (Digital inputs - reset/set/no change) | 1 | R |
| 387 | Dir AlgInp (Analog input) | 2 | R |
| 388 | Order Code (Order number) | 11 | R |

## Setpoint Parameters (Sollwertvorgaben)

| Parameter # | Purpose | Data Type | Access |
|-------------|---------|-----------|---------|
| 727 | Dir AlgOut (Analog output) | 2 | RW |
| 740 | Pressure (Pressure value - W corresponds to 0 = zero on, W corresponds to not 0 = zero off) | 10 | RW |
| 742 | UserGasCor (Correction factor) | 2 | RW |
| 797 | BaseAdr (Interface address) | 1 | RW |

## Data Type Legend
- **1**: Integer
- **2**: Float/Real number
- **4**: String/Text
- **6**: Enumerated value
- **7**: Configuration value
- **10**: Scientific notation/Pressure value
- **11**: Long string/Serial number

## Access Types
- **R**: Read-only parameter
- **RW**: Read/write parameter

## Notes
- Parameter 040 (DeGas): Cleaning process for measurement
- Parameter 041 (BA/CC): Controls Bayard-Alpert/Cold Cathode gauge on/off
- Parameter 070/071: Digital and relay output controls
- Parameter 740: Pressure reading with zero function control
- Parameter 797: RS-485 interface address configuration