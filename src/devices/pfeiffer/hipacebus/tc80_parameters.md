# TC80 Parameter List

Based on the documentation provided, here are all the parameters for the TC80 device:

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
| 023 | MotorPump (Motor pump - 0=off, 1=on) | 0 | RW | 1 |
| 024 | Cfg DO1 (Configuration output DO1 - see P:019 functions) | 7 | RW | 0 |
| 025 | OpMode BKP (Operating mode backing pump - various modes) | 7 | RW | 0 |
| 026 | SpdSetMode (Speed control mode - 0=off, 1=on) | 7 | RW | 0 |
| 027 | GasMode (Gas mode - 0=heavy gases, 1=light gases, 2=Helium) | 7 | RW | 0 |
| 030 | VentMode (Venting mode - 0=delayed, 1=no venting, 2=direct) | 7 | RW | 2 |
| 035 | Cfg Acc A1 (Configuration accessory connection A1 - various functions) | 7 | RW | 0 |
| 036 | Cfg Acc B1 (Configuration accessory connection B1 - see P:035) | 7 | RW | 1 |
| 041 | Press1HVen (Enable HV sensor integrated - various enable modes) | 7 | RW | 2 |
| 050 | SealingGas (Sealing gas - 0=off, 1=on) | 0 | RW | 0 |
| 055 | Cfg AO1 (Configuration output AO1 - various analog outputs) | 7 | RW | 0 |
| 058 | TmpMgtMode (Temperature management configuration - various temp limits) | 7 | RW | 0 |
| 060 | CtrlViaInt (Control via interface - various interface options) | 7 | RW | 1 |
| 061 | IntSelLckd (Interface selection locked - 0=off, 1=on) | 0 | RW | 0 |
| 062 | Cfg DI1 (Configuration input DI1 - various digital input functions) | 7 | RW | 1 |
| 063 | Cfg DI2 (Configuration input DI2 - see P:062 functions) | 7 | RW | 2 |
| 068 | Cfg Acc C1 (Configuration accessory connection C1 - see P:035) | 7 | RW | 0 |
| 069 | Cfg Acc D1 (Configuration accessory connection D1 - see P:035) | 7 | RW | 0 |

## Status Query Parameters (Statusabfragen)

