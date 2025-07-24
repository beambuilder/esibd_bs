"""
Arduino device controller.

This module provides the Arduino class for communicating with Arduino
microcontrollers via serial communication protocols.
"""

from typing import Any, Dict, Optional
import serial
import logging
import re


class Arduino:
    """
    Arduino microcontroller communication class.

    This class handles serial communication with Arduino devices,
    providing methods for sending commands and reading responses.

    Example:
        arduino = Arduino("lab_arduino_01", port="COM3", baudrate=9600)
        arduino.connect()
        value = arduino.read_analog_pin(0)
        arduino.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.0,
        data_parser: str = "pump_locker",
        **kwargs,
    ):
        """
        Initialize Arduino device.

        Args:
            device_id: Unique identifier for the Arduino
            port: Serial port (e.g., 'COM3' on Windows, '/dev/ttyUSB0' on Linux)
            baudrate: Communication speed (default: 9600)
            timeout: Serial communication timeout in seconds
            data_parser: Parser type ("pump_locker", "trafo_locker", "custom", etc.)
            **kwargs: Additional connection parameters
        """
        self.device_id = device_id
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.data_parser = data_parser
        self.is_connected = False
        self.serial_connection: Optional[serial.Serial] = None
        self.logger = logging.getLogger(f"Arduino_{device_id}")

    def connect(self) -> bool:
        """
        Establish serial connection to the Arduino.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.logger.info(f"Connecting to Arduino {self.device_id} on {self.port}")
            self.serial_connection = serial.Serial(
                self.port, self.baudrate, timeout=self.timeout
            )
            self.is_connected = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Arduino: {e}")
            return False

    def disconnect(self) -> bool:
        """
        Close serial connection to the Arduino.

        Returns:
            bool: True if disconnection successful, False otherwise
        """
        try:
            if self.serial_connection:
                self.serial_connection.close()
            self.is_connected = False
            self.logger.info(f"Disconnected from Arduino {self.device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disconnect from Arduino: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Get current Arduino status.

        Returns:
            Dict[str, Any]: Dictionary containing Arduino status information
        """
        return {
            "device_id": self.device_id,
            "port": self.port,
            "baudrate": self.baudrate,
            "connected": self.is_connected,
            "timeout": self.timeout,
        }

    def parse_data(self, data_line: str) -> Optional[Dict[str, Any]]:
        """
        Parse Arduino data line based on the configured parser type.

        Args:
            data_line: Raw data line from Arduino

        Returns:
            dict: Parsed data or None if parsing fails
        """
        if not data_line:
            return None

        if self.data_parser == "pump_locker":
            return self._parse_pump_locker_data(data_line)
        elif self.data_parser == "trafo_locker":
            return self._parse_trafo_locker_data(data_line)
        elif self.data_parser == "custom":
            return self._parse_custom_data(data_line)
        else:
            # Default: return raw data
            return {"raw_data": data_line}

    def _parse_pump_locker_data(self, data_line: str) -> Optional[Dict[str, Any]]:
        """
        Parse temperature, fan and waterflow data.
        Expected format: "Temperature: 23.44 °C | Fan_PWR: 60 % | Waterflow: 15.2 L/min"
        """
        pattern = r"Temperature:\s*([\d.]+)\s*°C\s*\|\s*Fan_PWR:\s*(\d+)\s*%\s*\|\s*Waterflow:\s*([\d.]+)\s*L/min"
        match = re.search(pattern, data_line)

        if match:
            try:
                temperature = float(match.group(1))
                fan_power = int(match.group(2))
                waterflow = float(match.group(3))
                return {
                    "temperature": temperature,
                    "fan_power": fan_power,
                    "waterflow": waterflow,
                    "raw_data": data_line,
                }
            except ValueError:
                return None
        return None

    def _parse_trafo_locker_data(self, data_line: str) -> Optional[Dict[str, Any]]:
        """
        Parse temperature and fan data.
        Expected format: "Temperature: 23.44 °C | Fan_PWR: 60 %"
        """
        pattern = r"Temperature:\s*([\d.]+)\s*°C\s*\|\s*Fan_PWR:\s*(\d+)\s*%"
        match = re.search(pattern, data_line)

        if match:
            try:
                temperature = float(match.group(1))
                fan_power = int(match.group(2))
                return {
                    "temperature": temperature,
                    "fan_power": fan_power,
                    "raw_data": data_line,
                }
            except ValueError:
                return None
        return None

    def _parse_custom_data(self, data_line: str) -> Optional[Dict[str, Any]]:
        """
        Parse custom data format.
        Override this method for custom parsing logic.
        """
        return {"raw_data": data_line}

    def readout(self) -> Optional[str]:
        """
        Read a line from Arduino serial monitor

        Returns:
            str: The line read from Arduino, or None if no data/error
        """
        if not self.is_connected or not self.serial_connection:
            print("Arduino not connected. Call connect() first.")
            return None

        try:
            if self.serial_connection.in_waiting > 0:
                # Read line and decode from bytes to string
                line = (
                    self.serial_connection.readline()
                    .decode("utf-8", errors="ignore")
                    .strip()
                )
                return line
            else:
                return None
        except serial.SerialException as e:
            print(f"Error reading from Arduino: {e}")
            return None

    def read_arduino_data(self) -> Optional[Dict[str, Any]]:
        """
        Read and parse data from Arduino.

        Returns:
            dict: Parsed data or None if reading fails
        """
        data_line = self.readout()
        if data_line:
            return self.parse_data(data_line)
        else:
            print("No data received from Arduino.")
            return None
