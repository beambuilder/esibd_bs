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
        return self.data_converter.u_real_2_float(response)

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
    #     TPG366 Specific Methods (To be implemented)
    # =============================================================================
    
    # TODO: Implement pressure reading methods
    # TODO: Implement setpoint configuration methods  
    # TODO: Implement control commands
    # TODO: Implement convenience methods/aliases
    # TODO: Implement housekeeping override
