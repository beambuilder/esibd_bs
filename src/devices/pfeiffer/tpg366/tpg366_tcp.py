"""
TPG366 TCP device controller.

This module provides the TPG366TCP class for communicating with Pfeiffer
TPG366 pressure measurement and control units via TCP/IP (Ethernet)
using the same telegram frame protocol as the serial variant.
"""
from typing import Optional
import logging
import threading
import socket
import time
from datetime import datetime
from pathlib import Path

from ..data_converter import PfeifferDataConverter
from ..pfeifferVacuumProtocol import query_data, write_command


class _TcpSocketWrapper:
    """
    Wraps a TCP socket to expose the same interface as pyserial
    (write, read, reset_input_buffer) so that pfeifferVacuumProtocol
    functions work without modification.
    """

    def __init__(self, sock: socket.socket):
        self._sock = sock

    def write(self, data: bytes) -> int:
        return self._sock.send(data)

    def read(self, size: int = 1) -> bytes:
        try:
            return self._sock.recv(size)
        except socket.timeout:
            return b""

    def reset_input_buffer(self):
        """Drain any pending bytes from the receive buffer."""
        self._sock.setblocking(False)
        try:
            while True:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
        except (BlockingIOError, OSError):
            pass
        finally:
            self._sock.setblocking(True)
            self._sock.settimeout(self._timeout)

    @property
    def _timeout(self):
        return self._sock.gettimeout()

    def close(self):
        self._sock.close()


