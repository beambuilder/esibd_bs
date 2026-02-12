"""
Arduino base device controller.

This module provides the Arduino base class for communicating with Arduino
microcontrollers via serial communication protocols. Subclass this for
specific Arduino configurations (e.g., PumpArduino, TrafoArduino).
"""

from typing import Any, Dict, Optional
import serial
import logging
from datetime import datetime
from pathlib import Path
import threading
from abc import abstractmethod


class Arduino:
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

    def __init__(
        self,
        device_id: str,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.0,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 1.0,
        **kwargs,
    ):
        """
        Initialize Arduino device.

        Args:
            device_id: Unique identifier for the Arduino
            port: Serial port (e.g., 'COM3' on Windows, '/dev/ttyUSB0' on Linux)
            baudrate: Communication speed (default: 9600)
            timeout: Serial communication timeout in seconds
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 1.0)
            **kwargs: Additional connection parameters
        """
        self.device_id = device_id
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_connected = False
        self.serial_connection: Optional[serial.Serial] = None

        # Housekeeping and threading setup
        self.hk_interval = hk_interval
        self.hk_running = False
        self.hk_stop_event = threading.Event()

        # Determine if using external or internal thread management
        self.external_thread = hk_thread is not None
        self.external_lock = thread_lock is not None

        # Setup thread lock (for serial communication)
        self.thread_lock = thread_lock if thread_lock is not None else threading.Lock()

        # Setup housekeeping lock (separate from communication lock)
        self.hk_lock = threading.Lock()

        # Setup housekeeping thread
        if hk_thread is not None:
            self.hk_thread = hk_thread
        else:
            self.hk_thread = threading.Thread(
                target=self._hk_worker, name=f"HK_{device_id}", daemon=True
            )

        # Setup logger
        if logger is not None:
            self.logger = logger
            self._external_logger_provided = True
        else:
            self._external_logger_provided = False
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"Arduino_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            if not self.logger.handlers:
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent / "debugging" / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                log_filename = f"Arduino_{device_id}_{timestamp}.log"
                log_filepath = logs_dir / log_filename

                file_handler = logging.FileHandler(log_filepath)
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                file_handler.setFormatter(formatter)

                self.logger.addHandler(file_handler)
                self.logger.setLevel(logging.INFO)

                self.logger.info(
                    f"Arduino logger initialized for device '{device_id}' on port '{port}'"
                )

    # =========================================================================
    #     Connection Management
    # =========================================================================

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
            self.stop_housekeeping()

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
            "hk_running": self.hk_running,
            "hk_interval": self.hk_interval,
            "external_thread": self.external_thread,
        }

    # =========================================================================
    #     Logging Helpers
    # =========================================================================

    def enable_file_logging(self) -> bool:
        """
        Enable file logging if not already enabled.

        Returns:
            bool: True if file logging is enabled, False if it failed
        """
        try:
            if self._external_logger_provided:
                self.logger.info("Using external logger - no additional file logging needed")
                return True

            for handler in self.logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    self.logger.info("File logging already enabled")
                    return True

            self.logger.warning("Internal logger missing file handler - this should not happen")
            return False

        except Exception as e:
            self.logger.warning(f"Failed to check file logging: {e}")
            return False

    def custom_logger(self, dev_name: str, port: str, measure: str, value, unit: str):
        """Log a single measurement in a standardised format."""
        return self.logger.info(f"{dev_name}   {port}   {measure}   {value}//{unit}")

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
            str: The line read from Arduino, or None if no data / error
        """
        if not self.is_connected or not self.serial_connection:
            self.logger.warning("Arduino not connected. Call connect() first.")
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
            self.logger.error(f"Error reading from Arduino: {e}")
            return None

    # =========================================================================
    #     Data Parsing (override in subclasses)
    # =========================================================================

    @abstractmethod
    def parse_data(self, data_line: str) -> Optional[Dict[str, Any]]:
        """
        Parse an Arduino CSV data line into a dict.

        Subclasses **must** implement this for their specific data format.

        Args:
            data_line: Raw CSV data line from the Arduino (header already filtered)

        Returns:
            dict with parsed values, or None if parsing fails
        """
        ...

    def read_arduino_data(self) -> Optional[Dict[str, Any]]:
        """
        Read and parse one line of data from the Arduino.

        Returns:
            dict: Parsed data or None if reading/parsing fails
        """
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

        Subclasses implement this to read sensor data and log it using
        ``custom_logger``.
        """
        ...

    def start_housekeeping(self, interval: float = -1, log_to_file: bool = True) -> bool:
        """
        Start housekeeping monitoring.

        - Internal mode (no thread passed to __init__): creates and manages its own thread
        - External mode (thread passed to __init__): enables monitoring for external thread control

        Args:
            interval: Monitoring interval in seconds. <=0 keeps current value.
            log_to_file: Whether to enable file logging (default: True)

        Returns:
            bool: True if started successfully, False otherwise
        """
        if not self.is_connected:
            self.logger.warning("Cannot start housekeeping: device not connected")
            return False

        with self.hk_lock:
            if self.hk_running:
                self.logger.warning("Housekeeping already running")
                return True

            try:
                self.hk_running = True
                if interval > 0:
                    self.hk_interval = interval
                else:
                    interval = self.hk_interval

                self.hk_stop_event.clear()

                if log_to_file:
                    self.enable_file_logging()

                if self.external_thread:
                    self.logger.info(
                        f"Housekeeping enabled (external mode) - interval: {interval}s"
                    )
                    self.logger.info(
                        "Use do_housekeeping_cycle() in your external thread"
                    )
                else:
                    if not self.hk_thread.is_alive():
                        self.hk_thread = threading.Thread(
                            target=self._hk_worker,
                            name=f"HK_{self.device_id}",
                            daemon=True,
                        )
                        self.hk_thread.start()

                    self.logger.info(
                        f"Housekeeping started (internal mode) - interval: {interval}s"
                    )

                return True

            except Exception as e:
                self.logger.error(f"Failed to start housekeeping: {e}")
                self.hk_running = False
                return False

    def stop_housekeeping(self) -> bool:
        """
        Stop housekeeping monitoring.

        Returns:
            bool: True if stopped successfully, False otherwise
        """
        if not self.hk_running:
            return True

        with self.hk_lock:
            try:
                self.hk_running = False
                self.hk_stop_event.set()

                if self.external_thread:
                    self.logger.info("Housekeeping stopped (external mode)")
                else:
                    if self.hk_thread and self.hk_thread.is_alive():
                        self.hk_thread.join(timeout=5.0)
                        if self.hk_thread.is_alive():
                            self.logger.warning(
                                "Housekeeping thread did not stop within timeout"
                            )
                    self.logger.info("Housekeeping stopped (internal mode)")

                return True

            except Exception as e:
                self.logger.error(f"Failed to stop housekeeping: {e}")
                return False

    def _hk_worker(self) -> None:
        """Internal housekeeping worker thread function."""
        self.logger.info(f"Housekeeping worker started for {self.device_id}")

        while not self.hk_stop_event.is_set() and self.hk_running:
            try:
                if self.is_connected:
                    self.hk_monitor()
                else:
                    self.logger.warning("Device disconnected, pausing housekeeping")

                self.hk_stop_event.wait(timeout=self.hk_interval)

            except Exception as e:
                self.logger.error(f"Housekeeping error: {e}")
                self.hk_stop_event.wait(timeout=self.hk_interval)

        self.logger.info(f"Housekeeping worker stopped for {self.device_id}")

    def do_housekeeping_cycle(self) -> bool:
        """
        Perform one housekeeping cycle. Use this in external threads.

        Returns:
            bool: True if cycle completed successfully, False otherwise
        """
        if not self.hk_running:
            return False

        try:
            if self.is_connected:
                self.hk_monitor()
                return True
            else:
                self.logger.warning("Device not connected during housekeeping cycle")
                return False
        except Exception as e:
            self.logger.error(f"Housekeeping cycle error: {e}")
            return False
