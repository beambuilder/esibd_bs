"""
Syringe pump device controller.

This module provides the SyringePump class for communicating with syringe
pump devices over serial for precise fluid control, built on
``SerialDeviceBase`` (uniform constructor, canonical logging, telemetry
sink, explicit test mode).
"""

from typing import Any, Dict
import glob
import sys
import time

import serial

from ..serial_device import SerialDeviceBase


class SyringePump(SerialDeviceBase):
    """
    Syringe pump device communication class.

    This class handles communication with syringe pump devices, providing
    methods for precise fluid control, flow rate management, and volume
    dispensing.

    Example:
        pump = SyringePump("main_pump", port="COM5")
        pump.connect()
        pump.set_rate(10.0)
        pump.start_pump()
        pump.disconnect()
    """

    FAMILY = "SyringePump"

    def __init__(
        self,
        device_id: str,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.0,
        x: int = 0,
        mode: int = 0,
        hk_interval: float = 30.0,
        **kwargs,
    ):
        """
        Initialize Syringe Pump device (see ``SerialDeviceBase`` for the
        shared parameters ``logger``, ``sink``, ``test_mode``, ``hk_thread``,
        ``thread_lock``).

        Args:
            device_id: Unique identifier for the syringe pump.
            port: Serial port (e.g., "COM5" on Windows, "/dev/ttyUSB0" on Linux).
            baudrate: Communication baud rate (default: 9600).
            timeout: Serial communication timeout in seconds (default: 1.0).
            x: Pump channel/axis identifier (default: 0, no prefix).
            mode: Pump operation mode (default: 0, no mode suffix).
            hk_interval: Housekeeping monitoring interval in seconds.
            **kwargs: Shared SerialDeviceBase parameters.
        """
        super().__init__(
            device_id=device_id,
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            hk_interval=hk_interval,
            **kwargs,
        )
        self.x = x
        self.mode = mode

        # 1 mL syringe defaults
        self.volume = 1.0
        self.diameter = 4.64
        self.units = "mL/hr"
        self.pump_rate = 120.0
        self.withdraw_rate = 120.0

        # Simulated pump state so test mode behaves consistently across calls.
        self._sim_running = False

    def _open_transport(self) -> None:
        super()._open_transport()
        self._flush_buffers()

    def _flush_buffers(self):
        """Flush input and output buffers."""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()

    # =========================================================================
    #     Serial I/O
    # =========================================================================

    def _send_command(self, command: str) -> list:
        """
        Send command to syringe pump and get response.

        Args:
            command: Command string to send.

        Returns:
            list: Response from pump as list of strings.
        """
        if self.test_mode:
            self.logger.debug(f"Command (simulated): {command}")
            return []

        if not self.is_connected or not self.serial_connection:
            self.log_event("error", "no active connection")
            return []

        try:
            with self.thread_lock:
                # Send command with carriage return
                arg = bytes(str(command), "utf8") + b"\r"
                self.serial_connection.write(arg)
                time.sleep(0.05)  # Wait for response

                response = self._get_response()
                self.logger.debug(f"Command: {command}, Response: {response}")
                return response

        except Exception as e:
            self.log_event("error", f"command '{command}' failed: {e}")
            return []

    def _get_response(self) -> list:
        """
        Read response from syringe pump.

        Returns:
            list: Response lines as list of strings.
        """
        try:
            response_list = []
            response = self.serial_connection.readlines()
            for line in response:
                line = line.strip(b"\n").decode("utf8")
                line = line.strip("\r")
                if line:  # Only add non-empty lines
                    response_list.append(line)
            return response_list

        except Exception as e:
            self.log_event("error", f"failed to get response: {e}")
            return []

    def _add_mode(self, command: str) -> str:
        """Add mode suffix to command if mode is set."""
        if self.mode == 0:
            return command
        else:
            return command + " " + str(self.mode - 1)

    def _add_x(self, command: str) -> str:
        """Add pump channel/axis prefix to command if x is set."""
        if self.x == 0:
            return command
        else:
            return str(self.x) + " " + command

    # =========================================================================
    #     Pump Control
    # =========================================================================

    def start_pump(self) -> list:
        """
        Start the syringe pump.

        Returns:
            list: Response from pump.
        """
        command = "start"
        command = self._add_x(command)
        command = self._add_mode(command)
        response = self._send_command(command)
        self._sim_running = True
        self.log_event("info", "pump started")
        return response

    def stop_pump(self) -> list:
        """
        Stop the syringe pump.

        Returns:
            list: Response from pump.
        """
        command = "stop"
        command = self._add_x(command)
        response = self._send_command(command)
        self._sim_running = False
        self.log_event("info", "pump stopped")
        return response

    def pause_pump(self) -> list:
        """
        Pause the syringe pump.

        Returns:
            list: Response from pump.
        """
        command = "pause"
        command = self._add_x(command)
        response = self._send_command(command)
        self._sim_running = False
        self.log_event("info", "pump paused")
        return response

    def restart_pump(self) -> list:
        """
        Restart the syringe pump.

        Returns:
            list: Response from pump.
        """
        command = "restart"
        response = self._send_command(command)
        self.log_event("info", "pump restarted")
        return response

    # =========================================================================
    #     Parameter Setting
    # =========================================================================

    def set_units(self, units: str) -> list:
        """
        Set flow rate units.

        Args:
            units: Units string ('mL/min', 'mL/hr', 'μL/min', 'μL/hr').

        Returns:
            list: Response from pump.
        """
        units_dict = {"mL/min": "0", "mL/hr": "1", "μL/min": "2", "μL/hr": "3"}

        if units not in units_dict:
            self.log_event("error", f"invalid units: {units}")
            return []

        command = f"set units {units_dict[units]}"
        response = self._send_command(command)
        self.log_event("info", f"units set to {units}")
        return response

    def set_diameter(self, diameter: float) -> list:
        """
        Set syringe diameter.

        Args:
            diameter: Syringe diameter in mm.

        Returns:
            list: Response from pump.
        """
        command = f"set diameter {diameter}"
        response = self._send_command(command)
        self.log_event("info", f"diameter set to {diameter} mm")
        return response

    def set_rate(self, rate) -> list:
        """
        Set flow rate.

        Args:
            rate: Flow rate (float) or list of rates for multi-step.

        Returns:
            list: Response from pump.
        """
        if isinstance(rate, list):
            # Multi-step command
            command = "set rate " + ",".join([str(x) for x in rate])
        else:
            command = f"set rate {rate}"

        response = self._send_command(command)
        self.log_event("info", f"flow rate set to {rate}")
        return response

    def set_volume(self, volume) -> list:
        """
        Set syringe volume.

        Args:
            volume: Volume (float) or list of volumes for multi-step.

        Returns:
            list: Response from pump.
        """
        if isinstance(volume, list):
            # Multi-step command
            command = "set volume " + ",".join([str(x) for x in volume])
        else:
            command = f"set volume {volume}"

        response = self._send_command(command)
        self.log_event("info", f"volume set to {volume}")
        return response

    def set_delay(self, delay) -> list:
        """
        Set delay between steps.

        Args:
            delay: Delay (float) or list of delays for multi-step.

        Returns:
            list: Response from pump.
        """
        if isinstance(delay, list):
            # Multi-step command
            command = "set delay " + ",".join([str(x) for x in delay])
        else:
            command = f"set delay {delay}"

        response = self._send_command(command)
        self.log_event("info", f"delay set to {delay}")
        return response

    def set_time(self, timer: float) -> list:
        """
        Set pump timer.

        Args:
            timer: Timer value.

        Returns:
            list: Response from pump.
        """
        command = f"set time {timer}"
        response = self._send_command(command)
        self.log_event("info", f"timer set to {timer}")
        return response

    # =========================================================================
    #     Parameter Reading
    # =========================================================================

    def get_parameter_limits(self) -> list:
        """Get parameter limits from pump."""
        if self.test_mode:
            return ["simulated: no limits"]
        return self._send_command("read limit parameter")

    def get_parameters(self) -> list:
        """Get current parameters from pump."""
        if self.test_mode:
            return [
                f"simulated: rate={self.pump_rate} {self.units}, "
                f"volume={self.volume} mL, diameter={self.diameter} mm"
            ]
        return self._send_command("view parameter")

    def get_displaced_volume(self) -> list:
        """Get displaced volume from pump."""
        if self.test_mode:
            return [f"{self._sim_uniform(0.0, self.volume, 3)} mL"]
        return self._send_command("dispensed volume")

    def get_elapsed_time(self) -> list:
        """Get elapsed time from pump."""
        if self.test_mode:
            return ["0:00"]
        return self._send_command("elapsed time")

    def get_pump_status(self) -> list:
        """Get pump status."""
        if self.test_mode:
            return ["pumping" if self._sim_running else "stopped"]
        return self._send_command("pump status")

    @staticmethod
    def get_available_ports() -> list:
        """
        Get list of available serial ports.

        Returns:
            list: Available port names.
        """
        if sys.platform.startswith("win"):
            ports = [f"COM{i+1}" for i in range(256)]
        elif sys.platform.startswith("linux") or sys.platform.startswith("cygwin"):
            ports = glob.glob("/dev/tty[A-Za-z]*")
        elif sys.platform.startswith("darwin"):
            ports = glob.glob("/dev/tty.*")
        else:
            raise EnvironmentError("Unsupported platform")

        result = []
        for port in ports:
            try:
                s = serial.Serial(port)
                s.close()
                result.append(port)
            except (OSError, serial.SerialException):
                pass
        return result

    # =========================================================================
    #     High-Level Operations
    # =========================================================================

    def apply_parameters(self, rate: float = None) -> None:
        """
        Send stored syringe parameters to the pump.

        Args:
            rate: Flow rate to apply. If None, uses self.pump_rate.
        """
        self.set_volume(self.volume)
        self.set_diameter(self.diameter)
        self.set_units(self.units)
        self.set_rate(rate if rate is not None else self.pump_rate)

    def withdraw(self) -> list:
        """
        Perform a full withdrawal cycle.

        Stops the pump (resetting displaced volume), configures withdrawal
        parameters (negative volume, withdraw_rate), starts the pump, waits
        for the estimated completion time plus a 2-second margin, then stops.

        Returns:
            list: Response from the final stop command.
        """
        # Step 1: Stop pump (resets displaced volume to zero)
        self.stop_pump()

        # Step 2: Configure withdrawal parameters
        self.set_rate(rate=self.withdraw_rate)
        self.set_volume(-self.volume)

        # Step 3: Start the pump
        self.start_pump()

        # Step 4: Estimate time and wait (units are mL/hr)
        estimated_seconds = (self.volume / self.withdraw_rate) * 3600

        wait_time = estimated_seconds + 2
        self.log_event(
            "info",
            f"withdrawal started: volume={self.volume}, rate={self.withdraw_rate}, "
            f"estimated time={estimated_seconds:.1f}s, waiting {wait_time:.1f}s",
        )
        time.sleep(wait_time)

        # Step 5: Stop the pump after withdrawal completes
        response = self.stop_pump()
        self.log_event("info", "withdrawal complete")
        return response

    # =========================================================================
    #     Housekeeping
    # =========================================================================

    def hk_monitor(self) -> None:
        """One housekeeping cycle: report pump status channels."""
        try:
            status = self.get_pump_status()
            self.log_sample("Pump_Status", status[0] if status else "no response")
            displaced = self.get_displaced_volume()
            if displaced:
                # Response shape is e.g. "0.923 mL" — report numerically when
                # possible so the value reaches the telemetry sink.
                try:
                    self.log_sample(
                        "Displaced_Vol", float(displaced[0].split()[0]), "mL", fmt=".3f"
                    )
                except (ValueError, IndexError):
                    self.log_sample("Displaced_Vol", displaced[0])
        except Exception as e:
            self.log_event("error", f"housekeeping read failed: {e}")

    def extra_status(self) -> Dict[str, Any]:
        """Syringe-pump-specific status entries."""
        return {
            "x": self.x,
            "mode": self.mode,
            "volume": self.volume,
            "diameter": self.diameter,
            "units": self.units,
            "pump_rate": self.pump_rate,
            "withdraw_rate": self.withdraw_rate,
        }
