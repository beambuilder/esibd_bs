"""
Chiller device controller.

This module provides the Chiller class for communicating with temperature
control and chilling systems via various communication protocols.
"""
# ToDo: Logging into each function
from typing import Any, Dict, Optional
import logging
from datetime import datetime
from pathlib import Path
import threading
import time

import serial


class ChillerCommands:
    """Constants for Lauda chiller communication commands."""

    # Read commands
    READ_TEMP = "IN_PV_00\r\n"
    READ_SET_TEMP = "IN_SP_00\r\n"
    READ_PUMP_LEVEL = "IN_SP_01\r\n"
    READ_COOLING_MODE = "IN_SP_02\r\n"
    READ_KEYLOCK = "IN_MODE_00\r\n"
    READ_RUNNING_STATE = "IN_MODE_02\r\n"
    READ_STATUS = "STATUS\r\n"
    READ_DIAGNOSTICS = "STAT\r\n"

    # Write commands
    SET_TEMP = "OUT_SP_00"
    SET_PUMP_LEVEL = "OUT_SP_01"
    SET_KEYLOCK = "OUT_MODE_00"
    START_DEVICE = "START"
    STOP_DEVICE = "STOP"


class Chiller:
    """
    Chiller (Lauda) device communication class.

    This class handles communication with chiller devices, providing
    methods for temperature control, monitoring, and system management.

    Example:
        chiller = Chiller("main_chiller", port="COM4")
        chiller.connect()
        chiller.set_temperature(20.0)
        temp = chiller.read_temp()
        chiller.disconnect()
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
        hk_interval: float = 30.0,  # Housekeeping interval in seconds
        **kwargs,
    ):
        """
        Initialize Chiller device.

        Args:
            device_id: Unique identifier for the chiller
            port: Serial port (e.g., "COM4" on Windows, "/dev/ttyUSB0" on Linux)
            baudrate: Communication baud rate (default: 9600)
            timeout: Serial communication timeout in seconds (default: 1.0)
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 30.0)
            **kwargs: Additional keyword arguments for future extensibility
        """
        self.device_id = device_id
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_connected = False
        self.serial_connection: Optional[serial.Serial] = None
        self.current_temperature: Optional[float] = None
        self.target_temperature: Optional[float] = None
        self.is_cooling: bool = False

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
        else:
            # Create logger with file handler and timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"Chiller_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            # Only add handler if logger doesn't already have one
            if not self.logger.handlers:
                # Create logs directory if it doesn't exist
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent / "debugging" / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                # Create file handler with timestamp
                log_filename = f"Chiller_{device_id}_{timestamp}.log"
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
                    f"Chiller logger initialized for device '{device_id}' on port '{port}'"
                )
                if self.external_thread:
                    self.logger.info(
                        f"Using external thread: {self.hk_thread.name if hasattr(self.hk_thread, 'name') else 'unnamed'}"
                    )
                else:
                    self.logger.info(f"Using internal thread: {self.hk_thread.name}")

                if self.external_lock:
                    self.logger.info("Using external thread lock")
                else:
                    self.logger.info("Using internal thread lock")

    def enable_file_logging(self) -> bool:
        """
        Enable file logging if not already enabled.

        Returns:
            bool: True if file logging is enabled, False if it failed
        """
        try:
            # Check if we already have a file handler
            for handler in self.logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    self.logger.info("File logging already enabled")
                    return True

            # Create logs directory if it doesn't exist
            logs_dir = Path(__file__).parent.parent.parent.parent / "debugging" / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)

            # Create new file handler with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"Chiller_{self.device_id}_HK_{timestamp}.log"
            log_filepath = logs_dir / log_filename

            file_handler = logging.FileHandler(log_filepath)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            file_handler.setFormatter(formatter)

            self.logger.addHandler(file_handler)
            self.logger.info(f"File logging enabled: {log_filepath}")
            return True

        except Exception as e:
            self.logger.warning(f"Failed to enable file logging: {e}")
            return False

    def connect(self) -> bool:
        """
        Establish connection to the chiller.

        Returns:
            bool: True if connection successful, False otherwise
        """
        with self.thread_lock:
            try:
                self.logger.info(
                    f"Connecting to chiller {self.device_id} on {self.port}"
                )
                self.serial_connection = serial.Serial(
                    self.port, self.baudrate, timeout=self.timeout
                )
                self.is_connected = True
                return True
            except Exception as e:
                self.logger.error(f"Failed to connect to chiller: {e}")
                return False

    def disconnect(self) -> bool:
        """
        Disconnect from the chiller.

        Returns:
            bool: True if disconnection successful, False otherwise
        """
        # Stop housekeeping first
        self.stop_housekeeping()

        with self.thread_lock:
            try:
                if self.serial_connection:
                    self.serial_connection.close()
                self.is_connected = False
                self.logger.info(f"Disconnected from chiller {self.device_id}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to disconnect from chiller: {e}")
                return False

    def read_dev(self, command: str) -> str:
        """
        Send a command to read a parameter and parse the response.

        Args:
            command: Command string to send to the device

        Returns:
            str: Response from the device

        Raises:
            Exception: If serial connection is not open
            ValueError: If response format is invalid
        """
        with self.thread_lock:
            if not self.serial_connection or not self.serial_connection.is_open:
                raise Exception("Serial connection not open")

            self.serial_connection.write(command.encode("ascii"))
            response = self.serial_connection.readline().decode("ascii").strip()

            try:
                return response
            except ValueError:
                raise ValueError(f"Invalid response: {response}")

    def set_param(self, param: str) -> None:
        """
        Set a parameter on the device.

        Args:
            param: Parameter command string to send

        Raises:
            Exception: If serial connection is not open or command fails
        """
        with self.thread_lock:
            if not self.serial_connection or not self.serial_connection.is_open:
                raise Exception("Serial connection not open")

            command = f"{param}\r\n"
            self.serial_connection.write(command.encode("ascii"))
            response = self.serial_connection.readline().decode("ascii").strip()

            if response != "OK":
                raise Exception(
                    f"Failed to set parameter {param}. Response: {response}"
                )

    # =============================================================================
    #     Read device parameters
    # =============================================================================

    def read_temp(self) -> float:
        """
        Read the current bath temperature.

        Returns:
            float: Current bath temperature in degrees Celsius
        """
        return float(self.read_dev(ChillerCommands.READ_TEMP))

    def read_set_temp(self) -> float:
        """
        Read the current set temperature.

        Returns:
            float: Current set temperature in degrees Celsius
        """
        return float(self.read_dev(ChillerCommands.READ_SET_TEMP))

    def read_pump_level(self) -> int:
        """
        Read the current pump level (1-6).

        Returns:
            int: Current pump level (1-6)
        """
        return int(float(self.read_dev(ChillerCommands.READ_PUMP_LEVEL)))

    def read_cooling(self) -> Optional[str]:
        """
        Read the cooling mode.

        Returns:
            Optional[str]: Cooling mode ("OFF", "ON", "AUTO") or None if invalid
        """
        response = int(float(self.read_dev(ChillerCommands.READ_COOLING_MODE)))

        cooling_modes = {0: "OFF", 1: "ON", 2: "AUTO"}
        return cooling_modes.get(response)

    def read_keylock(self) -> Optional[str]:
        """
        Read the keylock indicator.

        Returns:
            Optional[str]: Keylock status ("FREE", "LOCKED") or None if invalid
        """
        response = int(float(self.read_dev(ChillerCommands.READ_KEYLOCK)))

        keylock_states = {0: "FREE", 1: "LOCKED"}
        return keylock_states.get(response)

    def read_running(self) -> Optional[str]:
        """
        Read the device running status.

        Returns:
            Optional[str]: Running status ("DEVICE RUNNING", "DEVICE STANDBY") or None if invalid
        """
        response = int(float(self.read_dev(ChillerCommands.READ_RUNNING_STATE)))

        running_states = {0: "DEVICE RUNNING", 1: "DEVICE STANDBY"}
        return running_states.get(response)

    def read_status(self) -> Optional[str]:
        """
        Read the device status.

        Returns:
            Optional[str]: Device status ("OK", "ERROR") or None if invalid

        Note:
            See instruction manual p.111 for detailed status codes
        """
        response = int(float(self.read_dev(ChillerCommands.READ_STATUS)))

        status_codes = {0: "OK", 1: "ERROR"}
        return status_codes.get(response)

    def read_stat_diagnose(self) -> str:
        """
        Read the status diagnostic information.

        Returns:
            str: Diagnostic status information
        """
        return self.read_dev(ChillerCommands.READ_DIAGNOSTICS)

    # =============================================================================
    #     Write Device
    # =============================================================================

    def set_temperature(self, target_temp: float) -> None:
        """
        Set the target (setpoint) temperature.

        Args:
            target_temp: Target temperature in degrees Celsius (e.g., 23.5)
        """
        # Format temperature to 6-character fixed-point with 2 decimals, leading zeros
        temp_str = f"{target_temp:06.2f}"
        command = f"{ChillerCommands.SET_TEMP} {temp_str}"
        self.set_param(command)

    def set_pump_level(self, level: int) -> None:
        """
        Set the pump level (1-6).

        Args:
            level: Pump level (1-6)

        Raises:
            ValueError: If level is not in valid range
        """
        if not 1 <= level <= 6:
            raise ValueError(f"Pump level must be between 1 and 6, got {level}")

        # Format level to 3-character fixed-point with 0 decimals, leading zeros
        level_str = f"{level:03d}"
        command = f"{ChillerCommands.SET_PUMP_LEVEL} {level_str}"
        self.set_param(command)

    def set_keylock(self, locked: bool) -> None:
        """
        Set the keylock state.

        Args:
            locked: True to lock keys, False to unlock
        """
        command = f"{ChillerCommands.SET_KEYLOCK} {int(locked)}"
        self.set_param(command)

    def start_device(self) -> None:
        """
        Start pumping and cooling.
        """
        self.set_param(ChillerCommands.START_DEVICE)

    def stop_device(self) -> None:
        """
        Stop pumping and cooling.
        """
        self.set_param(ChillerCommands.STOP_DEVICE)

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

                    self.logger.info(f"Housekeeping stopped (internal mode)")

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

        if not self.is_connected:
            self.logger.warning("Device not connected - skipping housekeeping")
            return False

        try:
            self.hk_monitor()  # This method is already thread-safe
            return True
        except Exception as e:
            self.logger.error(f"Housekeeping cycle failed: {e}")
            return False

    def should_continue_housekeeping(self) -> bool:
        """
        Check if housekeeping should continue. Use this in external thread loops.

        Returns:
            bool: True if housekeeping should continue, False if it should stop
        """
        return self.hk_running and not self.hk_stop_event.is_set()

    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive device status information.

        Returns:
            Dict[str, Any]: Dictionary containing device status information
        """
        return {
            "device_id": self.device_id,
            "port": self.port,
            "baudrate": self.baudrate,
            "connected": self.is_connected,
            "timeout": self.timeout,
            "current_temperature": self.current_temperature,
            "target_temperature": self.target_temperature,
            "is_cooling": self.is_cooling,
            "housekeeping_running": self.hk_running,
            "housekeeping_interval": self.hk_interval,
            "thread_name": self.hk_thread.name if self.hk_thread else None,
        }

    def custom_logger(self, dev_name, port, measure, value, unit):
        return self.logger.info(f"{dev_name}   {port}   {measure}   {value}//{unit}")

    def hk_monitor(self):
        """
        Perform housekeeping monitoring of all device parameters.
        This method is thread-safe and can be called from the housekeeping thread
        or manually from the main thread.
        """
        try:
            # Each read operation already uses thread_lock via read_dev
            self.custom_logger(
                self.device_id, self.port, "Cur_Temp", self.read_temp(), "degC"
            )
            self.custom_logger(
                self.device_id,
                self.port,
                "Set_Temp",
                self.read_set_temp(),
                "degC",  # Fixed bug: was read_temp()
            )
            self.custom_logger(
                self.device_id, self.port, "Run_Stat", self.read_running(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Dev_Stat", self.read_status(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Pump_Lvl", self.read_pump_level(), ""
            )
            self.custom_logger(
                self.device_id, self.port, "Col_Stat", self.read_cooling(), ""
            )
        except Exception as e:
            self.logger.error(f"Housekeeping monitoring failed: {e}")

    def __del__(self):
        """Cleanup method to ensure housekeeping thread is stopped."""
        try:
            self.stop_housekeeping()
        except:
            pass  # Ignore errors during cleanup