| Parameter # | Purpose | Data Type | Access | Unit |
|-------------|---------|-----------|---------|------|
| 300 | RemotePrio (Remote priority - 0=no, 1=yes) | 0 | R | - |
| 302 | SpdSwPtAtt (Speed switching point reached - 0=no, 1=yes) | 0 | R | - |
| 303 | Error code (Error code) | 4 | R | - |
| 304 | OvTempElec (Overtemperature electronics - 0=no, 1=yes) | 0 | R | - |
| 305 | OvTempPump (Overtemperature pump - 0=no, 1=yes) | 0 | R | - |
| 306 | SetSpdAtt (Target speed reached - 0=no, 1=yes) | 0 | R | - |
| 307 | PumpAccel (Pump accelerating - 0=no, 1=yes) | 0 | R | - |
| 308 | SetRotSpd (Target speed in Hz) | 1 | R | Hz |
| 309 | ActualSpd (Actual speed in Hz) | 1 | R | Hz |
| 310 | DrvCurrent (Drive current in A) | 2 | R | A |
| 311 | OpHrsPump (Operating hours pump in h) | 1 | R | h |
| 312 | Fw version (Software version drive electronics) | 4 | R | - |
| 313 | DrvVoltage (Drive voltage in V) | 2 | R | V |
| 314 | OpHrsElec (Operating hours drive electronics in h) | 1 | R | h |
| 315 | Nominal Spd (Nominal speed in Hz) | 1 | R | Hz |
| 316 | DrvPower (Drive power in W) | 1 | R | W |
| 319 | PumpCycles (Pump cycles) | 1 | R | - |
| 324 | TmpPwrStg (Power stage temperature in °C) | 1 | R | °C |
| 326 | TempElec (Electronics temperature in °C) | 1 | R | °C |
| 330 | TempPmpBot (Pump bottom temperature in °C) | 1 | R | °C |
| 336 | AccelDecel (Acceleration/deceleration in rpm/s) | 1 | R | rpm/s |
| 349 | ElecName (Drive electronics designation) | 4 | R | - |
| 354 | HW Version (Hardware version drive electronics) | 4 | R | - |
| 355 | Serial No (Serial number) | 11 | R | - |
| 360-369 | ErrHist1-10 (Error code history positions 1-10) | 4 | R | - |
| 384 | TempRotor (Rotor temperature in °C) | 1 | R | °C |
| 388 | Order Code (Order number) | 11 | R | - |
| 396 | AddID (Pump identification) | 1 | R | - |
| 397 | SetRotSpd (Target speed in 1/min) | 1 | R | rpm |
| 398 | ActualSpd (Actual speed in 1/min) | 1 | R | rpm |
| 399 | NominalSpd (Nominal speed in 1/min) | 1 | R | rpm |

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
| 726 | mxPwrOutTm (Maximum time for output voltage in power backup mode) | 1 | RW | s | 10 |
| 728 | fanOnTemp (Fan switch-on temperature in temperature-controlled mode) | 1 | RW | °C | 45 |
| 730 | PrsSwPt 1 (Pressure switching point 1) | 10 | RW | hPa | 1000 |
| 732 | PrsSwPt 2 (Pressure switching point 2) | 10 | RW | hPa | 1000 |
| 733 | PwrOutVolt (Output voltage in power backup mode) | 2 | RW | V | 23.00 |
| 734 | PwrOutThrs (Power threshold for voltage output from P733) | 1 | RW | W | 20 |
| 739 | PrsSn1Name (Pressure sensor 1 name) | 4 | R | - | - |
| 740 | Pressure 1 (Pressure value 1) | 10 | RW | hPa | - |
| 742 | PrsCorrPi 1 (Correction factor 1) | 2 | RW | - | 0 |
| 749 | PrsSn2Name (Pressure sensor 2 name) | 4 | R | - | - |
| 750 | Pressure 2 (Pressure value 2) | 10 | RW | hPa | - |
| 752 | PrsCorrPi 2 (Correction factor 2) | 2 | RW | - | 0 |
| 777 | NomSpdConf (Nominal speed confirmation) | 1 | RW | Hz | 0 |
| 797 | RS485Adr (RS-485 interface address) | 1 | RW | - | 1 |

## Additional Controller Parameters (Zusätzliche Parameter für das Steuergerät)

| Parameter # | Purpose | Data Type | Access | Unit | Default |
|-------------|---------|-----------|---------|------|---------|
| 340 | Pressure (Pressure actual value ActiveLine) | 7 | R | hPa | - |
| 350 | Ctr Name (Controller type) | 4 | R | - | - |
| 351 | Ctr Software (Controller software version) | 4 | R | - | - |
| 738 | Gaugetype (Pressure measurement tube type) | 4 | RW | - | - |
| 794 | Param set (Parameter set - 0=basic, 1=extended) | 7 | RW | - | 0 |
| 795 | Servicelin (Insert service line) | 7 | RW | - | 795 |

## Data Type Legend
- **0**: Boolean (0/1)
- **1**: Integer
- **2**: Float/Real number
- **4**: String/Text
- **7**: Configuration/Enumerated value
- **10**: Scientific notation/Pressure value
- **11**: Long string/Serial number

## Access Types
- **R**: Read-only parameter
- **RW**: Read/write parameter
- **W**: Write-only parameter

## Notes
- TC80 is a turbo pump controller similar to TC400 but with some differences in configuration
- The TC80 has fewer accessory connections (A1, B1, C1, D1) compared to TC400
- Motor pump parameter (023) has default value 1 (on) unlike TC400
- VentMode default is 2 (direct venting) unlike TC400 which defaults to 0
- Temperature management includes special power backup functionality (P726, P733, P734)
- Extended parameter set (P:794=1) provides additional controller-specific functions
- Many configuration parameters reference functions from other parameters (e.g., P:019, P:035)