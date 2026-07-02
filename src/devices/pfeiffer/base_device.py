"""
Base class for Pfeiffer devices.

This module provides the base class for all Pfeiffer vacuum devices,
implementing the telegram frame protocol on top of ``SerialDeviceBase``
(uniform constructor, canonical logging, telemetry sink, explicit test
mode).
"""
from typing import Any, Dict, Optional
import logging
import threading

from ..serial_device import SerialDeviceBase
from .pfeifferVacuumProtocol import query_data, write_command
from .data_converter import PfeifferDataConverter


class PfeifferBaseDevice(SerialDeviceBase):
    """
    Base class for Pfeiffer vacuum devices.

    This class handles serial communication with Pfeiffer devices using the
    telegram frame protocol. Subclasses implement their parameter maps and
    ``hk_monitor()``; reads must branch on ``self.test_mode`` and return
    simulated values instead of calling ``query_parameter()``.

    Example:
        device = PfeifferBaseDevice("pfeiffer_pump_01", port="COM5", device_address=1)
        device.connect()
        device.start_housekeeping()
        device.disconnect()
    """

    FAMILY = "Pfeiffer"

    def __init__(
        self,
        device_id: str,
        port: str,
        device_address: int = 1,
        baudrate: int = 9600,
        timeout: float = 1.0,
        hk_interval: float = 1.0,
        **kwargs,
    ):
        """
        Initialize Pfeiffer base device (see ``SerialDeviceBase`` for the
        shared parameters ``logger``, ``sink``, ``test_mode``, ``hk_thread``,
        ``thread_lock``).

        Args:
            device_id: Unique identifier for the device.
            port: Serial port (e.g., 'COM5' on Windows, '/dev/ttyUSB0' on Linux).
            device_address: Pfeiffer device address (1-255).
            baudrate: Communication speed (default: 9600).
            timeout: Serial communication timeout in seconds.
            hk_interval: Housekeeping monitoring interval in seconds.
            **kwargs: Shared SerialDeviceBase parameters.
        """
        self.device_address = device_address
        self.data_converter = PfeifferDataConverter()
        super().__init__(
            device_id=device_id,
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            hk_interval=hk_interval,
            **kwargs,
        )

    def query_parameter(self, param_num: int) -> str:
        """
        Query a parameter from the Pfeiffer device.

        Args:
            param_num: Parameter number to query.

        Returns:
            str: Raw response from device.

        Raises:
            RuntimeError: If called in test mode — simulation happens at the
                read-method level, never at the protocol level.
            Exception: If device not connected or communication fails.
        """
        if self.test_mode:
            raise RuntimeError(
                "query_parameter() called in test_mode — simulate in the "
                "read method instead"
            )
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        try:
            with self.thread_lock:  # Thread-safe communication
                return query_data(
                    self.serial_connection, self.device_address, param_num
                )
        except Exception as e:
            self.log_event("error", f"query parameter {param_num} failed: {e}")
            raise

    def write_parameter(self, param_num: int, data_str: str) -> str:
        """
        Write a parameter to the Pfeiffer device.

        Args:
            param_num: Parameter number to write.
            data_str: Data string to write.

        Returns:
            str: Response from device.

        Raises:
            RuntimeError: If called in test mode.
            Exception: If device not connected or communication fails.
        """
        if self.test_mode:
            raise RuntimeError(
                "write_parameter() called in test_mode — guard the calling "
                "method with self.test_mode"
            )
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        try:
            with self.thread_lock:  # Thread-safe communication
                return write_command(
                    self.serial_connection, self.device_address, param_num, data_str
                )
        except Exception as e:
            self.log_event("error", f"write parameter {param_num} failed: {e}")
            raise

    def extra_status(self) -> Dict[str, Any]:
        """Pfeiffer-specific status entries."""
        return {"device_address": self.device_address}
