"""
HiPace300Bus device controller.

This module provides the HiPace300Bus class for communicating with Pfeiffer
HiPace300Bus turbo molecular pumps via serial communication using the 
telegram frame protocol.
"""
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
        device_address: int = 1,  # HiPace300Bus standard address
        baudrate: int = 9600,
        timeout: float = 2.0,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 30.0,
        **kwargs,
    ):
        """
        Initialize HiPace300Bus device.

        Args:
            device_id: Unique identifier for the device
            port: Serial port (e.g., 'COM7' on Windows, '/dev/ttyUSB0' on Linux)
            device_address: Pfeiffer device address (1-255, default: 1)
            baudrate: Communication speed (default: 9600)
            timeout: Serial communication timeout in seconds (default: 2.0)
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 30.0)
            **kwargs: Additional connection parameters
        """
        super().__init__(
            device_id=device_id,
            port=port,
            device_address=device_address,
            baudrate=baudrate,
            timeout=timeout,
            logger=logger,
            hk_thread=hk_thread,
            thread_lock=thread_lock,
            hk_interval=hk_interval,
            **kwargs
        )

    # =============================================================================
    #     Bus Communication Helpers
    # =============================================================================
    
    def _query_omnicontrol_parameter(self, param_num: int) -> str:
        """
        Query a parameter from the OmniControl device (base device).
        
        Args:
            param_num: Parameter number to query
            
        Returns:
            str: Raw response from device
            
        Raises:
            Exception: If device not connected or communication fails
        """
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        try:
            with self.thread_lock:  # Thread-safe communication
                from ..pfeifferVacuumProtocol import query_data
                return query_data(self.serial_connection, self.device_address, param_num)
        except Exception as e:
            self.logger.error(f"Failed to query OmniControl parameter {param_num}: {e}")
            raise

    def _set_omnicontrol_parameter(self, param_num: int, value: str) -> None:
        """
        Set a parameter on the OmniControl device (base device).
        
        Args:
            param_num: Parameter number to set
            value: Value to set
            
        Raises:
            Exception: If device not connected or communication fails
        """
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        try:
            with self.thread_lock:  # Thread-safe communication
                from ..pfeifferVacuumProtocol import write_command
                write_command(self.serial_connection, self.device_address, param_num, value)
        except Exception as e:
            self.logger.error(f"Failed to set OmniControl parameter {param_num}: {e}")
            raise

    def _query_tc400_parameter(self, param_num: int) -> str:
        """
        Query a parameter from the TC400 device (turbo controller).
        
        Args:
            param_num: Parameter number to query
            
        Returns:
            str: Raw response from device
            
        Raises:
            Exception: If device not connected or communication fails
        """
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        # TC400 address is base_address + 1
        tc400_address = self.device_address + 1
        
        try:
            with self.thread_lock:  # Thread-safe communication
                from ..pfeifferVacuumProtocol import query_data
                return query_data(self.serial_connection, tc400_address, param_num)
        except Exception as e:
            self.logger.error(f"Failed to query TC400 parameter {param_num}: {e}")
            raise

    def _set_tc400_parameter(self, param_num: int, value: str) -> None:
        """
        Set a parameter on the TC400 device (turbo controller).
        
        Args:
            param_num: Parameter number to set
            value: Value to set
            
        Raises:
            Exception: If device not connected or communication fails
        """
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        # TC400 address is base_address + 1
        tc400_address = self.device_address + 1
        
        try:
            with self.thread_lock:  # Thread-safe communication
                from ..pfeifferVacuumProtocol import write_command
                write_command(self.serial_connection, tc400_address, param_num, value)
        except Exception as e:
            self.logger.error(f"Failed to set TC400 parameter {param_num}: {e}")
            raise

    # =============================================================================
    #     OmniControl Methods (Base Device)
    # =============================================================================

    def get_omni_error_code(self) -> str:
        """Get error code from OmniControl."""
        response = self._query_omnicontrol_parameter(303)
        return self.data_converter.string_2_str(response)

    def get_omni_firmware_version(self) -> str:
        """Get firmware version from OmniControl."""
        response = self._query_omnicontrol_parameter(312)
        return self.data_converter.string_2_str(response)

    def get_omni_device_name(self) -> str:
        """Get device designation from OmniControl."""
        response = self._query_omnicontrol_parameter(349)
        return self.data_converter.string_2_str(response)

    def get_omni_hardware_version(self) -> str:
        """Get hardware version from OmniControl."""
        response = self._query_omnicontrol_parameter(354)
        return self.data_converter.string_2_str(response)

    def get_omni_serial_number(self) -> str:
        """Get serial number from OmniControl."""
        response = self._query_omnicontrol_parameter(355)
        return self.data_converter.string16_2_str(response)

    def get_omni_pressure(self) -> float:
        """Get pressure value from OmniControl."""
        response = self._query_omnicontrol_parameter(740)
        return self.data_converter.u_expo_new_2_float(response)

    def set_omni_pressure_zero(self, zero_on: bool) -> None:
        """Set pressure zero function (0=zero on, not 0=zero off)."""
        value = "000000" if zero_on else "000001"
        self._set_omnicontrol_parameter(740, value)

    def get_omni_rs485_address(self) -> int:
        """Get RS485 interface address from OmniControl."""
        response = self._query_omnicontrol_parameter(797)
        return self.data_converter.u_integer_2_int(response)

    def set_omni_rs485_address(self, address: int) -> None:
        """Set RS485 interface address on OmniControl."""
        if not (1 <= address <= 255):
            raise ValueError("RS485 address must be between 1-255")
        value = self.data_converter.int_2_u_integer(address)
        self._set_omnicontrol_parameter(797, value)

    # =============================================================================
    #     TC400 Pump Control Methods
    # =============================================================================

    def enable_pump(self) -> None:
        """Enable/start the turbo pump."""
        value = self.data_converter.bool_2_boolean_old(True)
        self._set_tc400_parameter(10, value)

    def disable_pump(self) -> None:
        """Disable/stop the turbo pump."""
        value = self.data_converter.bool_2_boolean_old(False)
        self._set_tc400_parameter(10, value)

    def enable_heating(self) -> None:
        """Enable pump heating."""
        value = self.data_converter.bool_2_boolean_old(True)
        self._set_tc400_parameter(1, value)

    def disable_heating(self) -> None:
        """Disable pump heating."""
        value = self.data_converter.bool_2_boolean_old(False)
        self._set_tc400_parameter(1, value)

    def set_standby(self, enabled: bool) -> None:
        """Set pump standby mode."""
        value = self.data_converter.bool_2_boolean_old(enabled)
        self._set_tc400_parameter(2, value)

    def acknowledge_error(self) -> None:
        """Acknowledge pump errors."""
        value = self.data_converter.bool_2_boolean_old(True)
        self._set_tc400_parameter(9, value)

    # =============================================================================
    #     TC400 Status Query Methods
    # =============================================================================

    def get_pump_error_code(self) -> str:
        """Get error code from TC400."""
        response = self._query_tc400_parameter(303)
        return self.data_converter.string_2_str(response)

    def get_pump_firmware_version(self) -> str:
        """Get firmware version from TC400."""
        response = self._query_tc400_parameter(312)
        return self.data_converter.string_2_str(response)

    def get_pump_device_name(self) -> str:
        """Get device designation from TC400."""
        response = self._query_tc400_parameter(349)
        return self.data_converter.string_2_str(response)

    def get_actual_speed_hz(self) -> int:
        """Get actual pump speed in Hz."""
        response = self._query_tc400_parameter(309)
        return self.data_converter.u_integer_2_int(response)

    def get_actual_speed_rpm(self) -> int:
        """Get actual pump speed in RPM."""
        response = self._query_tc400_parameter(398)
        return self.data_converter.u_integer_2_int(response)

    def get_target_speed_hz(self) -> int:
        """Get target pump speed in Hz."""
        response = self._query_tc400_parameter(308)
        return self.data_converter.u_integer_2_int(response)

    def get_drive_current(self) -> float:
        """Get drive current in A."""
        response = self._query_tc400_parameter(310)
        return self.data_converter.u_real_2_float(response)

    def get_drive_voltage(self) -> float:
        """Get drive voltage in V."""
        response = self._query_tc400_parameter(313)
        return self.data_converter.u_real_2_float(response)

    def get_drive_power(self) -> int:
        """Get drive power in W."""
        response = self._query_tc400_parameter(316)
        return self.data_converter.u_integer_2_int(response)

    def get_operating_hours_pump(self) -> int:
        """Get operating hours of pump in hours."""
        response = self._query_tc400_parameter(311)
        return self.data_converter.u_integer_2_int(response)

    def get_electronics_temperature(self) -> int:
        """Get electronics temperature in °C."""
        response = self._query_tc400_parameter(326)
        return self.data_converter.u_integer_2_int(response)

    def get_pump_bottom_temperature(self) -> int:
        """Get pump bottom temperature in °C."""
        response = self._query_tc400_parameter(330)
        return self.data_converter.u_integer_2_int(response)

    def get_bearing_temperature(self) -> int:
        """Get bearing temperature in °C."""
        response = self._query_tc400_parameter(342)
        return self.data_converter.u_integer_2_int(response)

    def is_target_speed_reached(self) -> bool:
        """Check if target speed is reached."""
        response = self._query_tc400_parameter(306)
        return self.data_converter.boolean_old_2_bool(response)

    def is_pump_accelerating(self) -> bool:
        """Check if pump is accelerating."""
        response = self._query_tc400_parameter(307)
        return self.data_converter.boolean_old_2_bool(response)

    # =============================================================================
    #     TC400 Setpoint Methods
    # =============================================================================

    def set_speed_setpoint(self, speed_percent: float) -> None:
        """Set speed control setpoint in percent."""
        if not (0.0 <= speed_percent <= 100.0):
            raise ValueError("Speed setpoint must be between 0-100%")
        value = self.data_converter.float_2_u_real(speed_percent)
        self._set_tc400_parameter(707, value)

    def get_speed_setpoint(self) -> float:
        """Get speed control setpoint in percent."""
        response = self._query_tc400_parameter(707)
        return self.data_converter.u_real_2_float(response)

    def set_rs485_address(self, address: int) -> None:
        """Set RS485 address for TC400."""
        if not (1 <= address <= 255):
            raise ValueError("RS485 address must be between 1-255")
        value = self.data_converter.int_2_u_integer(address)
        self._set_tc400_parameter(797, value)

    def get_rs485_address(self) -> int:
        """Get RS485 address from TC400."""
        response = self._query_tc400_parameter(797)
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
            status['target_speed_hz'] = self.get_target_speed_hz()
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
            info['pressure'] = self.get_omni_pressure()
        except Exception as e:
            self.logger.error(f"Failed to get system info: {e}")
            info['error'] = str(e)
        return info