class TPG366TCP:
    """
    Pfeiffer TPG366 Pressure Measurement and Control Unit Class (TCP/IP).

    Identical functionality to the serial TPG366 class, but communicates
    over Ethernet instead of RS-485/USB serial.

    The TPG366 Ethernet interface exposes a raw TCP socket that accepts
    the same Pfeiffer telegram protocol frames.

    Example:
        gauge = TPG366TCP("tpg366_01", host="192.168.1.100", port=8000, device_address=10)
        gauge.connect()
        pressure = gauge.get_pressure(1)
        gauge.disconnect()
    """

    def __init__(
            self,
            device_id: str,
            host: str,
            port: int = 8000,
            device_address: int = 10,
            timeout: float = 2.0,
            logger: Optional[logging.Logger] = None,
            hk_thread: Optional[threading.Thread] = None,
            thread_lock: Optional[threading.Lock] = None,
            hk_interval: float = 30.0,
            **kwargs,
    ):
        """
        Initialize TPG366 TCP device.

        Args:
            device_id: Unique identifier for the device
            host: IP address or hostname of the TPG366 (e.g., '192.168.1.100')
            port: TCP port number (default: 8000, check TPG366 Ethernet config)
            device_address: Pfeiffer device address (default: 10)
            timeout: Socket timeout in seconds (default: 2.0)
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 30.0)
            **kwargs: Additional parameters
        """
        self.device_id = device_id
        self.host = host
        self.port = port
        self.device_address = device_address
        self.timeout = timeout
        self.is_connected = False
        self._socket: Optional[socket.socket] = None
        self._conn: Optional[_TcpSocketWrapper] = None

        # Initialize data converter
        self.data_converter = PfeifferDataConverter()

        # Housekeeping and threading setup
        self.hk_interval = hk_interval
        self.hk_running = False
        self.hk_stop_event = threading.Event()

        # Determine if using external or internal thread management
        self.external_thread = hk_thread is not None

        # Setup thread lock (for communication)
        if thread_lock is not None:
            self.thread_lock = thread_lock
        else:
            self.thread_lock = threading.Lock()

        # Setup housekeeping lock
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
            logger_name = f"Pfeiffer_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            if not self.logger.handlers:
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent / "debugging" / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                log_filename = f"Pfeiffer_{device_id}_{timestamp}.log"
                log_filepath = logs_dir / log_filename

                file_handler = logging.FileHandler(log_filepath)
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                file_handler.setFormatter(formatter)

                self.logger.addHandler(file_handler)
                self.logger.setLevel(logging.INFO)

                self.logger.info(
                    f"Pfeiffer device logger initialized for device '{device_id}' at {host}:{port}"
                )
                self.logger.info(f"Device address: {device_address}")

    # =============================================================================
    #     Connection Management
    # =============================================================================

    def connect(self) -> bool:
        """
        Establish TCP connection to the TPG366 device.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.logger.info(
                f"Connecting to TPG366 {self.device_id} at {self.host}:{self.port}"
            )
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            self._conn = _TcpSocketWrapper(self._socket)
            self.is_connected = True
            self.logger.info(
                f"Successfully connected to device at address {self.device_address}"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to TPG366 via TCP: {e}")
            self._socket = None
            self._conn = None
            return False

    def disconnect(self) -> bool:
        """
        Close TCP connection to the TPG366 device.

        Returns:
            bool: True if disconnection successful, False otherwise
        """
        try:
            self.stop_housekeeping()

            if self._conn:
                self._conn.close()
            self._socket = None
            self._conn = None
            self.is_connected = False
            self.logger.info(f"Disconnected from TPG366 {self.device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disconnect from TPG366: {e}")
            return False

    def get_status(self):
        return {
            "device_id": self.device_id,
            "host": self.host,
            "port": self.port,
            "device_address": self.device_address,
            "connected": self.is_connected,
            "timeout": self.timeout,
            "hk_running": self.hk_running,
            "hk_interval": self.hk_interval,
            "external_thread": self.external_thread,
        }

    # =============================================================================
    #     Protocol Communication (using TCP socket wrapper)
    # =============================================================================

    def query_parameter(self, param_num: int) -> str:
        if not self.is_connected or not self._conn:
            raise Exception("Device not connected. Call connect() first.")
        try:
            with self.thread_lock:
                return query_data(self._conn, self.device_address, param_num)
        except Exception as e:
            self.logger.error(f"Failed to query parameter {param_num}: {e}")
            raise

    def write_parameter(self, param_num: int, data_str: str) -> str:
        if not self.is_connected or not self._conn:
            raise Exception("Device not connected. Call connect() first.")
        try:
            with self.thread_lock:
                return write_command(self._conn, self.device_address, param_num, data_str)
        except Exception as e:
            self.logger.error(f"Failed to write parameter {param_num}: {e}")
            raise

    def set_parameter(self, param_num: int, data_str: str) -> str:
        """Alias for write_parameter (matches base_device interface)."""
        return self.write_parameter(param_num, data_str)

    def _query_channel_parameter(self, channel: int, param_num: int) -> str:
        if not 1 <= channel <= 6:
            raise ValueError("Channel must be between 1 and 6")
        if not self.is_connected or not self._conn:
            raise Exception("Device not connected. Call connect() first.")

        channel_address = self.device_address + channel
        try:
            with self.thread_lock:
                return query_data(self._conn, channel_address, param_num)
        except Exception as e:
            self.logger.error(f"Failed to query channel {channel} parameter {param_num}: {e}")
            raise

    def _set_channel_parameter(self, channel: int, param_num: int, value: str) -> None:
        if not 1 <= channel <= 6:
            raise ValueError("Channel must be between 1 and 6")
        if not self.is_connected or not self._conn:
            raise Exception("Device not connected. Call connect() first.")

        channel_address = self.device_address + channel
        try:
            with self.thread_lock:
                write_command(self._conn, channel_address, param_num, value)
        except Exception as e:
            self.logger.error(f"Failed to set channel {channel} parameter {param_num}: {e}")
            raise

    # =============================================================================
    #     Logging
    # =============================================================================

    def custom_logger(self, dev_name, port, measure, value, unit):
        return self.logger.info(f"{dev_name}//{port}//{measure}={value}//{unit}")

    def enable_file_logging(self) -> bool:
        if self._external_logger_provided:
            return True
        for handler in self.logger.handlers:
            if isinstance(handler, logging.FileHandler):
                return True
        return False

    # =============================================================================
    #     Device Configuration Methods
    # =============================================================================

    def get_serial_number(self) -> str:
        response = self.query_parameter(355)
        return self.data_converter.string16_2_str(response)

    def get_hardware_version(self) -> str:
        response = self.query_parameter(354)
        return self.data_converter.string_2_str(response)

    def set_rs485_address(self, address: int) -> None:
        if not (10 <= address <= 240) or address % 10 != 0:
            raise ValueError("RS485 address must be between 10-240 and divisible by 10")
        value = self.data_converter.int_2_u_integer(address)
        self.set_parameter(797, value)

    # =============================================================================
    #     Pressure Reading Methods
    # =============================================================================

    def read_pressure_value_channel_1(self) -> float:
        response = self._query_channel_parameter(1, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_2(self) -> float:
        response = self._query_channel_parameter(2, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_3(self) -> float:
        response = self._query_channel_parameter(3, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_4(self) -> float:
        response = self._query_channel_parameter(4, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_5(self) -> float:
        response = self._query_channel_parameter(5, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value_channel_6(self) -> float:
        response = self._query_channel_parameter(6, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def read_pressure_value(self, channel: int) -> float:
        if not 1 <= channel <= 6:
            raise ValueError("Channel must be between 1 and 6")
        response = self._query_channel_parameter(channel, 740)
        return self.data_converter.u_expo_new_2_float(response)

    def get_sensor_error(self, channel: int) -> str:
        response = self._query_channel_parameter(channel, 303)
        return self.data_converter.string_2_str(response)

    # =============================================================================
    #     Base Device Status Methods
    # =============================================================================

    def get_error(self) -> str:
        response = self.query_parameter(303)
        return self.data_converter.string_2_str(response)

    def get_software_version(self) -> str:
        response = self.query_parameter(312)
        return self.data_converter.string_2_str(response)

    def get_electronics_name(self) -> str:
        response = self.query_parameter(349)
        return self.data_converter.string_2_str(response)

    def get_rs485_address(self) -> int:
        response = self.query_parameter(797)
        return self.data_converter.u_integer_2_int(response)

    # =============================================================================
    #     Pressure Threshold Methods
    # =============================================================================

    def get_switch_on_threshold(self, channel: int) -> float:
        response = self._query_channel_parameter(channel, 730)
        return self.data_converter.u_expo_new_2_float(response)

    def set_switch_on_threshold(self, channel: int, threshold: float) -> None:
        if not (1e-5 <= threshold <= 1.0):
            raise ValueError("Switch-on threshold must be between 1E-5 and 1.0 hPa")
        value = self.data_converter.float_2_u_expo_new(threshold)
        self._set_channel_parameter(channel, 730, value)

    def get_switch_off_threshold(self, channel: int) -> float:
        response = self._query_channel_parameter(channel, 732)
        return self.data_converter.u_expo_new_2_float(response)

    def set_switch_off_threshold(self, channel: int, threshold: float) -> None:
        value = self.data_converter.float_2_u_expo_new(threshold)
        self._set_channel_parameter(channel, 732, value)

    def get_correction_factor(self, channel: int) -> float:
        response = self._query_channel_parameter(channel, 742)
        return self.data_converter.u_real_2_float(response)

    def set_correction_factor(self, channel: int, factor: float) -> None:
        if not (0.10 <= factor <= 10.00):
            raise ValueError("Correction factor must be between 0.10 and 10.00")
        value = self.data_converter.float_2_u_real(factor)
        self._set_channel_parameter(channel, 742, value)

    # =============================================================================
    #     Convenience Aliases
    # =============================================================================

    def get_pressure(self, channel: int) -> float:
        return self.read_pressure_value(channel)

    def get_firmware_version(self) -> str:
        return self.get_software_version()

    def get_device_name(self) -> str:
        return self.get_electronics_name()

    # =============================================================================
    #     Multi-Channel Operations
    # =============================================================================

    def read_all_pressures(self) -> dict:
        pressures = {}
        for channel in range(1, 7):
            try:
                pressures[channel] = self.read_pressure_value(channel)
            except Exception as e:
                self.logger.warning(f"Failed to read pressure from channel {channel}: {e}")
                pressures[channel] = None
        return pressures

    def get_all_correction_factors(self) -> dict:
        factors = {}
        for channel in range(1, 7):
            try:
                factors[channel] = self.get_correction_factor(channel)
            except Exception as e:
                self.logger.warning(f"Failed to get correction factor from channel {channel}: {e}")
                factors[channel] = None
        return factors

    def set_all_correction_factors(self, factor: float) -> None:
        for channel in range(1, 7):
            try:
                self.set_correction_factor(channel, factor)
            except Exception as e:
                self.logger.error(f"Failed to set correction factor for channel {channel}: {e}")

    # =============================================================================
    #     Housekeeping
    # =============================================================================

    def hk_monitor(self):
        try:
            a = self.read_all_pressures()
            for ch in range(1, 7):
                self.custom_logger(
                    self.device_id, f"{self.host}:{self.port}",
                    f"Sensor_CH{ch}_Press", a[ch], "hPa"
                )
        except Exception as e:
            self.logger.error(f"Housekeeping monitoring failed: {e}")

    def start_housekeeping(self, interval=-1, log_to_file=True) -> bool:
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
