# TC400 Parameter List

Based on the documentation provided, here are all the parameters for the TC400 device:

## Control Parameters (Stellbefehle)

| Parameter # | Purpose | Data Type | Access | Default |
|-------------|---------|-----------|---------|---------|
| 001 | Heating (Heizung - 0=off, 1=on) | 0 | RW | 0 |
| 002 | Standby (Standby - 0=off, 1=on) | 0 | RW | 0 |
| 004 | RUTimeCtrl (Start-up time monitoring - 0=off, 1=on) | 0 | RW | 1 |
| 009 | ErrorAckn (Error acknowledgment - 1=acknowledge error) | 0 | W | - |
| 010 | PumpgStatn (Pump status - 0=off, 1=on and error acknowledgment) | 0 | RW | 0 |
| 012 | EnableVent (Enable venting - 0=no, 1=yes) | 0 | RW | 0 |
| 017 | CfgSpdSwPt (Configuration speed switching point - 0=point 1, 1=point 1&2) | 7 | RW | 0 |
| 019 | Cfg DO2 (Configuration output DO2 - various pump status options) | 7 | RW | 1 |
| 023 | MotorPump (Motor vacuum pump - 0=off, 1=on) | 0 | RW | 0 |
| 024 | Cfg DO1 (Configuration output DO1 - see P:019 functions) | 7 | RW | 0 |
| 025 | OpMode BKP (Operating mode backing pump - various modes) | 7 | RW | 0 |
| 026 | SpdSetMode (Speed control mode - 0=off, 1=on) | 7 | RW | 0 |
| 027 | GasMode (Gas mode - 0=heavy gases, 1=light gases, 2=Helium) | 7 | RW | 0 |
| 028 | Cfg Remote (Remote configuration - 0=standard, 4=relay inverted) | 7 | RW | 0 |
| 030 | VentMode (Venting mode - 0=delayed, 1=no venting, 2=direct) | 7 | RW | 0 |
| 035 | Cfg Acc A1 (Configuration accessory connection A1 - various functions) | 7 | RW | 0 |
| 036 | Cfg Acc B1 (Configuration accessory connection B1 - see P:035) | 7 | RW | 1 |
| 037 | Cfg Acc A2 (Configuration accessory connection A2 - see P:035) | 7 | RW | 3 |
| 038 | Cfg Acc B2 (Configuration accessory connection B2 - see P:035) | 7 | RW | 2 |
| 041 | Press1HVen (Enable HV sensor integrated - various enable modes) | 7 | RW | 2 |
| 045 | Cfg Rel R1 (Configuration relay 1 - see P:019 functions) | 7 | RW | 0 |
| 046 | Cfg Rel R2 (Configuration relay 2 - see P:019 functions) | 7 | RW | 1 |
| 047 | Cfg Rel R3 (Configuration relay 3 - see P:019 functions) | 7 | RW | 3 |
| 050 | SealingGas (Sealing gas - 0=off, 1=on) | 0 | RW | 0 |
| 055 | Cfg AO1 (Configuration output AO1 - various analog outputs) | 7 | RW | 0 |
| 057 | Cfg AI1 (Configuration input AI1 - 0=off, 1=speed control input) | 7 | RW | 1 |
| 060 | CtrlViaInt (Control via interface - various interface options) | 7 | RW | 1 |
| 061 | IntSelLckd (Interface selection locked - 0=off, 1=on) | 0 | RW | 0 |
| 062 | Cfg DI1 (Configuration input DI1 - various digital input functions) | 7 | RW | 1 |
| 063 | Cfg DI2 (Configuration input DI2 - see P:062 functions) | 7 | RW | 2 |
| 064 | Cfg DI3 (Configuration input DI3 - see P:062 functions) | 7 | RW | 3 |

## Status Query Parameters (Statusabfragen)

