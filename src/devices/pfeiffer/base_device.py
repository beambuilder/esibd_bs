"""
Base class for Pfeiffer devices.

This module provides the base class for all Pfeiffer vacuum devices,
implementing common functionality and the telegram frame protocol.
"""
from typing import Any, Dict, Optional
import serial
import logging
from datetime import datetime
from pathlib import Path
import threading
import time

from .pfeifferVacuumProtocol import query_data, write_command
from .data_converter import PfeifferDataConverter


class PfeifferBaseDevice:
    """
    Base class for Pfeiffer vacuum devices.

    This class handles serial communication with Pfeiffer devices using the
    telegram frame protocol, providing methods for device communication,
    logging, and housekeeping functionality.

    Example:
        device = PfeifferBaseDevice("pfeiffer_pump_01", port="COM5", device_address=1)
        device.connect()
        device.start_housekeeping()
        device.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        device_address: int = 1,
        baudrate: int = 9600,
        timeout: float = 1.0,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 30.0,  # Housekeeping interval in seconds
        **kwargs,
    ):
        """
        Initialize Pfeiffer base device.

        Args:
            device_id: Unique identifier for the device
            port: Serial port (e.g., 'COM5' on Windows, '/dev/ttyUSB0' on Linux)
            device_address: Pfeiffer device address (1-255)
            baudrate: Communication speed (default: 9600)
            timeout: Serial communication timeout in seconds
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 30.0)
            **kwargs: Additional connection parameters
        """
        self.device_id = device_id
        self.port = port
        self.device_address = device_address
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_connected = False
        self.serial_connection: Optional[serial.Serial] = None

        # Initialize data converter
        self.data_converter = PfeifferDataConverter()

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
                target=self._hk_worker,
                name=f"HK_{device_id}",
                daemon=True
            )

        # Setup logger
        if logger is not None:
            self.logger = logger
        else:
            # Create logger with file handler and timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"Pfeiffer_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            # Only add handler if logger doesn't already have one
            if not self.logger.handlers:
                # Create logs directory if it doesn't exist
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent / "debugging" / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                # Create file handler with timestamp
                log_filename = f"Pfeiffer_{device_id}_{timestamp}.log"
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
                    f"Pfeiffer device logger initialized for device '{device_id}' on port '{port}'"
                )
                self.logger.info(f"Device address: {device_address}")

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
            log_filename = f"Pfeiffer_{self.device_id}_HK_{timestamp}.log"
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
        Establish serial connection to the Pfeiffer device.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.logger.info(f"Connecting to Pfeiffer device {self.device_id} on {self.port}")
            self.serial_connection = serial.Serial(
                self.port, self.baudrate, timeout=self.timeout
            )
            self.is_connected = True
            self.logger.info(f"Successfully connected to device at address {self.device_address}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Pfeiffer device: {e}")
            return False

    def disconnect(self) -> bool:
        """
        Close serial connection to the Pfeiffer device.

        Returns:
            bool: True if disconnection successful, False otherwise
        """
        try:
            # Stop housekeeping before disconnecting
            self.stop_housekeeping()
            
            if self.serial_connection:
                self.serial_connection.close()
            self.is_connected = False
            self.logger.info(f"Disconnected from Pfeiffer device {self.device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disconnect from Pfeiffer device: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Get current device status.

        Returns:
            Dict[str, Any]: Dictionary containing device status information
        """
        return {
            "device_id": self.device_id,
            "port": self.port,
            "device_address": self.device_address,
            "baudrate": self.baudrate,
            "connected": self.is_connected,
            "timeout": self.timeout,
            "hk_running": self.hk_running,
            "hk_interval": self.hk_interval,
            "external_thread": self.external_thread,
        }

    def query_parameter(self, param_num: int) -> str:
        """
        Query a parameter from the Pfeiffer device.

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
                return query_data(self.serial_connection, self.device_address, param_num)
        except Exception as e:
            self.logger.error(f"Failed to query parameter {param_num}: {e}")
            raise

    def write_parameter(self, param_num: int, data_str: str) -> str:
        """
        Write a parameter to the Pfeiffer device.

        Args:
            param_num: Parameter number to write
            data_str: Data string to write

        Returns:
            str: Response from device

        Raises:
            Exception: If device not connected or communication fails
        """
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        try:
            with self.thread_lock:  # Thread-safe communication
                return write_command(self.serial_connection, self.device_address, param_num, data_str)
        except Exception as e:
            self.logger.error(f"Failed to write parameter {param_num}: {e}")
            raise

    def custom_logger(self, dev_name, port, measure, value, unit):
        """Custom logging format for device measurements."""
        return self.logger.info(f"{dev_name}   {port}   {measure}   {value}//{unit}")

    def hk_monitor(self):
        """
        Perform housekeeping monitoring of device data.
        This method should be overridden by derived classes.
        """
        try:
            # Base implementation - log basic status
            status = self.get_status()
            self.custom_logger(
                self.device_id, self.port, "Status", "Connected" if self.is_connected else "Disconnected", ""
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
                    self.logger.info(f"Housekeeping enabled (external mode) - interval: {interval}s")
                    self.logger.info("Use do_housekeeping_cycle() in your external thread")
                else:
                    # Internal mode: Start our own thread
                    if not self.hk_thread.is_alive():
                        self.hk_thread = threading.Thread(
                            target=self._hk_worker,
                            name=f"HK_{self.device_id}",
                            daemon=True
                        )
                        self.hk_thread.start()
                    
                    self.logger.info(f"Housekeeping started (internal mode) - interval: {interval}s")
                
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
                            self.logger.warning("Housekeeping thread did not stop within timeout")
                    
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
