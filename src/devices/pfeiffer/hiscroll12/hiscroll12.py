"""
HiScroll12 device controller.

This module provides the HiScroll12 class for communicating with Pfeiffer
HiScroll12 vacuum pumps via serial communication using the telegram frame protocol.
"""
from typing import Optional
import logging
import threading

from ..base_device import PfeifferBaseDevice


class HiScroll12(PfeifferBaseDevice):
    """
    Pfeiffer HiScroll12 Scroll Pump Device Class.
    
    This class inherits from PfeifferBaseDevice and provides specific functionality
    for controlling HiScroll12 scroll pumps, including status monitoring, 
    setpoint configuration, and control commands.
    
    Example:
        pump = HiScroll12("hiscroll_01", port="COM5", device_address=1)
        pump.connect()
        pump.start_housekeeping()
        pump.enable_pump()
        pump.set_speed_setpoint(80.0)
        pump.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        device_address: int = 2, # because standard address of HiScroll12 is 2
        baudrate: int = 9600,
        timeout: float = 2.0,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 30.0,
        **kwargs,
    ):
        """
        Initialize HiScroll12 device.

        Args:
            device_id: Unique identifier for the device
            port: Serial port (e.g., 'COM5' on Windows, '/dev/ttyUSB0' on Linux)
            device_address: Pfeiffer device address (1-255)
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
    #     Status Requests
    # =============================================================================

    def get_error(self) -> str:
        """Get error status from the pump."""
        response = self.query_parameter(303)
        return self.data_converter.string_2_str(response)

    def get_overtemp_electronics(self) -> str:
        """Get electronics overtemperature status."""
        response = self.query_parameter(304)
        return self.data_converter.boolean_old_2_bool(response)

    def get_overtemp_pump(self) -> str:
        """Get pump overtemperature status."""
        response = self.query_parameter(305)
        return self.data_converter.boolean_old_2_bool(response)

    def get_set_rotation_speed_hz(self) -> float:
        """Get set rotation speed in Hz."""
        response = self.query_parameter(308)
        return self.data_converter.u_integer_2_int(response)

    def get_actual_rotation_speed_hz(self) -> float:
        """Get actual rotation speed in Hz."""
        response = self.query_parameter(309)
        return self.data_converter.u_integer_2_int(response)

    def get_drive_current(self) -> float:
        """Get drive current."""
        response = self.query_parameter(310)
        return self.data_converter.u_real_2_float(response)

    def get_pump_operating_time(self) -> int:
        """Get pump operating time in hours."""
        response = self.query_parameter(311)
        return self.data_converter.u_integer_2_int(response)

    def get_software_version(self) -> str:
        """Get software version."""
        response = self.query_parameter(312)
        return self.data_converter.string_2_str(response)

    def get_drive_voltage(self) -> float:
        """Get drive voltage."""
        response = self.query_parameter(313)
        return self.data_converter.u_real_2_float(response)

    def get_electronics_operating_time(self) -> int:
        """Get electronics operating time in hours."""
        response = self.query_parameter(314)
        return self.data_converter.u_integer_2_int(response)

    def get_nominal_speed_hz(self) -> float:
        """Get nominal speed in Hz."""
        response = self.query_parameter(315)
        return self.data_converter.u_integer_2_int(response)

    def get_drive_power(self) -> float:
        """Get drive power."""
        response = self.query_parameter(316)
        return self.data_converter.u_integer_2_int(response)

    def get_temp_power_stage(self) -> float:
        """Get power stage temperature in degC."""
        response = self.query_parameter(324)
        return self.data_converter.u_integer_2_int(response)

    def get_temp_electronics(self) -> float:
        """Get electronics temperature in degC."""
        response = self.query_parameter(326)
        return self.data_converter.u_integer_2_int(response)

    def get_temp_motor(self) -> float:
        """Get motor temperature in degC."""
        response = self.query_parameter(346)
        return self.data_converter.u_integer_2_int(response)

    def get_electronics_name(self) -> str:
        """Get electronics name."""
        response = self.query_parameter(349)
        return self.data_converter.string_2_str(response)

    def get_serial_number(self) -> str:
        """Get device serial number."""
        response = self.query_parameter(355)
        return self.data_converter.string16_2_str(response)

    def get_set_rotation_speed_rpm(self) -> float:
        """Get set rotation speed in RPM."""
        response = self.query_parameter(397)
        return self.data_converter.u_integer_2_int(response)

    def get_actual_rotation_speed_rpm(self) -> float:
        """Get actual rotation speed in RPM."""
        response = self.query_parameter(398)
        return self.data_converter.u_integer_2_int(response)

    def get_nominal_speed_rpm(self) -> float:
        """Get nominal speed in RPM."""
        response = self.query_parameter(399)
        return self.data_converter.u_integer_2_int(response)

    # =============================================================================
    #     Setpoint Specification
    # =============================================================================

    def get_speed_setpoint(self) -> float:
        """Get speed setpoint value (40-100%)."""
        response = self.query_parameter(707)
        return self.data_converter.u_real_2_float(response)

    def set_speed_setpoint(self, value: float) -> None:
        """
        Set speed setpoint value.
        
        Args:
            value: Speed value between 40 and 100 (%)
            
        Raises:
            ValueError: If value is not between 40 and 100
        """
        if not 40 <= value <= 100:
            raise ValueError("Speed setpoint must be between 40 and 100%")

        data_str = self.data_converter.float_2_u_real(value)
        self.write_parameter(707, data_str)

    def get_standby_setpoint(self) -> float:
        """Get standby setpoint value (40-100%)."""
        response = self.query_parameter(717)
        return self.data_converter.u_real_2_float(response)

    def set_standby_setpoint(self, value: float) -> None:
        """
        Set standby setpoint value.
        
        Args:
            value: Standby value between 40 and 100 (%)
            
        Raises:
            ValueError: If value is not between 40 and 100
        """
        if not 40 <= value <= 100:
            raise ValueError("Standby setpoint must be between 40 and 100%")

        data_str = self.data_converter.float_2_u_real(value)
        self.write_parameter(717, data_str)

    # =============================================================================
    #     Control Commands
    # =============================================================================

    def get_standby_mode(self) -> bool:
        """Get standby mode status."""
        response = self.query_parameter(2)
        return self.data_converter.booleanOld_2_bool(response)

    def set_standby_mode(self, enable: bool) -> None:
        """
        Set standby mode.
        
        Args:
            enable: True to enable standby, False to disable
        """
        data_str = self.data_converter.bool_2_booleanOld(enable)
        self.write_parameter(2, data_str)

    def enable_standby(self) -> None:
        """Enable standby mode."""
        self.set_standby_mode(True)

    def disable_standby(self) -> None:
        """Disable standby mode."""
        self.set_standby_mode(False)

    def acknowledge_error(self) -> None:
        """Acknowledge errors."""
        self.write_parameter(9, "111111")

    def get_pump_enable(self) -> bool:
        """Get pump enable status."""
        response = self.query_parameter(10)
        return self.data_converter.booleanOld_2_bool(response)

    def set_pump_enable(self, enable: bool) -> None:
        """
        Set pump enable status.
        
        Args:
            enable: True to enable pump, False to disable
        """
        data_str = self.data_converter.bool_2_booleanOld(enable)
        self.write_parameter(10, data_str)

    def enable_pump(self) -> None:
        """Enable the pump."""
        self.set_pump_enable(True)

    def disable_pump(self) -> None:
        """Disable the pump."""
        self.set_pump_enable(False)

    def reset_to_factory_settings(self) -> None:
        """Reset device to factory settings."""
        data_str = self.data_converter.bool_2_booleanOld(True)
        self.write_parameter(95, data_str)

    # =============================================================================
    #     Convenience Methods (Aliases)
    # =============================================================================

    # Pump control aliases
    def start_pump(self) -> None:
        """Start the pump (alias for enable_pump)."""
        self.enable_pump()

    def stop_pump(self) -> None:
        """Stop the pump (alias for disable_pump)."""
        self.disable_pump()

    def ack_error(self) -> None:
        """Acknowledge error (alias for acknowledge_error)."""
        self.acknowledge_error()

    # Temperature reading aliases
    def get_temperature_electronics(self) -> float:
        """Get electronics temperature (alias)."""
        return self.get_temp_electronics()

    def get_temperature_motor(self) -> float:
        """Get motor temperature (alias)."""
        return self.get_temp_motor()

    def get_temperature_power_stage(self) -> float:
        """Get power stage temperature (alias)."""
        return self.get_temp_power_stage()

    # Speed reading aliases
    def get_speed_hz(self) -> float:
        """Get actual speed in Hz (alias)."""
        return self.get_actual_rotation_speed_hz()

    def get_speed_rpm(self) -> float:
        """Get actual speed in RPM (alias)."""
        return self.get_actual_rotation_speed_rpm()

    # Status check aliases
    def is_standby(self) -> bool:
        """Check if pump is in standby mode."""
        return self.get_standby_mode()

    def is_pump_enabled(self) -> bool:
        """Check if pump is enabled."""
        return self.get_pump_enable()

    # =============================================================================
    #     Housekeeping Override
    # =============================================================================

    def hk_monitor(self):
        """
        Perform housekeeping monitoring of HiScroll12 parameters.
        Logs critical pump status information.
        """
        try:
            # Log critical pump parameters
            self.custom_logger(
                self.device_id, self.port, "Pump_Enabled", self.get_pump_enable(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Standby_Mode", self.get_standby_mode(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Speed_RPM", self.get_actual_rotation_speed_rpm(), "RPM"
            )
            self.custom_logger(
                self.device_id, self.port, "Speed_Hz", self.get_actual_rotation_speed_hz(), "Hz"
            )
            self.custom_logger(
                self.device_id, self.port, "Temp_Motor", self.get_temp_motor(), "degC"
            )
            self.custom_logger(
                self.device_id, self.port, "Temp_Electronics", self.get_temp_electronics(), "degC"
            )
            self.custom_logger(
                self.device_id, self.port, "Drive_Current", self.get_drive_current(), "A"
            )
            self.custom_logger(
                self.device_id, self.port, "Drive_Power", self.get_drive_power(), "W"
            )
            
        except Exception as e:
            self.logger.error(f"HiScroll12 housekeeping monitoring failed: {e}")
