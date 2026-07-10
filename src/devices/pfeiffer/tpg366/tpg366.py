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
            auto_off_channels: Optional[list] = None,
            auto_off_above_hpa: float = 1e-4,
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
            auto_off_channels: Channels whose sensor is automatically turned
                OFF when its own reading rises above auto_off_above_hpa
                (delicate gauges that must not run at high pressure).
                Re-activation is always manual. Default: none.
            auto_off_above_hpa: Overpressure threshold for auto_off_channels
                in hPa (default: 1e-4)
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

        # Overpressure guard: sensors listed here are turned OFF by
        # hk_monitor() when their own reading exceeds the threshold
        # (delicate gauges — Transfer/Depo — must not run above ~1e-4 hPa).
        # Turning ON is never automatic (see the sensor on/off section).
        self.auto_off_channels = {int(c) for c in (auto_off_channels or [])}
        bad = self.auto_off_channels - set(range(1, 7))
        if bad:
            raise ValueError(f"auto_off_channels must be within 1-6, got {sorted(bad)}")
        self.auto_off_above_hpa = float(auto_off_above_hpa)

        # Simulated per-channel sensor state (test mode): CH1-3 start on,
        # CH4-6 off — mirrors the lab's typical state and shows both UI
        # states (curves and gaps) without touching hardware. sensor_on/off
        # flip these; an off channel reads pressure 0.0 like the hardware.
        self._sim_sensor_on = {1: True, 2: True, 3: True,
                               4: False, 5: False, 6: False}
        # Stable decade per channel (plus small jitter per read) so the
        # simulated curves look like measurements, not noise across decades.
        self._sim_base_exponent = {1: -6.0, 2: -7.2, 3: -8.1,
                                   4: -8.8, 5: -7.6, 6: -6.6}

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

        if self.test_mode:
            raise RuntimeError(
                "_query_channel_parameter() called in test_mode — simulate "
                "in the read method instead"
            )
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

        if self.test_mode:
            self.log_event("info", f"set channel {channel} param {param_num} = {value} (simulated)")
            return
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
        """Read pressure value from sensor channel 1."""
        return self.read_pressure_value(1)

    def read_pressure_value_channel_2(self) -> float:
        """Read pressure value from sensor channel 2."""
        return self.read_pressure_value(2)

    def read_pressure_value_channel_3(self) -> float:
        """Read pressure value from sensor channel 3."""
        return self.read_pressure_value(3)

    def read_pressure_value_channel_4(self) -> float:
        """Read pressure value from sensor channel 4."""
        return self.read_pressure_value(4)

    def read_pressure_value_channel_5(self) -> float:
        """Read pressure value from sensor channel 5."""
        return self.read_pressure_value(5)

    def read_pressure_value_channel_6(self) -> float:
        """Read pressure value from sensor channel 6."""
        return self.read_pressure_value(6)

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

        if self.test_mode:
            if not self._sim_sensor_on[channel]:
                return 0.0  # zero-mantissa telegram = sensor off, like hardware
            exponent = (self._sim_base_exponent[channel]
                        + self._sim_uniform(-0.08, 0.08))
            return round(10 ** exponent, 12)

        response = self._query_channel_parameter(channel, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def get_sensor_error(self, channel: int) -> str:
        """Get error status from specified sensor channel."""
        response = self._query_channel_parameter(channel, 303)
        return self.data_converter.string_2_str(response)

    # =============================================================================
    #     Sensor On/Off Methods
    #
    #     SAFETY: gauges can be DESTROYED if activated at atmospheric
    #     pressure. sensor_on() must NEVER be called from an automatic
    #     path (__init__, connect(), hk_monitor()) — it exists solely for
    #     an explicit external caller (the service ctrl API).
    #     sensor_off() is the opposite direction — protection — and IS
    #     called automatically by the hk_monitor overpressure guard for
    #     channels in auto_off_channels.
    # =============================================================================

    def sensor_on(self, channel: int) -> None:
        """
        Turn on the sensor for the specified channel.

        Args:
            channel: Sensor channel number (1-6)

        Raises:
            ValueError: If channel is not an int between 1 and 6
        """
        if not isinstance(channel, int) or not 1 <= channel <= 6:
            raise ValueError("Channel must be between 1 and 6")

        if self.test_mode:
            self._sim_sensor_on[channel] = True
            self.log_event("info", f"sensor CH{channel} on (simulated)")
            return

        value = self.data_converter.int_2_u_short_int(1)
        self._set_channel_parameter(channel, 41, value)

    def sensor_off(self, channel: int) -> None:
        """
        Turn off the sensor for the specified channel.

        Args:
            channel: Sensor channel number (1-6)

        Raises:
            ValueError: If channel is not an int between 1 and 6
        """
        if not isinstance(channel, int) or not 1 <= channel <= 6:
            raise ValueError("Channel must be between 1 and 6")

        if self.test_mode:
            self._sim_sensor_on[channel] = False
            self.log_event("info", f"sensor CH{channel} off (simulated)")
            return

        value = self.data_converter.int_2_u_short_int(0)
        self._set_channel_parameter(channel, 41, value)

    def get_sensor_on(self, channel: int) -> bool:
        """
        Get sensor on/off state for the specified channel.

        Args:
            channel: Sensor channel number (1-6)

        Returns:
            bool: True if the sensor is on, False if off

        Raises:
            ValueError: If channel is not an int between 1 and 6
        """
        if not isinstance(channel, int) or not 1 <= channel <= 6:
            raise ValueError("Channel must be between 1 and 6")

        if self.test_mode:
            return self._sim_sensor_on[channel]

        response = self._query_channel_parameter(channel, 41)
        return bool(self.data_converter.u_short_int_2_int(response))

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
        """
        One housekeeping cycle: for each of the 6 channels, report the
        sensor on/off state and, only for channels reporting on, the
        pressure.

        Hardware quirk (found on real hardware the night of 2026-07-03): a
        deactivated sensor does NOT return the zero-mantissa telegram (that
        only happens for a channel that has never measured since
        power-up) — it returns the LAST measured value, frozen. Reading
        pressure unconditionally would silently re-log that frozen value
        as a fresh measurement every cycle (this is exactly what happened
        to CH4/CH5 overnight). So the on/off state (param 41) is read
        first and gates the pressure read/log; 0.0 is still skipped since
        it is never a real measurement either (log-scale plots break on
        it).

        Each channel runs in its own try/except so one failing channel
        cannot suppress the others. If the state read itself fails, fall
        back to the old read-and-skip-zero behavior for that channel — a
        transient state-read hiccup must not black-hole real data.

        Overpressure guard: channels in auto_off_channels are turned OFF
        when their reading exceeds auto_off_above_hpa (or is the
        over-range sentinel — by definition above any threshold).
        Re-activation is always manual.
        """
        for channel in range(1, 7):
            try:
                on = self.get_sensor_on(channel)
            except Exception as e:
                self.log_event("warning", f"Sensor_CH{channel}_On read failed: {e}")
                try:
                    value = self.read_pressure_value(channel)
                    if value != 0.0 and not self.data_converter.is_pressure_sentinel(value):
                        self.log_sample(f"Sensor_CH{channel}_Press", value, "hPa", fmt=".2e")
                    # On-state unknown here; an off command to an already-off
                    # sensor is harmless, so the guard still applies.
                    self._check_overpressure_off(channel, value)
                except Exception as e2:
                    self.log_event("warning", f"Sensor_CH{channel}_Press read failed: {e2}")
                continue

            self.log_sample(f"Sensor_CH{channel}_On", 1.0 if on else 0.0)
            if not on:
                continue  # deactivated: register is frozen on the last reading — don't read/log it

            try:
                value = self.read_pressure_value(channel)
                if value == 0.0 or self.data_converter.is_pressure_sentinel(value):
                    # Zero mantissa (never measured since power-up) or the all-nines
                    # over-range sentinel — skip it, never a real measurement
                    # (log-scale plots break on 0.0, autoscale on 9.999e+79).
                    pass
                else:
                    self.log_sample(f"Sensor_CH{channel}_Press", value, "hPa", fmt=".2e")
                self._check_overpressure_off(channel, value)
            except Exception as e:
                self.log_event("warning", f"Sensor_CH{channel}_Press read failed: {e}")

    def _check_overpressure_off(self, channel: int, value: float) -> None:
        """
        Overpressure guard: turn a delicate sensor OFF when its own reading
        exceeds the threshold. The over-range sentinel counts as above any
        threshold; 0.0 (never measured) never triggers. Turning back ON is
        always manual (ctrl API / dashboard) — this method never calls
        sensor_on().
        """
        if channel not in self.auto_off_channels or value == 0.0:
            return
        if value <= self.auto_off_above_hpa and not self.data_converter.is_pressure_sentinel(value):
            return

        try:
            self.sensor_off(channel)
        except Exception as e:
            self.log_event(
                "error",
                f"Sensor_CH{channel} overpressure auto-off FAILED at "
                f"{value:.2e} hPa: {e}",
            )
            return

        self.log_event(
            "warning",
            f"Sensor_CH{channel} auto-disabled: {value:.2e} hPa above "
            f"{self.auto_off_above_hpa:.0e} hPa limit — re-enable manually "
            f"once the chamber is back at vacuum",
        )
        # Flip the telemetry state immediately so the dashboard switch goes
        # red this cycle instead of one hk_interval later.
        self.log_sample(f"Sensor_CH{channel}_On", 0.0)