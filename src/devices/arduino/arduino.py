"""
Arduino device controller.

This module provides the Arduino class for communicating with Arduino
microcontrollers via serial communication protocols.
"""
# ToDo: Logging into each function
from typing import Any, Dict, Optional
import serial
import logging
from datetime import datetime
from pathlib import Path
import threading
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
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 30.0,  # Housekeeping interval in seconds
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
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 30.0)
            **kwargs: Additional connection parameters
        """
        self.device_id = device_id
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.data_parser = data_parser
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
        if thread_lock is not None:
            self.thread_lock = thread_lock
        else:
            self.thread_lock = threading.Lock()

        # Setup housekeeping lock (separate from communication lock)
        self.hk_lock = threading.Lock()

        # Setup housekeeping thread
        if hk_thread is not None:
            self.hk_thread = hk_thread
            # For external threads, we don't manage the thread lifecycle
        else:
            self.hk_thread = threading.Thread(
                target=self._hk_worker, name=f"HK_{device_id}", daemon=True
            )

        # Setup logger
        if logger is not None:
            self.logger = logger
            self._external_logger_provided = True  # Flag to track external logger
        else:
            self._external_logger_provided = False
            # Create logger with file handler and timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"Arduino_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            # Only add handler if logger doesn't already have one
            if not self.logger.handlers:
                # Create logs directory if it doesn't exist
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent / "debugging" / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                # Create file handler with timestamp
                log_filename = f"Arduino_{device_id}_{timestamp}.log"
                log_filepath = logs_dir / log_filename

                file_handler = logging.FileHandler(log_filepath)
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                file_handler.setFormatter(formatter)

                self.logger.addHandler(file_handler)
                self.logger.setLevel(logging.INFO)

                # Log the initialization
                self.logger.info(
                    f"Arduino logger initialized for device '{device_id}' on port '{port}'"
                )
                self.logger.info(f"Data parser: {data_parser}")

    def enable_file_logging(self) -> bool:
        """
        Enable file logging if not already enabled.
        
        If an external logger was passed to the constructor, this method will not
        create additional file handlers and will use the external logger instead.
        For internal loggers, this method checks if file logging is already enabled.

        Returns:
            bool: True if file logging is enabled, False if it failed
        """
        try:
            # If external logger was provided, don't create additional file handlers
            # The external logger should handle its own file logging
            if self._external_logger_provided:
                self.logger.info("Using external logger - no additional file logging needed")
                return True
            
            # For internal loggers, check if we already have a file handler
            for handler in self.logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    self.logger.info("File logging already enabled")
                    return True
            
            # This should not happen for internal loggers since we create the file handler
            # during initialization, but just in case...
            self.logger.warning("Internal logger missing file handler - this should not happen")
            return False

        except Exception as e:
            self.logger.warning(f"Failed to check file logging: {e}")
            return False

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
            # Stop housekeeping before disconnecting
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
            "data_parser": self.data_parser,
            "hk_running": self.hk_running,
            "hk_interval": self.hk_interval,
            "external_thread": self.external_thread,
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
        pattern = r"Temperature:\s*([\d.]+)\s*°C\s*\|\s*Fan_PWR:\s*(\d+)\s*%\s*\|\s*H2O_FRate:\s*([\d.]+)\s*L/min"
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
            self.logger.warning("Arduino not connected. Call connect() first.")
            return None

        try:
            with self.thread_lock:  # Thread-safe serial communication
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
            self.logger.error(f"Error reading from Arduino: {e}")
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
            self.logger.debug("No data received from Arduino.")
            return None

    def custom_logger(self, dev_name, port, measure, value, unit):
        return self.logger.info(f"{dev_name}   {port}   {measure}   {value}//{unit}")

    def hk_monitor(self):
        """
        Perform housekeeping monitoring of Arduino data.
        This method reads and logs Arduino sensor data based on the configured parser.
        """
        try:
            rtn = self.read_arduino_data()

            if rtn and self.data_parser == "pump_locker":
                # Log parsed data for pump locker
                self.custom_logger(
                    self.device_id, self.port, "Temp", rtn.get("temperature"), "degC"
                )
                self.custom_logger(
                    self.device_id, self.port, "Fan_PWR", rtn.get("fan_power"), "%"
                )
                self.custom_logger(
                    self.device_id,
                    self.port,
                    "H2O_FRate",
                    rtn.get("waterflow"),
                    "L/min",
                )
            elif rtn and self.data_parser == "trafo_locker":
                # Log parsed data for trafo locker
                self.custom_logger(
                    self.device_id, self.port, "Temp", rtn.get("temperature"), "degC"
                )
                self.custom_logger(
                    self.device_id, self.port, "Fan_PWR", rtn.get("fan_power"), "%"
                )
            elif rtn and self.data_parser == "custom":
                # Log raw data for custom parser
                self.custom_logger(
                    self.device_id, self.port, "Raw_Data", rtn.get("raw_data"), ""
                )
            else:
                self.logger.warning("No valid data received or parsing failed.")
                self.custom_logger(
                    self.device_id, self.port, "Error", "Invalid data", ""
                )
        except Exception as e:
            self.logger.error(f"Housekeeping monitoring failed: {e}")

    # =============================================================================
    #     Housekeeping and Threading Methods
    # =============================================================================

    def start_housekeeping(self, interval=-1, log_to_file=True) -> bool:
        """
        Start housekeeping monitoring. Works automatically in both internal and external thread modes.

        - Internal mode (no thread passed to __init__): Creates and manages its own thread
        - External mode (thread passed to __init__): Enables monitoring for external thread control

        Args:
            interval (int): Monitoring interval in seconds (default: 30)
            log_to_file (bool): Whether to enable file logging (default: True)

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

                # Enable file logging if requested
                if log_to_file:
                    self.enable_file_logging()

                if self.external_thread:
                    # External mode: Just enable monitoring, external code controls the thread
                    self.logger.info(
                        f"Housekeeping enabled (external mode) - interval: {interval}s"
                    )
                    self.logger.info(
                        "Use do_housekeeping_cycle() in your external thread"
                    )
                else:
                    # Internal mode: Start our own thread
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
        Stop housekeeping monitoring. Works in both internal and external modes.

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
                    # External mode: Just signal to stop
                    self.logger.info("Housekeeping stopped (external mode)")
                else:
                    # Internal mode: Wait for our thread to finish
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
        """
        Internal housekeeping worker thread function.
        Runs continuously until stop_event is set.
        """
        self.logger.info(f"Housekeeping worker started for {self.device_id}")

        while not self.hk_stop_event.is_set() and self.hk_running:
            try:
                if self.is_connected:
                    self.hk_monitor()
                else:
                    self.logger.warning("Device disconnected, pausing housekeeping")

                # Wait for interval or stop event
                self.hk_stop_event.wait(timeout=self.hk_interval)

            except Exception as e:
                self.logger.error(f"Housekeeping error: {e}")
                # Continue running even after errors
                self.hk_stop_event.wait(timeout=self.hk_interval)

        self.logger.info(f"Housekeeping worker stopped for {self.device_id}")

    def do_housekeeping_cycle(self) -> bool:
        """
        Perform one housekeeping cycle. Use this in external threads.

        This is the main method for external thread control - call it periodically
        in your external thread loop.

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
