"""
Chiller device controller.

This module provides the Chiller class for communicating with Lauda
recirculating chillers over serial, built on ``SerialDeviceBase`` (uniform
constructor, canonical logging, telemetry sink, explicit test mode).
"""
import math
from typing import Any, Dict, Optional

from ..serial_device import SerialDeviceBase


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


class Chiller(SerialDeviceBase):
    """
    Chiller (Lauda) device communication class.

    This class handles communication with chiller devices, providing
    methods for temperature control, monitoring, and system management.

    Example:
        chiller = Chiller("Chiller_A", port="COM4")
        chiller.connect()
        chiller.set_temperature(20.0)
        temp = chiller.read_temp()
        chiller.disconnect()
    """

    FAMILY = "Chiller"

    #: Consecutive failed housekeeping cycles before the serial port is
    #: closed and reopened in place (and again at every further multiple
    #: while the failure persists).
    AUTO_RECONNECT_AFTER = 3

    def __init__(
        self,
        device_id: str,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.0,
        hk_interval: float = 30.0,
        **kwargs,
    ):
        """
        Initialize Chiller device (see ``SerialDeviceBase`` for the shared
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
        self.current_temperature: Optional[float] = None
        self.target_temperature: Optional[float] = None
        self._hk_fail_count = 0
        # Simulated setpoint/pump level so test mode behaves consistently
        # across calls (set → read roundtrips work without hardware).
        self._sim_set_temp = 20.0
        self._sim_pump_level = 3
        self._sim_running = True

    # =========================================================================
    #     Serial I/O
    # =========================================================================

    def read_dev(self, command: str) -> str:
        """
        Send a command to read a parameter and return the raw response.

        Args:
            command: Command string to send to the device.

        Returns:
            str: Response from the device.

        Raises:
            Exception: If serial connection is not open.
        """
        with self.thread_lock:
            if not self.serial_connection or not self.serial_connection.is_open:
                raise Exception("Serial connection not open")

            self.serial_connection.write(command.encode("ascii"))
            return self.serial_connection.readline().decode("ascii").strip()

    def set_param(self, param: str) -> None:
        """
        Set a parameter on the device.

        Args:
            param: Parameter command string to send.

        Raises:
            Exception: If serial connection is not open or command fails.
        """
        if self.test_mode:
            self.log_event("info", f"set_param '{param}' (simulated)")
            return

        with self.thread_lock:
            if not self.serial_connection or not self.serial_connection.is_open:
                raise Exception("Serial connection not open")

            command = f"{param}\r\n"
            self.serial_connection.write(command.encode("ascii"))
            response = self.serial_connection.readline().decode("ascii").strip()

            if response != "OK":
                raise Exception(f"Failed to set parameter {param}. Response: {response}")

    # =========================================================================
    #     Read device parameters
    # =========================================================================

    def read_temp(self) -> float:
        """
        Read the current bath temperature.

        Returns:
            float: Current bath temperature in degrees Celsius.
        """
        if self.test_mode:
            return self._sim_uniform(self._sim_set_temp - 0.5, self._sim_set_temp + 0.5)
        return float(self.read_dev(ChillerCommands.READ_TEMP))

    def read_set_temp(self) -> float:
        """
        Read the current set temperature.

        Returns:
            float: Current set temperature in degrees Celsius.
        """
        if self.test_mode:
            return self._sim_set_temp
        return float(self.read_dev(ChillerCommands.READ_SET_TEMP))

    def read_pump_level(self) -> int:
        """
        Read the current pump level (1-6).

        Returns:
            int: Current pump level (1-6).
        """
        if self.test_mode:
            return self._sim_pump_level
        return int(float(self.read_dev(ChillerCommands.READ_PUMP_LEVEL)))

    def read_cooling(self) -> Optional[str]:
        """
        Read the cooling mode.

        Returns:
            Optional[str]: Cooling mode ("OFF", "ON", "AUTO") or None if invalid.
        """
        if self.test_mode:
            return "AUTO"
        response = int(float(self.read_dev(ChillerCommands.READ_COOLING_MODE)))
        cooling_modes = {0: "OFF", 1: "ON", 2: "AUTO"}
        return cooling_modes.get(response)

    def read_keylock(self) -> Optional[str]:
        """
        Read the keylock indicator.

        Returns:
            Optional[str]: Keylock status ("FREE", "LOCKED") or None if invalid.
        """
        if self.test_mode:
            return "FREE"
        response = int(float(self.read_dev(ChillerCommands.READ_KEYLOCK)))
        keylock_states = {0: "FREE", 1: "LOCKED"}
        return keylock_states.get(response)

    def read_running(self) -> Optional[str]:
        """
        Read the device running status.

        Returns:
            Optional[str]: "DEVICE RUNNING" / "DEVICE STANDBY" or None if invalid.
        """
        if self.test_mode:
            return "DEVICE RUNNING" if self._sim_running else "DEVICE STANDBY"
        response = int(float(self.read_dev(ChillerCommands.READ_RUNNING_STATE)))
        running_states = {0: "DEVICE RUNNING", 1: "DEVICE STANDBY"}
        return running_states.get(response)

    def read_status(self) -> Optional[str]:
        """
        Read the device status.

        Returns:
            Optional[str]: Device status ("OK", "ERROR") or None if invalid.

        Note:
            See instruction manual p.111 for detailed status codes.
        """
        if self.test_mode:
            return "OK"
        response = int(float(self.read_dev(ChillerCommands.READ_STATUS)))
        status_codes = {0: "OK", 1: "ERROR"}
        return status_codes.get(response)

    def read_stat_diagnose(self) -> str:
        """
        Read the status diagnostic information.

        Returns:
            str: Diagnostic status information.
        """
        if self.test_mode:
            return "0000000"
        return self.read_dev(ChillerCommands.READ_DIAGNOSTICS)

    # =========================================================================
    #     Write Device
    # =========================================================================

    def set_temperature(self, target_temp: float) -> None:
        """
        Set the target (setpoint) temperature.

        Args:
            target_temp: Target temperature in degrees Celsius (e.g., 23.5).

        Raises:
            ValueError: If target_temp is NaN or infinite.
        """
        if not math.isfinite(target_temp):
            raise ValueError(f"Set temperature must be finite, got {target_temp}")
        # Format temperature to 6-character fixed-point with 2 decimals, leading zeros
        temp_str = f"{target_temp:06.2f}"
        command = f"{ChillerCommands.SET_TEMP} {temp_str}"
        self.set_param(command)
        self.target_temperature = target_temp
        if self.test_mode:
            self._sim_set_temp = target_temp
        self.log_event("info", f"setpoint changed to {target_temp:.2f} degC")

    def set_pump_level(self, level: int) -> None:
        """
        Set the pump level (1-6).

        Args:
            level: Pump level (1-6).

        Raises:
            ValueError: If level is not in valid range.
        """
        if not 1 <= level <= 6:
            raise ValueError(f"Pump level must be between 1 and 6, got {level}")

        # Format level to 3-character fixed-point with 0 decimals, leading zeros
        level_str = f"{level:03d}"
        command = f"{ChillerCommands.SET_PUMP_LEVEL} {level_str}"
        self.set_param(command)
        if self.test_mode:
            self._sim_pump_level = level
        self.log_event("info", f"pump level changed to {level}")

    def set_keylock(self, locked: bool) -> None:
        """
        Set the keylock state.

        Args:
            locked: True to lock keys, False to unlock.
        """
        command = f"{ChillerCommands.SET_KEYLOCK} {int(locked)}"
        self.set_param(command)
        self.log_event("info", f"keylock {'engaged' if locked else 'released'}")

    def start_device(self) -> None:
        """Start pumping and cooling."""
        self.set_param(ChillerCommands.START_DEVICE)
        if self.test_mode:
            self._sim_running = True
        self.log_event("info", "device started (pumping + cooling)")

    def stop_device(self) -> None:
        """Stop pumping and cooling."""
        self.set_param(ChillerCommands.STOP_DEVICE)
        if self.test_mode:
            self._sim_running = False
        self.log_event("info", "device stopped")

    # =========================================================================
    #     Housekeeping
    # =========================================================================

    def hk_monitor(self) -> None:
        """One housekeeping cycle: read and report every chiller channel."""
        try:
            self.current_temperature = self.read_temp()
            self.log_sample("Cur_Temp", self.current_temperature, "degC", fmt=".2f")
            self.target_temperature = self.read_set_temp()
            self.log_sample("Set_Temp", self.target_temperature, "degC", fmt=".2f")
            running = self.read_running()
            self.log_sample("Run_Stat", running)
            if running is not None:
                # Numeric twin of Run_Stat: strings never reach the telemetry
                # sink, but the dashboard's run/standby switch needs a channel.
                self.log_sample("Running", 1 if running == "DEVICE RUNNING" else 0)
            self.log_sample("Dev_Stat", self.read_status())
            self.log_sample("Pump_Lvl", self.read_pump_level())
            self.log_sample("Col_Stat", self.read_cooling())
            if self._hk_fail_count:
                self.log_event(
                    "info",
                    f"housekeeping recovered after {self._hk_fail_count} failed cycle(s)",
                )
                self._hk_fail_count = 0
        except Exception as e:
            self._hk_fail_count += 1
            self.log_event(
                "error",
                f"housekeeping read failed ({self._hk_fail_count} consecutive): {e}",
            )
            if (
                not self.test_mode
                and self._hk_fail_count % self.AUTO_RECONNECT_AFTER == 0
            ):
                self._auto_reconnect()

    def _auto_reconnect(self) -> None:
        """
        Close and reopen the serial port in place after consecutive
        housekeeping failures.

        The 2026-07-14 forensic run (notebook 031) showed the chillers drop
        off the USB bus and re-enumerate; the stale handle then fails every
        call with WinError 22 until the port is closed and reopened. Runs on
        the housekeeping thread, so it must not call reconnect() — that
        joins the housekeeping thread. ``is_connected`` stays True even on a
        failed reopen so housekeeping keeps cycling and the reopen is
        retried every ``AUTO_RECONNECT_AFTER`` failures.
        """
        self.log_event(
            "warning",
            f"auto-reconnect after {self._hk_fail_count} failed housekeeping "
            f"cycle(s): closing and reopening {self.port}",
        )
        with self.thread_lock:
            try:
                self._close_transport()
            except Exception as e:
                self.log_event(
                    "warning", f"auto-reconnect: close failed (continuing): {e}"
                )
            try:
                self._open_transport()
            except Exception as e:
                self.log_event("error", f"auto-reconnect: reopen FAILED (will retry): {e}")
                return
        self.log_event("info", "auto-reconnect: port reopened")

    def extra_status(self) -> Dict[str, Any]:
        """Chiller-specific status entries."""
        return {
            "current_temperature": self.current_temperature,
            "target_temperature": self.target_temperature,
            "hk_consecutive_failures": self._hk_fail_count,
        }
