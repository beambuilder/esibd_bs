"""
Shared base class for all serial (pyserial) device families.

``SerialDeviceBase`` is the pyserial shell over the transport-agnostic
``DeviceBase`` (see ``device_base.py``, where the constructor contract,
logger setup, housekeeping machinery, ``log_sample()`` and the explicit
test mode live). This class adds only what is serial-specific:

- the ``timeout`` constructor parameter (pyserial read timeout)
- ``self.serial_connection`` and the pyserial bodies of the transport
  hooks ``_open_transport()`` / ``_close_transport()``

All serial families (Pfeiffer, Chiller, Arduino, Syringe pump) inherit
this class; import paths are unchanged by the P6.1 hoist.

Canonical log line (aligned columns: device, port, channel, value unit)::

    2026-07-02 14:03:08 INFO   Chiller_A     COM4   Cur_Temp     19.85 degC
    2026-07-02 14:03:09 INFO   [SIM] TPG366  COM3   P_Chamber    2.1e-08 mbar
"""
from typing import Any, Dict, Optional
import logging
import threading

import serial

from .device_base import (
    DeviceBase,
    LOG_RECORD_FORMAT,
    LOG_DATE_FORMAT,
)
from .telemetry import TelemetrySink

__all__ = ["SerialDeviceBase", "LOG_RECORD_FORMAT", "LOG_DATE_FORMAT"]


class SerialDeviceBase(DeviceBase):
    """
    Base class for serial lab devices with housekeeping, logging, telemetry
    and explicit test mode.

    Subclasses implement ``hk_monitor()`` (one housekeeping cycle: read
    every channel and report it via ``log_sample()``) and their device
    protocol on top of ``self.serial_connection``. Reads should branch on
    ``self.test_mode`` and return simulated values (helpers:
    ``_sim_uniform()``, ``_sim_choice()``) instead of touching hardware.

    Example:
        device = Chiller("Chiller_A", port="COM4", sink=sink)
        device.connect()
        device.start_housekeeping()
        ...
        device.disconnect()
    """

    #: Family name used for default logger/file names (subclasses override).
    FAMILY = "SerialDevice"

    def __init__(
        self,
        device_id: str,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.0,
        logger: Optional[logging.Logger] = None,
        sink: Optional[TelemetrySink] = None,
        test_mode: bool = False,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 30.0,
        **kwargs,
    ):
        """
        Initialize a serial device.

        Args:
            device_id: Unique identifier for the device (appears in every log line).
            port: Serial port (e.g. "COM4" on Windows, "/dev/ttyUSB0" on Linux).
            baudrate: Communication baud rate.
            timeout: Serial communication timeout in seconds.
            logger: Optional external logger. If None, creates a timestamped
                file logger in debugging/logs/.
            sink: Optional telemetry sink; one sample per channel per
                housekeeping cycle is written to it.
            test_mode: If True, the device never opens the serial port and
                produces simulated values on the same channels with the same
                log format. Simulated samples carry sim=1 in the sink and a
                [SIM] marker in the log. Never enabled automatically.
            hk_thread: Optional external housekeeping thread. If None, an
                internal thread is created and managed.
            thread_lock: Optional external lock for serial communication.
            hk_interval: Housekeeping interval in seconds.
            **kwargs: Ignored; accepted for forward compatibility.
        """
        self.timeout = timeout
        self.serial_connection: Optional[serial.Serial] = None
        super().__init__(
            device_id,
            port,
            baudrate=baudrate,
            logger=logger,
            sink=sink,
            test_mode=test_mode,
            hk_thread=hk_thread,
            thread_lock=thread_lock,
            hk_interval=hk_interval,
            **kwargs,
        )

    # =========================================================================
    #     Transport hooks (pyserial)
    # =========================================================================

    def _open_transport(self) -> None:
        """Open the physical transport (override for non-pyserial transports)."""
        self.serial_connection = serial.Serial(
            self.port, self.baudrate, timeout=self.timeout
        )

    def _close_transport(self) -> None:
        """Close the physical transport (override for non-pyserial transports)."""
        if self.serial_connection:
            self.serial_connection.close()

    # =========================================================================
    #     Status
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """
        Get current device status (adds the serial ``timeout`` to the
        transport-agnostic status dict).

        Returns:
            Dict[str, Any]: Dictionary containing device status information.
        """
        status = super().get_status()
        status["timeout"] = self.timeout
        return status
