"""
Arduino base device controller.

This module provides the Arduino base class for communicating with Arduino
microcontrollers via serial CSV lines, built on ``SerialDeviceBase``
(uniform constructor, canonical logging, telemetry sink, explicit test
mode). Subclass this for specific Arduino configurations (e.g.,
PumpArduino, TrafoArduino).
"""

from abc import abstractmethod
from typing import Any, Dict, Optional

import serial

from ..serial_device import SerialDeviceBase


class Arduino(SerialDeviceBase):
    """
    Arduino microcontroller communication base class.

    This class handles serial communication with Arduino devices,
    providing methods for sending commands and reading responses.
    Subclasses implement device-specific data parsing and housekeeping.

    The Arduino firmware prints a CSV header line every 20 data lines.
    Non-numeric lines (headers) are rejected by ``parse_data()`` in each
    subclass — no separate filtering step is needed.

    Example:
        from devices.arduino.pump_arduino import PumpArduino

        arduino = PumpArduino("pump_01", port="COM3", baudrate=9600)
        arduino.connect()
        data = arduino.read_arduino_data()
        arduino.disconnect()
    """

    FAMILY = "Arduino"

    def __init__(
        self,
        device_id: str,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.0,
        hk_interval: float = 1.0,
        **kwargs,
    ):
        """
        Initialize Arduino device (see ``SerialDeviceBase`` for the shared
        parameters ``logger``, ``sink``, ``test_mode``, ``hk_thread``,
        ``thread_lock``).
        """
        super().__init__(
            device_id=device_id,
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            hk_interval=hk_interval,
            **kwargs,
        )

    # =========================================================================
    #     Serial I/O
    # =========================================================================

    def readout(self) -> Optional[str]:
        """
        Read a line from the Arduino serial port.

        Returns the raw stripped line, or None if nothing is available.
        Non-numeric lines (e.g. periodic CSV headers) are handled by
        ``parse_data()`` in each subclass — they simply return None.

        Returns:
            str: The line read from Arduino, or None if no data / error.
        """
        if not self.is_connected or not self.serial_connection:
            self.log_event("warning", "not connected, call connect() first")
            return None

        try:
            with self.thread_lock:
                if self.serial_connection.in_waiting > 0:
                    line = (
                        self.serial_connection.readline()
                        .decode("utf-8", errors="ignore")
                        .strip()
                    )
                    return line if line else None
                else:
                    return None
        except serial.SerialException as e:
            self.log_event("error", f"serial read failed: {e}")
            return None

    # =========================================================================
    #     Data Parsing / Simulation (override in subclasses)
    # =========================================================================

    @abstractmethod
    def parse_data(self, data_line: str) -> Optional[Dict[str, Any]]:
        """
        Parse an Arduino CSV data line into a dict.

        Subclasses **must** implement this for their specific data format.

        Args:
            data_line: Raw CSV data line from the Arduino (header already filtered).

        Returns:
            dict with parsed values, or None if parsing fails.
        """
        ...

    def _sim_data(self) -> Optional[Dict[str, Any]]:
        """
        Produce one simulated data dict (same keys as ``parse_data``).

        Subclasses with a test-mode simulator override this.
        """
        return None

    def read_arduino_data(self) -> Optional[Dict[str, Any]]:
        """
        Read and parse one line of data from the Arduino.

        In test mode this returns the subclass's simulated data instead of
        touching the serial port.

        Returns:
            dict: Parsed data or None if reading/parsing fails.
        """
        if self.test_mode:
            return self._sim_data()

        data_line = self.readout()
        if data_line:
            return self.parse_data(data_line)
        else:
            self.logger.debug("No data received from Arduino.")
            return None

    # =========================================================================
    #     Housekeeping (override hk_monitor in subclasses)
    # =========================================================================

    @abstractmethod
    def hk_monitor(self) -> None:
        """
        Perform one housekeeping read-and-log cycle.

        Subclasses implement this to read sensor data and report it using
        ``log_sample``.
        """
        ...
