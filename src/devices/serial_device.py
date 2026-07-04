"""
Shared base class for all serial (pyserial) device families.

``SerialDeviceBase`` is the single copy of everything the serial device
classes (Pfeiffer, Chiller, Arduino, Syringe pump) used to duplicate:

- the uniform constructor contract:
  ``device_id, port, baudrate, timeout, logger, sink, test_mode,
  hk_thread, thread_lock, hk_interval``
- logger setup (external logger passed through, otherwise a timestamped
  file logger in ``debugging/logs/``) with one shared line format
- the housekeeping thread machinery (internal or external thread mode)
- ``log_sample()`` — the canonical, aligned, human-readable log line for
  one measurement, which also feeds the optional telemetry sink
- explicit test mode: ``test_mode=True`` swaps in simulated values on the
  same channels with the same log format, marked ``[SIM]`` in the log and
  ``sim=1`` in the sink. Simulation is NEVER entered automatically — a
  failed real connect stays a loud error.

Canonical log line (aligned columns: device, port, channel, value unit)::

    2026-07-02 14:03:08 INFO   Chiller_A     COM4   Cur_Temp     19.85 degC
    2026-07-02 14:03:09 INFO   [SIM] TPG366  COM3   P_Chamber    2.1e-08 mbar
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import logging
import random
import threading
import time

import serial

from .telemetry import TelemetrySink

# One shared log-record format for every device logger (the message itself
# carries device, port and channel in aligned columns).
LOG_RECORD_FORMAT = "%(asctime)s %(levelname)-6s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Column widths of the canonical message layout.
_DEVICE_COL = 13
_PORT_COL = 6
_CHANNEL_COL = 20


class SerialDeviceBase:
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
        self.device_id = device_id
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.sink = sink
        self.test_mode = test_mode
        self.is_connected = False
        self.serial_connection: Optional[serial.Serial] = None
        # Wall-clock time of the last successful measurement (any channel).
        # Stamped by log_sample(); the basis of responding_state() — a port
        # can be open while the device is mute, so "connected" alone lies.
        self.last_sample_ts: Optional[float] = None

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
            self._external_logger_provided = True
        else:
            self._external_logger_provided = False
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"{self.FAMILY}_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            # Only add handler if logger doesn't already have one
            if not self.logger.handlers:
                logs_dir = Path(__file__).parent.parent.parent / "debugging" / "logs"
                logs_dir.mkdir(parents=True, exist_ok=True)

                log_filepath = logs_dir / f"{self.FAMILY}_{device_id}_{timestamp}.log"
                file_handler = logging.FileHandler(log_filepath)
                file_handler.setFormatter(
                    logging.Formatter(LOG_RECORD_FORMAT, datefmt=LOG_DATE_FORMAT)
                )
                self.logger.addHandler(file_handler)
                self.logger.setLevel(logging.INFO)

        mode = "TEST MODE (simulated)" if test_mode else f"{baudrate} baud"
        self.log_event("info", f"initialized ({mode})")

    # =========================================================================
    #     Canonical logging (aligned columns) + telemetry
    # =========================================================================

    def _prefix(self) -> str:
        """Aligned 'device port' columns; [SIM] marks simulated devices."""
        dev = f"[SIM] {self.device_id}" if self.test_mode else self.device_id
        return f"{dev:<{_DEVICE_COL}} {str(self.port):<{_PORT_COL}} "

    def log_sample(self, channel: str, value: Any, unit: str = "", fmt: str = "") -> None:
        """
        Log one measurement in the canonical aligned format and write it to
        the telemetry sink (numeric values only).

        Args:
            channel: Channel name (e.g. "Cur_Temp", "P_Chamber"). Same channel
                logs the same shape on every device.
            value: Measured value (numbers reach the sink; strings log only).
            unit: Physical unit appended after the value (e.g. "degC", "mbar").
            fmt: Optional format spec for numeric values (e.g. ".2f").
                Default formats floats compactly ("g").
        """
        is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if is_number:
            value_str = format(value, fmt) if fmt else format(value, "g")
        else:
            value_str = str(value)
        if is_number or isinstance(value, bool):
            # A measurement made it through the protocol — the device answers.
            self.last_sample_ts = time.time()
        suffix = f" {unit}" if unit else ""
        self.logger.info(f"{self._prefix()}{channel:<{_CHANNEL_COL}} {value_str}{suffix}")

        if self.sink is not None and (is_number or isinstance(value, bool)):
            try:
                self.sink.write(
                    self.device_id, channel, float(value),
                    sim=1 if self.test_mode else 0,
                )
            except Exception as e:
                self.logger.error(f"{self._prefix()}telemetry sink write failed: {e}")

    def log_event(self, level: str, message: str) -> None:
        """
        Log a lifecycle event (connect, disconnect, failure) in the canonical
        format and record it in the sink's events table.

        Args:
            level: "info", "warning" or "error".
            message: Short event text, e.g. "connected", "connect FAILED: ...".
        """
        getattr(self.logger, level, self.logger.info)(f"{self._prefix()}{message}")
        if self.sink is not None:
            try:
                self.sink.write_event(self.device_id, level.upper(), message)
            except Exception as e:
                self.logger.error(f"{self._prefix()}telemetry sink event failed: {e}")

    def custom_logger(self, dev_name: str, port: str, measure: str, value, unit: str):
        """Deprecated: use ``log_sample()``. Kept so old scripts keep working."""
        self.log_sample(measure, value, unit)

    # =========================================================================
    #     Simulation helpers (used by subclasses when self.test_mode is True)
    # =========================================================================

    def _sim_uniform(self, low: float, high: float, decimals: int = 2) -> float:
        """Plausible random value in [low, high], rounded for readable logs."""
        return round(random.uniform(low, high), decimals)

    def _sim_choice(self, options) -> Any:
        """Pick one of several plausible discrete values."""
        return random.choice(options)

    # =========================================================================
    #     Connection
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

    def _transport_desc(self) -> str:
        """Human-readable transport description for the connect log line."""
        return f"{self.baudrate} baud"

    def connect(self) -> bool:
        """
        Open the connection to the device.

        In test mode no hardware is touched and the device reports connected.
        A failed real connect logs an error and returns False — it never
        falls back to simulation.

        Returns:
            bool: True if connection successful, False otherwise.
        """
        if self.is_connected:
            # Idempotent: a supervisor retry racing an API reconnect must
            # not open the (exclusive) port a second time.
            return True
        if self.test_mode:
            self.is_connected = True
            self.log_event("info", "connected (simulated, no hardware)")
            return True
        try:
            self._open_transport()
            self.is_connected = True
            self.log_event("info", f"connected ({self._transport_desc()})")
            return True
        except Exception as e:
            self.is_connected = False
            self.log_event("error", f"connect FAILED: {e}")
            return False

    def disconnect(self) -> bool:
        """
        Stop housekeeping and close the connection.

        Returns:
            bool: True if disconnection successful, False otherwise.
        """
        # Stop housekeeping before disconnecting
        self.stop_housekeeping()
        try:
            if not self.test_mode:
                self._close_transport()
            self.is_connected = False
            self.log_event("info", "disconnected")
            return True
        except Exception as e:
            self.log_event("error", f"disconnect FAILED: {e}")
            return False

    def reconnect(self) -> bool:
        """
        Close and reopen the transport in place (stale-handle recovery after
        a power cycle or USB re-enumeration). Housekeeping is resumed
        afterwards if it was running before.

        The close is best-effort: a dead handle that refuses to close must
        not block the reopen attempt. Returns the result of the reopen.
        """
        was_hk = self.hk_running
        self.log_event("info", "reconnect requested (closing and reopening transport)")
        self.stop_housekeeping()
        with self.thread_lock:
            if not self.test_mode:
                try:
                    self._close_transport()
                except Exception as e:
                    self.log_event("warning", f"close before reconnect failed (continuing): {e}")
            self.is_connected = False
            self.last_sample_ts = None
        ok = self.connect()
        if ok and was_hk:
            self.start_housekeeping()
        return ok

    # =========================================================================
    #     Status
    # =========================================================================

    def responding_state(self) -> Optional[bool]:
        """
        Probe-based liveness, independent of the port-open flag:

        - ``None`` — unknown: not connected, or housekeeping is off (nothing
          is polling the device, so silence proves nothing).
        - ``True`` — a measurement arrived within ~2.5 housekeeping
          intervals (15 s floor).
        - ``False`` — housekeeping polls but no channel has answered
          recently: powered-off electronics, wrong address/baud, or a stale
          USB handle. ``connected`` stays 1 in exactly this case — this
          flag is the difference between "port open" and "device alive".
        """
        if not self.is_connected or not self.hk_running:
            return None
        if self.last_sample_ts is None:
            return False
        age = time.time() - self.last_sample_ts
        return age <= max(2.5 * self.hk_interval, 15.0)

    def get_status(self) -> Dict[str, Any]:
        """
        Get current device status.

        Returns:
            Dict[str, Any]: Dictionary containing device status information.
        """
        status = {
            "device_id": self.device_id,
            "port": self.port,
            "baudrate": self.baudrate,
            "timeout": self.timeout,
            "connected": self.is_connected,
            "responding": self.responding_state(),
            "last_sample_age_s": (
                round(time.time() - self.last_sample_ts, 1)
                if self.last_sample_ts is not None else None
            ),
            "test_mode": self.test_mode,
            "sink": type(self.sink).__name__ if self.sink is not None else None,
            "hk_running": self.hk_running,
            "hk_interval": self.hk_interval,
            "external_thread": self.external_thread,
        }
        status.update(self.extra_status())
        return status

    def extra_status(self) -> Dict[str, Any]:
        """Subclass hook: additional device-specific status entries."""
        return {}

    # =========================================================================
    #     Housekeeping and Threading Methods
    # =========================================================================

    def hk_monitor(self) -> None:
        """
        Perform one housekeeping read-and-log cycle.

        Subclasses override this to read every channel and report it via
        ``log_sample()`` (reads must honor ``self.test_mode``).
        """
        self.log_sample("Status", "Connected" if self.is_connected else "Disconnected")

    def start_housekeeping(self, interval: float = -1, log_to_file: bool = True) -> bool:
        """
        Start housekeeping monitoring. Works in both internal and external
        thread modes.

        - Internal mode (no thread passed to __init__): creates and manages
          its own thread.
        - External mode (thread passed to __init__): enables monitoring for
          external thread control via do_housekeeping_cycle().

        Args:
            interval: Monitoring interval in seconds (default: keep current).
            log_to_file: Kept for backward compatibility (file logging is
                configured in __init__).

        Returns:
            bool: True if started successfully, False otherwise.
        """
        if not self.is_connected:
            self.log_event("warning", "cannot start housekeeping: not connected")
            return False

        with self.hk_lock:
            if self.hk_running:
                self.log_event("warning", "housekeeping already running")
                return True

            try:
                self.hk_running = True
                if interval > 0:
                    self.hk_interval = interval
                else:
                    interval = self.hk_interval

                self.hk_stop_event.clear()

                if self.external_thread:
                    # External mode: external code drives do_housekeeping_cycle()
                    self.log_event(
                        "info",
                        f"housekeeping enabled (external mode, interval {interval}s)",
                    )
                else:
                    # Internal mode: start our own thread
                    if not self.hk_thread.is_alive():
                        self.hk_thread = threading.Thread(
                            target=self._hk_worker,
                            name=f"HK_{self.device_id}",
                            daemon=True,
                        )
                        self.hk_thread.start()
                    self.log_event(
                        "info",
                        f"housekeeping started (internal mode, interval {interval}s)",
                    )
                return True

            except Exception as e:
                self.log_event("error", f"failed to start housekeeping: {e}")
                self.hk_running = False
                return False

    def stop_housekeeping(self) -> bool:
        """
        Stop housekeeping monitoring. Works in both internal and external modes.

        Returns:
            bool: True if stopped successfully, False otherwise.
        """
        if not self.hk_running:
            return True

        with self.hk_lock:
            try:
                self.hk_running = False
                self.hk_stop_event.set()

                if self.external_thread:
                    self.log_event("info", "housekeeping stopped (external mode)")
                else:
                    if self.hk_thread and self.hk_thread.is_alive():
                        self.hk_thread.join(timeout=5.0)
                        if self.hk_thread.is_alive():
                            self.log_event(
                                "warning",
                                "housekeeping thread did not stop within timeout",
                            )
                    self.log_event("info", "housekeeping stopped (internal mode)")
                return True

            except Exception as e:
                self.log_event("error", f"failed to stop housekeeping: {e}")
                return False

    def _hk_worker(self) -> None:
        """Internal housekeeping worker; runs until the stop event is set."""
        self.logger.info(f"{self._prefix()}housekeeping worker started")

        while not self.hk_stop_event.is_set() and self.hk_running:
            try:
                if self.is_connected:
                    self.hk_monitor()
                else:
                    self.log_event("warning", "disconnected, pausing housekeeping")

                # Wait for interval or stop event
                self.hk_stop_event.wait(timeout=self.hk_interval)

            except Exception as e:
                self.log_event("error", f"housekeeping error: {e}")
                # Continue running even after errors
                self.hk_stop_event.wait(timeout=self.hk_interval)

        self.logger.info(f"{self._prefix()}housekeeping worker stopped")

    def do_housekeeping_cycle(self) -> bool:
        """
        Perform one housekeeping cycle. Call this periodically from an
        external thread (external mode).

        Returns:
            bool: True if cycle completed successfully, False otherwise.
        """
        if not self.hk_running:
            return False

        if not self.is_connected:
            self.log_event("warning", "not connected during housekeeping cycle")
            return False

        try:
            self.hk_monitor()
            return True
        except Exception as e:
            self.log_event("error", f"housekeeping cycle error: {e}")
            return False

    def should_continue_housekeeping(self) -> bool:
        """External-thread loop condition: keep cycling while True."""
        return self.hk_running and not self.hk_stop_event.is_set()

    # =========================================================================
    #     Backward compatibility
    # =========================================================================

    def enable_file_logging(self) -> bool:
        """
        Deprecated: file logging is configured in ``__init__``. Kept so old
        callers keep working.

        Returns:
            bool: True if a file handler (or external logger) is active.
        """
        if self._external_logger_provided:
            return True
        return any(
            isinstance(handler, logging.FileHandler)
            for handler in self.logger.handlers
        )

    def __del__(self):
        """Best-effort cleanup: stop the housekeeping thread."""
        try:
            self.stop_housekeeping()
        except Exception:
            pass  # Ignore errors during interpreter shutdown
