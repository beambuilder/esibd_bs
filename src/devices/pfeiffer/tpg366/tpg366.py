"""
TPG366 device controller.

This module provides the TPG366 class for communicating with Pfeiffer
TPG366 pressure measurement and control units via serial communication 
using the telegram frame protocol.
"""
from typing import Optional
import logging
import threading

from ..base_device import PfeifferBaseDevice


class TPG366(PfeifferBaseDevice):
    """
    Pfeiffer TPG366 Pressure Measurement and Control Unit Class.
    
    This class inherits from PfeifferBaseDevice and provides specific functionality
    for controlling TPG366 pressure measurement units, including pressure readings,
    setpoint configuration, and control commands.
    
    Example:
        gauge = TPG366("tpg366_01", port="COM6", device_address=1)
        gauge.connect()
        gauge.start_housekeeping()
        pressure = gauge.get_pressure(1)  # Read pressure from sensor 1
        gauge.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        device_address: int = 1,  # TPG366 standard address
        baudrate: int = 9600,
        timeout: float = 2.0,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 30.0,
        **kwargs,
    ):
        """
        Initialize TPG366 device.

        Args:
            device_id: Unique identifier for the device
            port: Serial port (e.g., 'COM6' on Windows, '/dev/ttyUSB0' on Linux)
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
    #     Channel-Specific Communication Helper
    # =============================================================================
    
    def _query_channel_parameter(self, channel: int, param_num: int) -> str:
        """
        Query a parameter from a specific TPG366 sensor channel.
        
        Args:
            channel: Sensor channel number (1-6)
            param_num: Parameter number to query
            
        Returns:
            str: Raw response from device
            
        Raises:
            ValueError: If channel is not between 1 and 6
            Exception: If device not connected or communication fails
        """
        if not 1 <= channel <= 6:
            raise ValueError("Channel must be between 1 and 6")
            
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        # Calculate channel address: base_address + channel
        channel_address = self.device_address + channel
        
        try:
            with self.thread_lock:  # Thread-safe communication
                from ..pfeifferVacuumProtocol import query_data
                return query_data(self.serial_connection, channel_address, param_num)
        except Exception as e:
            self.logger.error(f"Failed to query channel {channel} parameter {param_num}: {e}")
            raise

    def _set_channel_parameter(self, channel: int, param_num: int, value: str) -> None:
        """
        Set a parameter on a specific TPG366 sensor channel.
        
        Args:
            channel: Sensor channel number (1-6)
            param_num: Parameter number to set
            value: Value to set
            
        Raises:
            ValueError: If channel is not between 1 and 6
            Exception: If device not connected or communication fails
        """
        if not 1 <= channel <= 6:
            raise ValueError("Channel must be between 1 and 6")
            
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        # Calculate channel address: base_address + channel
        channel_address = self.device_address + channel
        
        try:
            with self.thread_lock:  # Thread-safe communication
                from ..pfeifferVacuumProtocol import write_command
                write_command(self.serial_connection, channel_address, param_num, value)
        except Exception as e:
            self.logger.error(f"Failed to set channel {channel} parameter {param_num}: {e}")
            raise

    # =============================================================================
    #     Device Configuration Methods
    # =============================================================================

    def get_serial_number(self) -> str:
        """Get serial number."""
        response = self.query_parameter(355)
        return self.data_converter.string16_2_str(response)

    def get_hardware_version(self) -> str:
        """Get hardware version."""
        response = self.query_parameter(354)
        return self.data_converter.string_2_str(response)

    def set_rs485_address(self, address: int) -> None:
        """Set RS485 address."""
        if not (10 <= address <= 240) or address % 10 != 0:
            raise ValueError("RS485 address must be between 10-240 and divisible by 10")
        value = self.data_converter.int_2_u_integer(address)
        self.set_parameter(797, value)

    # =============================================================================
    #     Pressure Reading Methods
    # =============================================================================

    def read_pressure_value_channel_1(self) -> float:
        """
        Read pressure value from sensor channel 1.
        
        Returns:
            float: Pressure value from channel 1
        """
        response = self._query_channel_parameter(1, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_2(self) -> float:
        """
        Read pressure value from sensor channel 2.
        
        Returns:
            float: Pressure value from channel 2
        """
        response = self._query_channel_parameter(2, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_3(self) -> float:
        """
        Read pressure value from sensor channel 3.
        
        Returns:
            float: Pressure value from channel 3
        """
        response = self._query_channel_parameter(3, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_4(self) -> float:
        """
        Read pressure value from sensor channel 4.
        
        Returns:
            float: Pressure value from channel 4
        """
        response = self._query_channel_parameter(4, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_5(self) -> float:
        """
        Read pressure value from sensor channel 5.
        
        Returns:
            float: Pressure value from channel 5
        """
        response = self._query_channel_parameter(5, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_6(self) -> float:
        """
        Read pressure value from sensor channel 6.
        
        Returns:
            float: Pressure value from channel 6
        """
        response = self._query_channel_parameter(6, 740)
        return self.data_converter.u_expo_new_2_float(response)

    # =============================================================================
    #     Convenience Method for Generic Channel Access
    # =============================================================================

    def read_pressure_value(self, channel: int) -> float:
        """
        Read pressure value from specified sensor channel.
        
        Args:
            channel: Sensor channel number (1-6)
            
        Returns:
            float: Pressure value from specified channel
            
        Raises:
            ValueError: If channel is not between 1 and 6
        """
        if not 1 <= channel <= 6:
            raise ValueError("Channel must be between 1 and 6")
            
        response = self._query_channel_parameter(channel, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def get_sensor_error(self, channel: int) -> str:
        """Get error status from specified sensor channel."""
        response = self._query_channel_parameter(channel, 303)
        return self.data_converter.string_2_str(response)

    # =============================================================================
    #     Base Device Status Methods (from HiScroll12)
    # =============================================================================

    def get_error(self) -> str:
        """Get error status from the pump."""
        response = self.query_parameter(303)
        return self.data_converter.string_2_str(response)

    def get_software_version(self) -> str:
        """Get software version."""
        response = self.query_parameter(312)
        return self.data_converter.string_2_str(response)

    def get_electronics_name(self) -> str:
        """Get electronics name."""
        response = self.query_parameter(349)
        return self.data_converter.string_2_str(response)

    def get_rs485_address(self) -> int:
        """Get RS485 address."""
        response = self.query_parameter(797)
        return self.data_converter.u_integer_2_int(response)

    # =============================================================================
    #     Pressure Threshold Methods
    # =============================================================================

    def get_switch_on_threshold(self, channel: int) -> float:
        """Get switch-on threshold for specified channel."""
        response = self._query_channel_parameter(channel, 730)
        return self.data_converter.u_expo_new_2_float(response)

    def set_switch_on_threshold(self, channel: int, threshold: float) -> None:
        """Set switch-on threshold for specified channel."""
        if not (1e-5 <= threshold <= 1.0):
            raise ValueError("Switch-on threshold must be between 1E-5 and 1.0 hPa")
        value = self.data_converter.float_2_u_expo_new(threshold)
        self._set_channel_parameter(channel, 730, value)

    def get_switch_off_threshold(self, channel: int) -> float:
        """Get switch-off threshold for specified channel."""
        response = self._query_channel_parameter(channel, 732)
        return self.data_converter.u_expo_new_2_float(response)

    def set_switch_off_threshold(self, channel: int, threshold: float) -> None:
        """Set switch-off threshold for specified channel."""
        value = self.data_converter.float_2_u_expo_new(threshold)
        self._set_channel_parameter(channel, 732, value)

    def get_correction_factor(self, channel: int) -> float:
        """Get correction factor for specified channel."""
        response = self._query_channel_parameter(channel, 742)
        return self.data_converter.u_real_2_float(response)

    def set_correction_factor(self, channel: int, factor: float) -> None:
        """Set correction factor for specified channel."""
        if not (0.10 <= factor <= 10.00):
            raise ValueError("Correction factor must be between 0.10 and 10.00")
        value = self.data_converter.float_2_u_real(factor)
        self._set_channel_parameter(channel, 742, value)

    # =============================================================================
    #     Convenience Aliases
    # =============================================================================

    def get_pressure(self, channel: int) -> float:
        """Alias for read_pressure_value."""
        return self.read_pressure_value(channel)

    def get_firmware_version(self) -> str:
        """Alias for get_software_version."""
        return self.get_software_version()
    #ToDO: get sensor name, try if get serial number works on sensors as well as on base device
    def get_device_name(self) -> str:
        """Alias for get_electronics_name."""
        return self.get_electronics_name()

    # =============================================================================
    #     Multi-Channel Operations
    # =============================================================================

    def read_all_pressures(self) -> dict:
        """
        Read pressure values from all 6 channels.
        
        Returns:
            dict: Dictionary with channel numbers as keys and pressure values as values
        """
        pressures = {}
        for channel in range(1, 7):
            try:
                pressures[channel] = self.read_pressure_value(channel)
            except Exception as e:
                self.logger.warning(f"Failed to read pressure from channel {channel}: {e}")
                pressures[channel] = None
        return pressures

    def get_all_correction_factors(self) -> dict:
        """
        Get correction factors from all 6 channels.
        
        Returns:
            dict: Dictionary with channel numbers as keys and correction factors as values
        """
        factors = {}
        for channel in range(1, 7):
            try:
                factors[channel] = self.get_correction_factor(channel)
            except Exception as e:
                self.logger.warning(f"Failed to get correction factor from channel {channel}: {e}")
                factors[channel] = None
        return factors

    def set_all_correction_factors(self, factor: float) -> None:
        """
        Set the same correction factor for all 6 channels.
        
        Args:
            factor: Correction factor to set (0.10 to 10.00)
        """
        for channel in range(1, 7):
            try:
                self.set_correction_factor(channel, factor)
            except Exception as e:
                self.logger.error(f"Failed to set correction factor for channel {channel}: {e}")

    def hk_monitor(self):
        #TODO: Implement housekeeping monitoring for TPG366
        return super().hk_monitor()
