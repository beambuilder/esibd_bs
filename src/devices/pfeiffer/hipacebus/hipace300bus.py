"""
HiPace300Bus device controller.

This module provides the HiPace300Bus class for communicating with Pfeiffer
HiPace300Bus turbo molecular pumps via serial communication using the 
telegram frame protocol.
"""
# TODO: Configure operation modes (see Manual)

from typing import Optional
import logging
import threading

from ..base_device import PfeifferBaseDevice


class HiPace300Bus(PfeifferBaseDevice):
    """
    Pfeiffer HiPace300Bus Turbo Molecular Pump Class.
    
    This class inherits from PfeifferBaseDevice and provides specific functionality
    for controlling HiPace300Bus turbo molecular pumps, including pump control,
    speed monitoring, temperature readings, and status queries.
    
    Example:
        pump = HiPace300Bus("hipace300_01", port="COM7", device_address=1)
        pump.connect()
        pump.start_housekeeping()
        pump.enable_pump()
        pump.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        device_address: int = 1,  # OmniControl base address
        tc400_address: int = 2,  # TC400 address (independent)
        gauge1_address: Optional[int] = None,  # Optional gauge address
        baudrate: int = 9600,
        timeout: float = 2.0,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 1.0,
        **kwargs,
    ):
        """
        Initialize HiPace300Bus device.

        Args:
            device_id: Unique identifier for the device
            port: Serial port (e.g., 'COM7' on Windows, '/dev/ttyUSB0' on Linux)
            device_address: OmniControl device address (1-255, default: 1)
            tc400_address: TC400 device address (1-255, default: 2)
            gauge1_address: Optional gauge device address (1-255)
            baudrate: Communication speed (default: 9600)
            timeout: Serial communication timeout in seconds (default: 2.0)
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 1.0)
            **kwargs: Additional connection parameters
        """
        super().__init__(
            device_id=device_id,
            port=port,
            device_address=device_address,  # This becomes the OmniControl address
            baudrate=baudrate,
            timeout=timeout,
            logger=logger,
            hk_thread=hk_thread,
            thread_lock=thread_lock,
            hk_interval=hk_interval,
            **kwargs
        )
        
        # Store device addresses
        self.omnicontrol_address = device_address
        self.tc400_address = tc400_address
        self.gauge1_address = gauge1_address
        
        # Create channel mapping
        self.channel_addresses = {
            'omnicontrol': self.omnicontrol_address,
            'tc400': self.tc400_address,
        }
        
        # Add gauge if provided
        if gauge1_address is not None:
            self.channel_addresses['gauge1'] = gauge1_address

        # Simulated device state (test mode). The same setters the ctrl API
        # calls flip these, so simulation reacts to buttons like hardware
        # does. Pump runs and the gauge measures by default, so a freshly
        # simulated device produces data immediately.
        self._sim_state = {
            "pump_on": True,
            "motor_pump": True,
            "standby": False,
            "vent": False,
            "heating": False,
            "gauge_on": True,
            # Accessory-port configs (params 35-38) — defaults mirror the
            # lab HiPace300s (A1 = heating band, rest = always "0").
            "acc_a1": 2,
            "acc_b1": 6,
            "acc_a2": 6,
            "acc_b2": 6,
            # Error history [P:360-362], newest first — blank = no entry.
            "err_hist": ["", "", ""],
        }

        # Latest error history (ErrHist1-3), cached by hk_monitor() and
        # served via extra_status() — strings never enter the telemetry
        # sink (numeric-only).
        self._error_history: list = []

    #: (channel, param) -> (_sim_state key, encoding) for parameters that are
    #: simulated statefully; writes update the state, queries encode it back.
    _SIM_PARAMS = {
        ("tc400", 1): ("heating", "boolean_old"),
        ("tc400", 2): ("standby", "boolean_old"),
        ("tc400", 10): ("pump_on", "boolean_old"),
        ("tc400", 12): ("vent", "boolean_old"),
        ("tc400", 23): ("motor_pump", "boolean_old"),
        ("tc400", 35): ("acc_a1", "u_short_int"),
        ("tc400", 36): ("acc_b1", "u_short_int"),
        ("tc400", 37): ("acc_a2", "u_short_int"),
        ("tc400", 38): ("acc_b2", "u_short_int"),
        ("gauge1", 41): ("gauge_on", "u_short_int"),
    }

    def _sim_param_entry(self, channel, param_num: int):
        return (self._SIM_PARAMS.get((channel, param_num))
                if isinstance(channel, str) else None)

    # =============================================================================
    #     Channel-Specific Communication Helper
    # =============================================================================
    
    def _query_channel_parameter(self, channel, param_num: int) -> str:
        """
        Query a parameter from a specific device channel on the HiPace300Bus.
        
        Args:
            channel: Device channel identifier ('omnicontrol', 'tc400', 'gauge1') or address (int)
            param_num: Parameter number to query
            
        Returns:
            str: Raw response from device
            
        Raises:
            ValueError: If channel is invalid
            Exception: If device not connected or communication fails
        """
        # Resolve channel to device address
        if isinstance(channel, str):
            if channel not in self.channel_addresses:
                raise ValueError(f"Unknown channel '{channel}'. Available: {list(self.channel_addresses.keys())}")
            device_address = self.channel_addresses[channel]
        elif isinstance(channel, int):
            device_address = channel
        else:
            raise ValueError("Channel must be a string identifier or integer address")

        if self.test_mode:
            entry = self._sim_param_entry(channel, param_num)
            if entry is None:
                raise RuntimeError(
                    "_query_channel_parameter() called in test_mode — simulated "
                    "values come from hk_monitor()/_sim_channels()"
                )
            key, encoding = entry
            state = self._sim_state[key]
            if encoding == "boolean_old":
                return self.data_converter.bool_2_boolean_old(state)
            return self.data_converter.int_2_u_short_int(int(state))
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        try:
            with self.thread_lock:  # Thread-safe communication
                from ..pfeifferVacuumProtocol import query_data
                return query_data(self.serial_connection, device_address, param_num)
        except Exception as e:
            self.logger.error(f"Failed to query channel {channel} (addr: {device_address}) parameter {param_num}: {e}")
            raise

    def _set_channel_parameter(self, channel, param_num: int, value: str) -> None:
        """
        Set a parameter on a specific device channel on the HiPace300Bus.
        
        Args:
            channel: Device channel identifier ('omnicontrol', 'tc400', 'gauge1') or address (int)
            param_num: Parameter number to set
            value: Value to set
            
        Raises:
            ValueError: If channel is invalid
            Exception: If device not connected or communication fails
        """
        # Resolve channel to device address
        if isinstance(channel, str):
            if channel not in self.channel_addresses:
                raise ValueError(f"Unknown channel '{channel}'. Available: {list(self.channel_addresses.keys())}")
            device_address = self.channel_addresses[channel]
        elif isinstance(channel, int):
            device_address = channel
        else:
            raise ValueError("Channel must be a string identifier or integer address")

        if self.test_mode:
            entry = self._sim_param_entry(channel, param_num)
            if entry is not None:
                key, encoding = entry
                # boolean params stay bools; u_short_int params (accessory
                # configs) keep their integer value.
                self._sim_state[key] = (bool(int(value))
                                        if encoding == "boolean_old"
                                        else int(value))
            self.log_event("info", f"set {channel} param {param_num} = {value} (simulated)")
            return
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        try:
            with self.thread_lock:  # Thread-safe communication
                from ..pfeifferVacuumProtocol import write_command
                write_command(self.serial_connection, device_address, param_num, value)
        except Exception as e:
            self.logger.error(f"Failed to set channel {channel} (addr: {device_address}) parameter {param_num}: {e}")
            raise

    # =============================================================================
    #     OmniControl Methods (Base Device)
    # =============================================================================

    def set_deGas(self, enabled: bool) -> None:
        """Set Gauge Degas. """
        value = self.data_converter.bool_2_boolean_new(enabled)
        self._set_channel_parameter('gauge1', 40, value)

    def get_deGas(self) -> bool:
        """Get pump standby mode status."""
        response = self._query_channel_parameter('gauge1', 40)
        return self.data_converter.boolean_new_2_bool(response)

    def set_SensOnOff(self, enabled: bool) -> None:
        """Set Gauge (Cold Cathode) On/Off. """
        value = self.data_converter.int_2_u_short_int(enabled)
        self._set_channel_parameter('gauge1', 41, value)

    def get_SensOnOff(self) -> bool:
        """Get Gauge (Cold Cathode) on/off state."""
        response = self._query_channel_parameter('gauge1', 41)
        return bool(self.data_converter.u_short_int_2_int(response))

    def get_omni_error_code(self) -> str:
        """Get error code from OmniControl."""
        response = self._query_channel_parameter('omnicontrol', 303)
        return self.data_converter.string_2_str(response)

    def get_omni_firmware_version(self) -> str:
        """Get firmware version from OmniControl."""
        response = self._query_channel_parameter('omnicontrol', 312)
        return self.data_converter.string_2_str(response)

    def get_omni_device_name(self) -> str:
        """Get device designation from OmniControl."""
        response = self._query_channel_parameter('omnicontrol', 349)
        return self.data_converter.string_2_str(response)

    def get_omni_hardware_version(self) -> str:
        """Get hardware version from OmniControl."""
        response = self._query_channel_parameter('omnicontrol', 354)
        return self.data_converter.string_2_str(response)

    def get_omni_serial_number(self) -> str:
        """Get serial number from OmniControl."""
        response = self._query_channel_parameter('omnicontrol', 355)
        return self.data_converter.string16_2_str(response)

    def get_gauge_pressure(self) -> float:
        """Get pressure value from OmniControl with Gauge (0.0 = sensor off)."""
        if self.test_mode:
            if not (self.gauge1_address and self._sim_state["gauge_on"]):
                return 0.0  # zero-mantissa telegram = sensor off, like hardware
            return round(10 ** (self.SIM_GAUGE_BASE_EXPONENT
                                + self._sim_uniform(-0.08, 0.08)), 12)
        response = self._query_channel_parameter('gauge1', 740)
        return self.data_converter.u_expo_new_2_float(response)

    def get_omni_rs485_address(self) -> int:
        """Get RS485 interface address from OmniControl."""
        response = self._query_channel_parameter('omnicontrol', 797)
        return self.data_converter.u_integer_2_int(response)

    def set_omni_rs485_address(self, address: int) -> None:
        """Set RS485 interface address on OmniControl."""
        if not (1 <= address <= 255):
            raise ValueError("RS485 address must be between 1-255")
        value = self.data_converter.int_2_u_integer(address)
        self._set_channel_parameter('omnicontrol', 797, value)

    # =============================================================================
    #     TC400 Pump Control Methods
    # =============================================================================

    def enable_heating(self) -> None:
        """Enable pump heating."""
        value = self.data_converter.bool_2_boolean_old(True)
        self._set_channel_parameter('tc400', 1, value)

    def disable_heating(self) -> None:
        """Disable pump heating."""
        value = self.data_converter.bool_2_boolean_old(False)
        self._set_channel_parameter('tc400', 1, value)

    def get_heating_enabled(self) -> bool:
        """Get pump heating enabled status."""
        response = self._query_channel_parameter('tc400', 1)
        return self.data_converter.boolean_old_2_bool(response)

    def set_standby(self, enabled: bool) -> None:
        """Set pump standby mode."""
        value = self.data_converter.bool_2_boolean_old(enabled)
        self._set_channel_parameter('tc400', 2, value)

    def get_standby(self) -> bool:
        """Get pump standby mode status."""
        response = self._query_channel_parameter('tc400', 2)
        return self.data_converter.boolean_old_2_bool(response)

    def acknowledge_error(self) -> None:
        """Acknowledge pump errors (ErrorAckn [P:009]) — required before a
        pump that tripped into an error state accepts a new start."""
        value = self.data_converter.bool_2_boolean_old(True)
        self._set_channel_parameter('tc400', 9, value)

    def get_error_history(self, slot: int) -> str:
        """Error history entry (ErrHist1-3 = [P:360-362], newest first).

        Args:
            slot: History slot 1-3.

        Returns:
            str: Error code like ``"Err021"`` or ``"Wrn007"``; blank when
            the slot is empty.
        """
        if slot not in (1, 2, 3):
            raise ValueError("Error-history slot must be 1, 2 or 3")
        if self.test_mode:
            return self._sim_state["err_hist"][slot - 1]
        response = self._query_channel_parameter('tc400', 359 + slot)
        return self.data_converter.string_2_str(response).strip()

    def enable_pumpStatn(self) -> None:
        """Enable/start the turbo pump Station."""
        value = self.data_converter.bool_2_boolean_old(True)
        self._set_channel_parameter('tc400', 10, value)

    def disable_pumpStatn(self) -> None:
        """Disable/stop the turbo pump Station."""
        value = self.data_converter.bool_2_boolean_old(False)
        self._set_channel_parameter('tc400', 10, value)

    def get_pumpStatn_enabled(self) -> bool:
        """Get pump station enabled status."""
        response = self._query_channel_parameter('tc400', 10)
        return self.data_converter.boolean_old_2_bool(response)

    def enable_vent(self) -> None:
        """Enable venting (EnableVent)."""
        value = self.data_converter.bool_2_boolean_old(True)
        self._set_channel_parameter('tc400', 12, value)

    def disable_vent(self) -> None:
        """Disable venting (EnableVent)."""
        value = self.data_converter.bool_2_boolean_old(False)
        self._set_channel_parameter('tc400', 12, value)

    def get_vent_enabled(self) -> bool:
        """Get venting enabled status (EnableVent)."""
        response = self._query_channel_parameter('tc400', 12)
        return self.data_converter.boolean_old_2_bool(response)

    def enable_motor_pump(self) -> None:
        """Enable motor pump (MotorPump)."""
        value = self.data_converter.bool_2_boolean_old(True)
        self._set_channel_parameter('tc400', 23, value)

    def disable_motor_pump(self) -> None:
        """Disable motor pump (MotorPump)."""
        value = self.data_converter.bool_2_boolean_old(False)
        self._set_channel_parameter('tc400', 23, value)

    def get_motor_pump_enabled(self) -> bool:
        """Get motor pump enabled status (MotorPump)."""
        response = self._query_channel_parameter('tc400', 23)
        return self.data_converter.boolean_old_2_bool(response)

    def enable_speed_set_mode(self) -> None:
        """Enable rotation speed setting mode (SpdSetMode)."""
        value = self.data_converter.int_2_u_short_int(1)
        self._set_channel_parameter('tc400', 26, value)

    def disable_speed_set_mode(self) -> None:
        """Disable rotation speed setting mode (SpdSetMode)."""
        value = self.data_converter.int_2_u_short_int(0)
        self._set_channel_parameter('tc400', 26, value)

    def get_speed_set_mode_enabled(self) -> bool:
        """Get rotation speed setting mode status (SpdSetMode)."""
        response = self._query_channel_parameter('tc400', 26)
        mode_value = self.data_converter.u_short_int_2_int(response)
        return mode_value == 1

    def set_gas_mode(self, mode: int) -> None:
        """Set gas mode (GasMode). 0=heavy gases, 1=light gases, 2=helium."""
        if mode not in [0, 1, 2]:
            raise ValueError("Gas mode must be 0 (heavy gases), 1 (light gases), or 2 (helium)")
        value = self.data_converter.int_2_u_short_int(mode)
        self._set_channel_parameter('tc400', 27, value)

    def get_gas_mode(self) -> int:
        """Get gas mode (GasMode). 0=heavy gases, 1=light gases, 2=helium."""
        response = self._query_channel_parameter('tc400', 27)
        return self.data_converter.u_short_int_2_int(response)

    def set_vent_mode(self, mode: int) -> None:
        """Set venting mode (VentMode). 0=delayed venting, 1=no venting, 2=direct venting."""
        if mode not in [0, 1, 2]:
            raise ValueError("Vent mode must be 0 (delayed venting), 1 (no venting), or 2 (direct venting)")
        value = self.data_converter.int_2_u_short_int(mode)
        self._set_channel_parameter('tc400', 30, value)

    def get_vent_mode(self) -> int:
        """Get venting mode (VentMode). 0=delayed venting, 1=no venting, 2=direct venting."""
        response = self._query_channel_parameter('tc400', 30)
        return self.data_converter.u_short_int_2_int(response)

    def _validate_accessory_config(self, config: int) -> None:
        """Validate accessory configuration value."""
        valid_configs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14]
        if config not in valid_configs:
            raise ValueError(f"Configuration must be one of {valid_configs}")

    def _set_accessory_config(self, connection: str, param_num: int, config: int) -> None:
        """Set configuration for an accessory connection."""
        self._validate_accessory_config(config)
        value = self.data_converter.int_2_u_short_int(config)
        self._set_channel_parameter('tc400', param_num, value)

    def _get_accessory_config(self, param_num: int) -> int:
        """Get configuration for an accessory connection."""
        response = self._query_channel_parameter('tc400', param_num)
        return self.data_converter.u_short_int_2_int(response)

    def set_cfg_acc_a1(self, config: int) -> None:
        """
        Set configuration for accessory connection A1 (CfgAccA1).
        
        Args:
            config: Configuration value:
                0 = Fan, 1 = Venting valve, 2 = Heating, 3 = Backing pump,
                4 = Fan (temperature controlled), 5 = Sealing gas, 6 = Always "0",
                7 = Always "1", 8 = Power failure venting unit, 9 = TMS Heating,
                10 = TMS Cooling, 12 = Second venting valve, 13 = Sealing Gas monitoring,
                14 = Heating (bottom part temperature controlled)
        """
        self._set_accessory_config('A1', 35, config)

    def get_cfg_acc_a1(self) -> int:
        """Get configuration for accessory connection A1 (CfgAccA1)."""
        return self._get_accessory_config(35)

    def set_cfg_acc_b1(self, config: int) -> None:
        """
        Set configuration for accessory connection B1 (CfgAccB1).
        
        Args:
            config: Configuration value (same options as A1)
        """
        self._set_accessory_config('B1', 36, config)

    def get_cfg_acc_b1(self) -> int:
        """Get configuration for accessory connection B1 (CfgAccB1)."""
        return self._get_accessory_config(36)

    def set_cfg_acc_a2(self, config: int) -> None:
        """
        Set configuration for accessory connection A2 (CfgAccA2).
        
        Args:
            config: Configuration value (same options as A1)
        """
        self._set_accessory_config('A2', 37, config)

    def get_cfg_acc_a2(self) -> int:
        """Get configuration for accessory connection A2 (CfgAccA2)."""
        return self._get_accessory_config(37)

    def set_cfg_acc_b2(self, config: int) -> None:
        """
        Set configuration for accessory connection B2 (CfgAccB2).
        
        Args:
            config: Configuration value (same options as A1)
        """
        self._set_accessory_config('B2', 38, config)

    def get_cfg_acc_b2(self) -> int:
        """Get configuration for accessory connection B2 (CfgAccB2)."""
        return self._get_accessory_config(38)


    # =============================================================================
    #     TC400 Status Query Methods
    # =============================================================================

    def get_rotationspd_SwP_reached(self) -> str:
        """Rotationspeed switchpointed reached."""
        response = self._query_channel_parameter('tc400', 302)
        return self.data_converter.boolean_old_2_bool(response)

    def get_pump_error_code(self) -> str:
        """Get error code from TC400."""
        response = self._query_channel_parameter('tc400', 303)
        return self.data_converter.string_2_str(response)

    def is_overtemperature_electronics(self) -> bool:
        """Check if drive electronics is overtemperature (OvTempElec)."""
        response = self._query_channel_parameter('tc400', 304)
        return self.data_converter.boolean_old_2_bool(response)

    def is_overtemperature_pump(self) -> bool:
        """Check if vacuum pump is overtemperature (OvTempPump)."""
        response = self._query_channel_parameter('tc400', 305)
        return self.data_converter.boolean_old_2_bool(response)

    def is_target_speed_reached(self) -> bool:
        """Check if target speed is reached."""
        response = self._query_channel_parameter('tc400', 306)
        return self.data_converter.boolean_old_2_bool(response)

    def is_pump_accelerating(self) -> bool:
        """Check if pump is accelerating."""
        response = self._query_channel_parameter('tc400', 307)
        return self.data_converter.boolean_old_2_bool(response)

    def get_set_speed_hz(self) -> int:
        """Get set pump speed in Hz."""
        response = self._query_channel_parameter('tc400', 308)
        return self.data_converter.u_integer_2_int(response)

    def get_actual_speed_hz(self) -> int:
        """Get actual pump speed in Hz."""
        response = self._query_channel_parameter('tc400', 309)
        return self.data_converter.u_integer_2_int(response)

    def get_drive_current(self) -> float:
        """Get drive current in A."""
        response = self._query_channel_parameter('tc400', 310)
        return self.data_converter.u_real_2_float(response)
    
    def get_operating_hours_pump(self) -> int:
        """Get operating hours of pump in hours."""
        response = self._query_channel_parameter('tc400', 311)
        return self.data_converter.u_integer_2_int(response)

    def get_pump_firmware_version(self) -> str:
        """Get firmware version from TC400."""
        response = self._query_channel_parameter('tc400', 312)
        return self.data_converter.string_2_str(response)
    
    def get_drive_voltage(self) -> float:
        """Get drive voltage in V."""
        response = self._query_channel_parameter('tc400', 313)
        return self.data_converter.u_real_2_float(response)

    def get_operating_hours_electronics(self) -> int:
        """Get operating hours of drive electronics in hours (OpHrsElec)."""
        response = self._query_channel_parameter('tc400', 314)
        return self.data_converter.u_integer_2_int(response)
    
    def get_nominal_speed_hz(self) -> int:
        """Get nominal pump speed in Hz."""
        response = self._query_channel_parameter('tc400', 315)
        return self.data_converter.u_integer_2_int(response)
    
    def get_drive_power(self) -> int:
        """Get drive power in W."""
        response = self._query_channel_parameter('tc400', 316)
        return self.data_converter.u_integer_2_int(response)

    def get_pump_cycles(self) -> int:
        """Get number of pump cycles (PumpCycles)."""
        response = self._query_channel_parameter('tc400', 319)
        return self.data_converter.u_integer_2_int(response)
    
    def get_electronics_temperature(self) -> int:
        """Get electronics temperature in °C."""
        response = self._query_channel_parameter('tc400', 326)
        return self.data_converter.u_integer_2_int(response)
    
    def get_pump_bottom_temperature(self) -> int:
        """Get pump bottom temperature in °C."""
        response = self._query_channel_parameter('tc400', 330)
        return self.data_converter.u_integer_2_int(response)

    def get_acceleration_deceleration(self) -> int:
        """Get acceleration/deceleration in rpm/s (AccelDecel)."""
        response = self._query_channel_parameter('tc400', 336)
        return self.data_converter.u_integer_2_int(response)

    def get_seal_gas_flow(self) -> int:
        """Get seal gas flow in sccm (SealGasFlw)."""
        response = self._query_channel_parameter('tc400', 337)
        return self.data_converter.u_integer_2_int(response)
    
    def get_bearing_temperature(self) -> int:
        """Get bearing temperature in °C."""
        response = self._query_channel_parameter('tc400', 342)
        return self.data_converter.u_integer_2_int(response)

    def get_motor_temperature(self) -> int:
        """Get motor temperature in °C (TempMotor)."""
        response = self._query_channel_parameter('tc400', 346)
        return self.data_converter.u_integer_2_int(response)

    def get_pump_device_name(self) -> str:
        """Get device designation from TC400."""
        response = self._query_channel_parameter('tc400', 349)
        return self.data_converter.string_2_str(response)

    def get_pump_hardware_version(self) -> str:
        """Get hardware version of drive electronics (Antriebselektronik)."""
        response = self._query_channel_parameter('tc400', 354)
        return self.data_converter.string_2_str(response)

    def get_set_speed_rpm(self) -> int:
        """Get set pump speed in RPM."""
        response = self._query_channel_parameter('tc400', 397)
        return self.data_converter.u_integer_2_int(response)

    def get_actual_speed_rpm(self) -> int:
        """Get actual pump speed in RPM."""
        response = self._query_channel_parameter('tc400', 398)
        return self.data_converter.u_integer_2_int(response)
    
    def get_nominal_speed_rpm(self) -> int:
        """Get nominal pump speed in RPM."""
        response = self._query_channel_parameter('tc400', 399)
        return self.data_converter.u_integer_2_int(response)

    # =============================================================================
    #     TC400 Setpoint Methods
    # =============================================================================

    def set_ramp_up_time(self, time_minutes: int) -> None:
        """Set ramp-up time setpoint in minutes (RUTimeSVal)."""
        if not (1 <= time_minutes <= 120):
            raise ValueError("Ramp-up time must be between 1-120 minutes")
        value = self.data_converter.int_2_u_integer(time_minutes)
        self._set_channel_parameter('tc400', 700, value)

    def get_ramp_up_time(self) -> int:
        """Get ramp-up time setpoint in minutes (RUTimeSVal)."""
        response = self._query_channel_parameter('tc400', 700)
        return self.data_converter.u_integer_2_int(response)

    def set_speed_setpoint(self, speed_percent: float) -> None:
        """Set speed control setpoint in percent."""
        if not (20.0 <= speed_percent <= 100.0):
            raise ValueError("Speed setpoint must be between 20-100%")
        value = self.data_converter.float_2_u_real(speed_percent)
        self._set_channel_parameter('tc400', 707, value)

    def get_speed_setpoint(self) -> float:
        """Get speed control setpoint in percent."""
        response = self._query_channel_parameter('tc400', 707)
        return self.data_converter.u_real_2_float(response)

    def set_power_setpoint(self, power_percent: int) -> None:
        """Set power consumption setpoint in percent (PwrSVal)."""
        if not (10 <= power_percent <= 100):
            raise ValueError("Power setpoint must be between 10-100%")
        value = self.data_converter.int_2_u_short_int(power_percent)
        self._set_channel_parameter('tc400', 708, value)

    def get_power_setpoint(self) -> int:
        """Get power consumption setpoint in percent (PwrSVal)."""
        response = self._query_channel_parameter('tc400', 708)
        return self.data_converter.u_short_int_2_int(response)

    def set_rs485_address(self, address: int) -> None:
        """
        Set RS485 address for TC400 and update class parameter if successful.
        
        This function sets the new RS485 address on the TC400 device, then verifies
        the change by querying the device at the new address. If the device responds
        correctly, the class tc400_address parameter is updated.
        
        Args:
            address: New RS485 address (1-255)
            
        Raises:
            ValueError: If address is out of valid range
            Exception: If device communication fails or address change verification fails
        """
        if not (1 <= address <= 255):
            raise ValueError("RS485 address must be between 1-255")
        
        # Store original address for rollback if needed
        original_address = self.tc400_address
        
        try:
            # Set the new address on the device
            value = self.data_converter.int_2_u_integer(address)
            self._set_channel_parameter('tc400', 797, value)
            
            # Update the class address temporarily for verification
            self.tc400_address = address
            self.channel_addresses['tc400'] = address
            
            # Verify the address change by querying the device at the new address
            # Query parameter 797 (RS485 address) to confirm the change
            response = self._query_channel_parameter('tc400', 797)
            verified_address = self.data_converter.u_integer_2_int(response)
            
            if verified_address == address:
                # Address change successful, keep the new address
                self.logger.info(f"Successfully changed TC400 RS485 address from {original_address} to {address}")
            else:
                # Address verification failed, rollback
                self.tc400_address = original_address
                self.channel_addresses['tc400'] = original_address
                raise Exception(f"Address verification failed. Expected {address}, got {verified_address}")
                
        except Exception as e:
            # Rollback address change on any error
            self.tc400_address = original_address
            self.channel_addresses['tc400'] = original_address
            self.logger.error(f"Failed to change TC400 RS485 address to {address}: {e}")
            raise Exception(f"Failed to set RS485 address to {address}: {e}")

    def get_rs485_address(self) -> int:
        """Get RS485 address from TC400."""
        response = self._query_channel_parameter('tc400', 797)
        return self.data_converter.u_integer_2_int(response)

    # =============================================================================
    #     Convenience Methods
    # =============================================================================

    def get_pump_status(self) -> dict:
        """
        Get comprehensive pump status information.
        
        Returns:
            dict: Dictionary containing pump status parameters
        """
        status = {}
        try:
            status['actual_speed_hz'] = self.get_actual_speed_hz()
            status['actual_speed_rpm'] = self.get_actual_speed_rpm()
            status['set_speed_hz'] = self.get_set_speed_hz()
            status['drive_current'] = self.get_drive_current()
            status['drive_voltage'] = self.get_drive_voltage()
            status['drive_power'] = self.get_drive_power()
            status['electronics_temp'] = self.get_electronics_temperature()
            status['pump_bottom_temp'] = self.get_pump_bottom_temperature()
            status['bearing_temp'] = self.get_bearing_temperature()
            status['target_speed_reached'] = self.is_target_speed_reached()
            status['pump_accelerating'] = self.is_pump_accelerating()
            status['operating_hours'] = self.get_operating_hours_pump()
        except Exception as e:
            self.logger.error(f"Failed to get pump status: {e}")
            status['error'] = str(e)
        return status

    def get_system_info(self) -> dict:
        """
        Get comprehensive system information from both devices.
        
        Returns:
            dict: Dictionary containing system information
        """
        info = {}
        try:
            # OmniControl info
            info['omni_device_name'] = self.get_omni_device_name()
            info['omni_serial_number'] = self.get_omni_serial_number()
            info['omni_firmware_version'] = self.get_omni_firmware_version()
            info['omni_hardware_version'] = self.get_omni_hardware_version()
            info['omni_rs485_address'] = self.get_omni_rs485_address()
            info['omni_error_code'] = self.get_omni_error_code()
            
            # TC400 info
            info['pump_device_name'] = self.get_pump_device_name()
            info['pump_firmware_version'] = self.get_pump_firmware_version()
            info['pump_rs485_address'] = self.get_rs485_address()
            info['pump_error_code'] = self.get_pump_error_code()
            
            # Current readings
            if self.gauge1_address:
                info['pressure'] = self.get_gauge_pressure()
        except Exception as e:
            self.logger.error(f"Failed to get system info: {e}")
            info['error'] = str(e)
        return info

    # =============================================================================
    #     Housekeeping Override
    # =============================================================================

    #: Housekeeping channel table: (channel, unit, fmt, reader-method name).
    HK_CHANNELS = (
        ("Pump_Station_Enabled", "", "", "get_pumpStatn_enabled"),
        ("Standby_Mode", "", "", "get_standby"),
        ("Motor_Pump_Enabled", "", "", "get_motor_pump_enabled"),
        ("Vent_Enabled", "", "", "get_vent_enabled"),
        ("Speed_Actual_Hz", "Hz", "", "get_actual_speed_hz"),
        ("Speed_Actual_RPM", "rpm", "", "get_actual_speed_rpm"),
        ("Speed_Set_Hz", "Hz", "", "get_set_speed_hz"),
        ("Target_Speed_Reached", "", "", "is_target_speed_reached"),
        ("Pump_Accelerating", "", "", "is_pump_accelerating"),
        ("Drive_Current", "A", ".2f", "get_drive_current"),
        ("Drive_Voltage", "V", ".1f", "get_drive_voltage"),
        ("Drive_Power", "W", "", "get_drive_power"),
        ("Temp_Electronics", "degC", "", "get_electronics_temperature"),
        ("Temp_Pump_Bottom", "degC", "", "get_pump_bottom_temperature"),
        ("Temp_Bearing", "degC", "", "get_bearing_temperature"),
        ("Temp_Motor", "degC", "", "get_motor_temperature"),
        ("Overtemp_Electronics", "", "", "is_overtemperature_electronics"),
        ("Overtemp_Pump", "", "", "is_overtemperature_pump"),
        ("Seal_Gas_Flow", "sccm", "", "get_seal_gas_flow"),
        ("Operating_Hours_Pump", "h", "", "get_operating_hours_pump"),
        ("Operating_Hours_Electronics", "h", "", "get_operating_hours_electronics"),
        ("Heating_Enabled", "", "", "get_heating_enabled"),
        # Accessory-port configs (params 35-38): readback drives the
        # dashboard dropdowns; a poked hk cycle right after a set is the
        # get-verify the user required. Appended last — hk aborts at the
        # first failing channel.
        ("Cfg_Acc_A1", "", "", "get_cfg_acc_a1"),
        ("Cfg_Acc_B1", "", "", "get_cfg_acc_b1"),
        ("Cfg_Acc_A2", "", "", "get_cfg_acc_a2"),
        ("Cfg_Acc_B2", "", "", "get_cfg_acc_b2"),
    )

    #: Nominal rotation speed used by the simulator (HiPace300: 1000 Hz).
    SIM_NOMINAL_SPEED_HZ = 1000
    #: Decade of the simulated OmniControl gauge pressure (stable base +
    #: small jitter, so the plotted line looks like a real measurement).
    SIM_GAUGE_BASE_EXPONENT = -8.3

    def _sim_channels(self) -> dict:
        """Plausible turbo-pump values for test mode (same channels as
        HK_CHANNELS), derived from ``_sim_state`` so start/stop/heating
        toggles show up in the data like they would on hardware."""
        running = self._sim_state["pump_on"]
        speed_hz = (round(self._sim_uniform(
            self.SIM_NOMINAL_SPEED_HZ * 0.998, self.SIM_NOMINAL_SPEED_HZ, 0))
            if running else 0)
        return {
            "Pump_Station_Enabled": running,
            "Standby_Mode": self._sim_state["standby"],
            "Motor_Pump_Enabled": self._sim_state["motor_pump"],
            "Vent_Enabled": self._sim_state["vent"],
            "Speed_Actual_Hz": speed_hz,
            "Speed_Actual_RPM": speed_hz * 60,
            "Speed_Set_Hz": self.SIM_NOMINAL_SPEED_HZ,
            "Target_Speed_Reached": running,
            "Pump_Accelerating": False,
            "Drive_Current": self._sim_uniform(0.5, 0.9) if running else 0.0,
            "Drive_Voltage": self._sim_uniform(47.0, 49.0, 1),
            "Drive_Power": round(self._sim_uniform(20, 40, 0)) if running else 0,
            "Temp_Electronics": round(self._sim_uniform(35, 45, 0) if running
                                      else self._sim_uniform(24, 28, 0)),
            "Temp_Pump_Bottom": round(self._sim_uniform(30, 40, 0) if running
                                      else self._sim_uniform(23, 27, 0)),
            "Temp_Bearing": round(self._sim_uniform(30, 36, 0) if running
                                  else self._sim_uniform(23, 27, 0)),
            "Temp_Motor": round(self._sim_uniform(35, 42, 0) if running
                                else self._sim_uniform(23, 27, 0)),
            "Overtemp_Electronics": False,
            "Overtemp_Pump": False,
            "Seal_Gas_Flow": 0,
            "Operating_Hours_Pump": 20000,
            "Operating_Hours_Electronics": 20000,
            "Heating_Enabled": self._sim_state["heating"],
            "Cfg_Acc_A1": self._sim_state["acc_a1"],
            "Cfg_Acc_B1": self._sim_state["acc_b1"],
            "Cfg_Acc_A2": self._sim_state["acc_a2"],
            "Cfg_Acc_B2": self._sim_state["acc_b2"],
        }

    def hk_monitor(self):
        """
        One housekeeping cycle: report critical pump channels from both
        OmniControl and TC400 (simulated wholesale in test mode), plus the
        OmniControl gauge when one is configured.
        """
        try:
            if self.test_mode:
                sim = self._sim_channels()
                for channel, unit, fmt, _reader in self.HK_CHANNELS:
                    self.log_sample(channel, sim[channel], unit, fmt=fmt)
            else:
                for channel, unit, fmt, reader in self.HK_CHANNELS:
                    self.log_sample(channel, getattr(self, reader)(), unit, fmt=fmt)
        except Exception as e:
            self.log_event("error", f"housekeeping read failed: {e}")

        # OmniControl gauge: separate guard so a mute gauge cannot abort the
        # pump channels (and vice versa — different RS-485 addresses).
        # Hardware quirk: a deactivated gauge can return its last measured
        # value, frozen, instead of a zero-mantissa telegram — so gate the
        # pressure read/log on the reported on/off state (same rule as
        # TPG366), not on value==0.0. 0.0 (never measured since power-up)
        # is still skipped, it is never a real measurement either. An
        # over-ranged gauge (cold cathode at atmosphere) answers the
        # all-nines u_expo_new sentinel (9.999e+79 hPa) in valid frames —
        # skipped the same way (found 2026-07-06, Collision_Cell).
        if self.gauge1_address:
            try:
                on = self.get_SensOnOff()
                self.log_sample("Gauge_Sensor_On", 1.0 if on else 0.0)
                if on:
                    pressure = self.get_gauge_pressure()
                    if pressure != 0.0 and not self.data_converter.is_pressure_sentinel(pressure):
                        self.log_sample("Gauge_Pressure", pressure, "hPa", fmt=".2e")
            except Exception as e:
                self.log_event("warning", f"gauge read failed: {e}")

        # Error history [P:360-362]: strings, so they bypass the (numeric)
        # sink — cached for get_status()/the dashboard card instead. Own
        # guard: a failed history read must not abort anything else.
        try:
            self._error_history = [self.get_error_history(n) for n in (1, 2, 3)]
        except Exception as e:
            self.log_event("warning", f"error-history read failed: {e}")

    def extra_status(self) -> dict:
        status = super().extra_status()
        status["error_history"] = self._error_history
        return status
