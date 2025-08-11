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
        """Get pressure value from OmniControl with Gauge."""
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

    def set_standby(self, enabled: bool) -> None:
        """Set pump standby mode."""
        value = self.data_converter.bool_2_boolean_old(enabled)
        self._set_channel_parameter('tc400', 2, value)

    def get_standby(self) -> bool:
        """Get pump standby mode status."""
        response = self._query_channel_parameter('tc400', 2)
        return self.data_converter.boolean_old_2_bool(response)

    def acknowledge_error(self) -> None:
        """Acknowledge pump errors."""
        value = self.data_converter.bool_2_boolean_old(True)
        self._set_channel_parameter('tc400', 9, value)

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

    def hk_monitor(self):
        """
        Perform housekeeping monitoring of HiPace300Bus parameters.
        Logs critical pump status information from both OmniControl and TC400.
        """
        try:
            # TC400 Pump Parameters
            self.custom_logger(
                self.device_id, self.port, "Pump_Station_Enabled", self.get_pumpStatn_enabled(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Standby_Mode", self.get_standby(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Motor_Pump_Enabled", self.get_motor_pump_enabled(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Vent_Enabled", self.get_vent_enabled(), ""
            )
            
            # Speed and Performance
            self.custom_logger(
                self.device_id, self.port, "Speed_Actual_Hz", self.get_actual_speed_hz(), "Hz"
            )
            self.custom_logger(
                self.device_id, self.port, "Speed_Actual_RPM", self.get_actual_speed_rpm(), "RPM"
            )
            self.custom_logger(
                self.device_id, self.port, "Speed_Set_Hz", self.get_set_speed_hz(), "Hz"
            )
            self.custom_logger(
                self.device_id, self.port, "Target_Speed_Reached", self.is_target_speed_reached(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Pump_Accelerating", self.is_pump_accelerating(), ""
            )
            
            # Electrical Parameters
            self.custom_logger(
                self.device_id, self.port, "Drive_Current", self.get_drive_current(), "A"
            )
            self.custom_logger(
                self.device_id, self.port, "Drive_Voltage", self.get_drive_voltage(), "V"
            )
            self.custom_logger(
                self.device_id, self.port, "Drive_Power", self.get_drive_power(), "W"
            )
            
            # Temperature Monitoring
            self.custom_logger(
                self.device_id, self.port, "Temp_Electronics", self.get_electronics_temperature(), "°C"
            )
            self.custom_logger(
                self.device_id, self.port, "Temp_Pump_Bottom", self.get_pump_bottom_temperature(), "°C"
            )
            self.custom_logger(
                self.device_id, self.port, "Temp_Bearing", self.get_bearing_temperature(), "°C"
            )
            self.custom_logger(
                self.device_id, self.port, "Temp_Motor", self.get_motor_temperature(), "°C"
            )
            
            # Status Monitoring
            self.custom_logger(
                self.device_id, self.port, "Overtemp_Electronics", self.is_overtemperature_electronics(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Overtemp_Pump", self.is_overtemperature_pump(), ""
            )
            
            # Gas Flow (TC400 specific)
            self.custom_logger(
                self.device_id, self.port, "Seal_Gas_Flow", self.get_seal_gas_flow(), "sccm"
            )
            
            # Operating Hours
            self.custom_logger(
                self.device_id, self.port, "Operating_Hours_Pump", self.get_operating_hours_pump(), "h"
            )
            self.custom_logger(
                self.device_id, self.port, "Operating_Hours_Electronics", self.get_operating_hours_electronics(), "h"
            )
            
            # Gauge Pressure (if available)
            if self.gauge1_address:
                self.custom_logger(
                    self.device_id, self.port, "Gauge_Pressure", self.get_gauge_pressure(), "hPa"
                )
                
        except Exception as e:
            self.logger.error(f"HiPace300Bus housekeeping monitoring failed: {e}")
