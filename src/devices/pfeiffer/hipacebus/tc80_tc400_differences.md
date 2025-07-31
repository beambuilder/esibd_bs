# TC80 vs TC400 Parameter Differences

This document outlines all the differences between TC80 and TC400 parameters, including different default values, missing parameters, and additional parameters.

## Parameters with Different Default Values

| Parameter # | Parameter Name | TC400 Default | TC80 Default | Description |
|-------------|----------------|---------------|--------------|-------------|
| 023 | MotorPump | 0 (off) | 1 (on) | Motor pump control - TC80 starts with pump enabled |
| 030 | VentMode | 0 (delayed venting) | 2 (direct venting) | TC80 uses direct venting by default |

## Parameters Present in TC400 but Missing in TC80

| Parameter # | Parameter Name | Purpose | TC400 Default |
|-------------|----------------|---------|---------------|
| 028 | Cfg Remote | Remote configuration (0=standard, 4=relay inverted) | 0 |
| 037 | Cfg Acc A2 | Configuration accessory connection A2 | 3 |
| 038 | Cfg Acc B2 | Configuration accessory connection B2 | 2 |
| 045 | Cfg Rel R1 | Configuration relay 1 | 0 |
| 046 | Cfg Rel R2 | Configuration relay 2 | 1 |
| 047 | Cfg Rel R3 | Configuration relay 3 | 3 |
| 057 | Cfg AI1 | Configuration input AI1 (analog input) | 1 |
| 064 | Cfg DI3 | Configuration input DI3 (digital input) | 3 |
| 337 | SealGasFlw | Sealing gas flow in sccm | - |
| 342 | TempBearng | Bearing temperature in °C | - |
| 346 | TempMotor | Motor temperature in °C | - |
| 791 | SlgWrnThrs | Sealing gas flow warning threshold | 15 |

## Parameters Present in TC80 but Missing in TC400

| Parameter # | Parameter Name | Purpose | TC80 Default | Unit |
|-------------|----------------|---------|--------------|------|
| 058 | TmpMgtMode | Temperature management configuration | 0 | - |
| 324 | TmpPwrStg | Power stage temperature | - | °C |
| 384 | TempRotor | Rotor temperature | - | °C |
| 396 | AddID | Pump identification | - | - |
| 726 | mxPwrOutTm | Maximum time for output voltage in power backup | 10 | s |
| 728 | fanOnTemp | Fan switch-on temperature in temp-controlled mode | 45 | °C |
| 733 | PwrOutVolt | Output voltage in power backup mode | 23.00 | V |
| 734 | PwrOutThrs | Power threshold for voltage output | 20 | W |

## Functional Differences

### TC80 Unique Features
1. **Power Backup Functionality**: TC80 includes specialized power backup parameters (726, 733, 734) for maintaining operation during power interruptions
2. **Enhanced Temperature Management**: Parameter 058 provides temperature management options not available in TC400
3. **Simplified Accessory Configuration**: TC80 has only 4 accessory connections (A1, B1, C1, D1) vs TC400's 6 connections (A1, B1, A2, B2, R1, R2, R3)
4. **Additional Temperature Monitoring**: TC80 monitors power stage and rotor temperatures separately

### TC400 Unique Features
1. **More Relay Controls**: TC400 has 3 configurable relays (R1, R2, R3) vs TC80's none
2. **Analog Input Configuration**: TC400 includes analog input configuration (AI1) missing in TC80
3. **Remote Configuration**: TC400 has remote configuration options not present in TC80
4. **Sealing Gas Monitoring**: TC400 includes sealing gas flow monitoring and warning thresholds
5. **Additional Digital Input**: TC400 has 3 digital inputs vs TC80's 2
6. **More Temperature Sensors**: TC400 monitors bearing and motor temperatures separately

### Configuration Range Differences

#### TC80 Accessory Connection Options (P:035, P:036, P:068, P:069)
- Range: 0-13 functions
- Missing functions 9, 10, 11 compared to TC400
- Function 13 = "ohne Funktion" (no function) - TC80 specific

#### TC400 Accessory Connection Options (P:035-038)
- Range: 0-14 functions
- Includes TMS heating/cooling (9, 10)
- Function 14 = "Heizung (Unterteiltemperatur geregelt)" - TC400 specific

## Summary

**TC80** appears to be a **simplified, specialized version** of TC400 with:
- **Enhanced power backup capabilities**
- **Simplified I/O configuration** (fewer relays, inputs, accessories)
- **Direct venting by default** (faster response)
- **Motor enabled by default** (ready-to-run configuration)

**TC400** is the **full-featured version** with:
- **More comprehensive I/O options**
- **Advanced sealing gas monitoring**
- **More granular temperature monitoring**
- **Flexible remote configuration**
- **More conservative default settings** (delayed venting, motor off)

The TC80 seems optimized for applications requiring reliable operation with minimal configuration, while TC400 provides maximum flexibility and monitoring capabilities for complex systems.