| Parameter # | Purpose | Data Type | Access |
|-------------|---------|-----------|---------|
| 300 | RemotePrio (Remote priority - 0=no, 1=yes) | 0 | R |
| 302 | SpdSwPtAtt (Speed switching point reached - 0=no, 1=yes) | 0 | R |
| 303 | Error code (Error code) | 4 | R |
| 304 | OvTempElec (Overtemperature electronics - 0=no, 1=yes) | 0 | R |
| 305 | OvTempPump (Overtemperature vacuum pump - 0=no, 1=yes) | 0 | R |
| 306 | SetSpdAtt (Target speed reached - 0=no, 1=yes) | 0 | R |
| 307 | PumpAccel (Vacuum pump accelerating - 0=no, 1=yes) | 0 | R |
| 308 | SetRotSpd (Target speed in Hz) | 1 | R |
| 309 | ActualSpd (Actual speed in Hz) | 1 | R |
| 310 | DrvCurrent (Drive current in A) | 2 | R |
| 311 | OpHrsPump (Operating hours vacuum pump in h) | 1 | R |
| 312 | Fw version (Software version drive electronics) | 4 | R |
| 313 | DrvVoltage (Drive voltage in V) | 2 | R |
| 314 | OpHrsElec (Operating hours drive electronics in h) | 1 | R |
| 315 | Nominal Spd (Nominal speed in Hz) | 1 | R |
| 316 | DrvPower (Drive power in W) | 1 | R |
| 319 | PumpCycles (Pump cycles) | 1 | R |
| 326 | TempElec (Electronics temperature in °C) | 1 | R |
| 330 | TempPmpBot (Pump bottom temperature in °C) | 1 | R |
| 336 | AccelDecel (Acceleration/deceleration in rpm/s) | 1 | R |
| 337 | SealGasFlw (Sealing gas flow in sccm) | 1 | R |
| 342 | TempBearng (Bearing temperature in °C) | 1 | R |
| 346 | TempMotor (Motor temperature in °C) | 1 | R |
| 349 | ElecName (Drive electronics designation) | 4 | R |
| 354 | HW Version (Hardware version drive electronics) | 4 | R |
| 360-369 | ErrHist1-10 (Error code history positions 1-10) | 4 | R |
| 397 | SetRotSpd (Target speed in 1/min) | 1 | R |
| 398 | ActualSpd (Actual speed in 1/min) | 1 | R |
| 399 | NominalSpd (Nominal speed in 1/min) | 1 | R |

## Setpoint Parameters (Sollwertvorgaben)

| Parameter # | Purpose | Data Type | Access | Unit | Default |
|-------------|---------|-----------|---------|------|---------|
| 700 | RUTimeSVal (Start-up time setpoint) | 1 | RW | min | 8 |
| 701 | SpdSwPt1 (Speed switching point 1) | 1 | RW | % | 80 |
| 707 | SpdSVal (Speed control setpoint) | 2 | RW | % | 65 |
| 708 | PwrSVal (Power consumption setpoint) | 7 | RW | % | 100 |
| 710 | Swoff BKP (Switch-off threshold backing pump in interval mode) | 1 | RW | W | 0 |
| 711 | SwOn BKP (Switch-on threshold backing pump in interval mode) | 1 | RW | W | 0 |
| 717 | StdbySVal (Speed setpoint in standby) | 2 | RW | % | 66.7 |
| 719 | SpdSwPt2 (Speed switching point 2) | 1 | RW | % | 20 |
| 720 | VentSpd (Venting speed for delayed venting) | 7 | RW | % | 50 |
| 721 | VentTime (Venting time for delayed venting) | 1 | RW | s | 3600 |
| 730 | PrsSwPt 1 (Pressure switching point 1) | 10 | RW | hPa | - |
| 732 | PrsSwPt 2 (Pressure switching point 2) | 10 | RW | hPa | - |
| 739 | PrsSn1Name (Pressure sensor 1 name) | 4 | R | - | - |
| 740 | Pressure 1 (Pressure value 1) | 10 | RW | hPa | - |
| 742 | PrsCorrPi 1 (Correction factor 1) | 2 | RW | - | - |
| 749 | PrsSn2Name (Pressure sensor 2 name) | 4 | R | - | - |
| 750 | Pressure 2 (Pressure value 2) | 10 | RW | hPa | - |
| 752 | PrsCorrPi 2 (Correction factor 2) | 2 | RW | - | - |
| 777 | NomSpdConf (Nominal speed confirmation) | 1 | RW | Hz | 0 |
| 791 | SlgWrnThrs (Sealing gas flow warning threshold) | 1 | RW | sccm | 15 |
| 797 | RS485Adr (RS-485 interface address) | 1 | RW | - | 1 |

## Additional Controller Parameters (Zusätzliche Parameter für das Steuergerät)

| Parameter # | Purpose | Data Type | Access | Unit |
|-------------|---------|-----------|---------|------|
| 340 | Pressure (Pressure actual value ActiveLine) | 7 | R | hPa |
| 350 | Ctr Name (Controller type) | 4 | R | - |
| 351 | Ctr Software (Controller software version) | 4 | R | - |
| 738 | Gaugetype (Pressure measurement tube type) | 4 | RW | - |
| 794 | Param set (Parameter set - 0=basic, 1=extended) | 7 | RW | - |
| 795 | Servicelin (Insert service line) | 7 | RW | - |

## Data Type Legend
- **0**: Boolean (0/1)
- **1**: Integer
- **2**: Float/Real number
- **4**: String/Text
- **7**: Configuration/Enumerated value
- **10**: Scientific notation/Pressure value

## Access Types
- **R**: Read-only parameter
- **RW**: Read/write parameter
- **W**: Write-only parameter

## Notes
- TC400 is a turbo pump controller with extensive configuration options
- Parameters support various pump operating modes and external component control
- Pressure-related parameters use hPa as the unit
- Many configuration parameters reference other parameter functions (e.g., P:019, P:035)
- Extended parameter set (P:794=1) provides additional controller-specific functions