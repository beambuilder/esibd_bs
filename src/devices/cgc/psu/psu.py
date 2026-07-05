"""
PSU (HV-PSU-CTRL-2D power supply) on the shared CGC lab layer.

``PSU`` combines the pure ctypes wrapper (``PSUBase``) with ``CGCDevice``
(canonical log line, telemetry sink, housekeeping worker + poke,
responding/reconnect, explicit test mode).

One controller carries 2 outputs (``PSU_POS=0`` feeding the positive rail,
``PSU_NEG=1`` the negative one); the lab's 4 physical supplies are 4 ``PSU``
instances distinguished by the ``port=`` DLL device index (0-3, notebook
023). The DLL carries that index in every export, so multiple units share
one loaded DLL ([[cgc-psu]]).

UNITS: the lab layer talks **milliampere** for output currents — exactly
like the pre-P6 wrapper that notebooks 011-023 were written against. The
publishable ``PSUBase`` API underneath stays in ampere.
"""
from typing import Optional
import logging
import threading

from ..cgc_device import CGCDevice
from .psu_base import PSUBase


class PSU(CGCDevice, PSUBase):
    """
    HV-PSU-CTRL-2D power supply with canonical logging, telemetry and
    test mode.

    Curated high-level methods (simulated in test mode): housekeeping/
    sensor/fan/CPU reads, state reads, PSU + device enable, output
    voltage set/read (V) and output current set/read (**mA**), measured
    PSU data, NVM config save/load. Raw DLL exports are
    real-hardware-only.

    Example:
        psu = PSU("PSU1", com=15, port=0, sink=sink)
        psu.connect()          # open + comspeed
        psu.set_device_enable(True)
        psu.set_psu0_output_voltage(50.0)
        status, volts = psu.get_psu0_output_voltage()
        psu.disconnect()
    """

    FAMILY = "PSU"
    DLL_BASE = PSUBase

    def __init__(
        self,
        device_id: str,
        com: int,
        port: int = 0,
        baudrate: int = 230400,
        logger: Optional[logging.Logger] = None,
        *,
        sink=None,
        test_mode: bool = False,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 5.0,
        **kwargs,
    ):
        """
        Initialize a PSU controller (see ``CGCDevice.__init__`` for the
        shared parameters). ``port`` is the DLL device index (0-3) that
        separates the 4 physical supplies. In test mode the vendor DLL is
        never loaded.
        """
        CGCDevice.__init__(
            self,
            device_id,
            com,
            baudrate,
            logger=logger,
            sink=sink,
            test_mode=test_mode,
            hk_thread=hk_thread,
            thread_lock=thread_lock,
            hk_interval=hk_interval,
            **kwargs,
        )
        # DLL device index; PSUBase.__init__ sets it too, but test mode
        # skips that call and extra_status()/close_port() still need it.
        self.dll_port = port
        # Simulated state (test mode only).
        self._sim_v_target = {self.PSU_POS: 0.0, self.PSU_NEG: 0.0}
        self._sim_i_limit_ma = {self.PSU_POS: 300.0, self.PSU_NEG: 300.0}
        self._sim_psu_enable = {self.PSU_POS: False, self.PSU_NEG: False}
        self._sim_device_enable = False
        self._sim_config = None
        if not test_mode:
            PSUBase.__init__(self, com=com, port=port, log=None, idn=device_id)

    # =========================================================================
    #     Transport (notebook 011/023 bring-up; reconnect() re-runs it)
    # =========================================================================

    def _open_transport(self) -> None:
        """PSU bring-up: open the DLL device index on the COM port, then
        negotiate the baud rate (a comspeed failure is a warning, the
        device stays usable at its default)."""
        self._check(self.open_port(self.com, self.dll_port), "open_port")
        baud_status = self.set_comspeed(self.baudrate)
        if baud_status == self.NO_ERR:
            self.log_event("info", f"comspeed set to {self.baudrate}")
        else:
            self.log_event(
                "warning",
                f"set_comspeed returned {baud_status}; "
                "continuing at device default",
            )

    # =========================================================================
    #     Status
    # =========================================================================

    def extra_status(self):
        status = CGCDevice.extra_status(self)
        status["dll_port"] = self.dll_port
        return status

    # =========================================================================
    #     Housekeeping (one canonical log_sample() line per channel)
    # =========================================================================

    def hk_monitor(self) -> None:
        """One housekeeping cycle: controller rails/temps, sensors, fans,
        CPU, states/enables and both PSU outputs. Blocks are individually
        guarded so one failing read does not silence the others."""
        with self.thread_lock:
            for block in (
                self._hk_general_housekeeping,
                self._hk_sensors,
                self._hk_fans,
                self._hk_cpu,
                self._hk_states,
                self._hk_psu_data,
            ):
                try:
                    block()
                except Exception as e:
                    self.log_event(
                        "error", f"housekeeping block {block.__name__} failed: {e}"
                    )

    def _hk_general_housekeeping(self):
        status, volt_rect, volt_5v0, volt_3v3, temp_cpu = self.get_housekeeping()
        if status != self.NO_ERR:
            self.log_event("warning", f"get_housekeeping returned {status}")
            return
        self.log_sample("Volt_Rect", volt_rect, "V", ".2f")
        self.log_sample("Volt_5V0", volt_5v0, "V", ".2f")
        self.log_sample("Volt_3V3", volt_3v3, "V", ".2f")
        self.log_sample("Temp_CPU", temp_cpu, "degC", ".1f")

    def _hk_sensors(self):
        status, temp0, temp1, temp2 = self.get_sensor_data()
        if status == self.NO_ERR:
            for i, temp in enumerate((temp0, temp1, temp2)):
                self.log_sample(f"Temp_Sensor{i}", temp, "degC", ".1f")

    def _hk_fans(self):
        status, enabled, failed, set_rpm, measured_rpm, pwm = self.get_fan_data()
        if status != self.NO_ERR:
            return
        for i in range(self.FAN_COUNT):
            self.log_sample(f"Fan{i}_RPM", measured_rpm[i], "rpm", ".0f")
            if failed[i]:
                self.log_event("warning", f"fan {i} reports FAILED")

    def _hk_cpu(self):
        status, load, frequency = self.get_cpu_data()
        if status == self.NO_ERR:
            self.log_sample("CPU_Load", load * 100, "%", ".1f")

    def _hk_states(self):
        status, state_hex, state_name = self.get_main_state()
        if status == self.NO_ERR:
            self.log_sample("Main_State", state_name)
        status, state_hex, names = self.get_device_state()
        if status == self.NO_ERR:
            self.log_sample("Device_State", ", ".join(names))
        status, state_hex, names = self.get_psu_state()
        if status == self.NO_ERR:
            self.log_sample("PSU_State", ", ".join(names) if names else "NONE")
        status, psu0, psu1 = self.get_psu_enable()
        if status == self.NO_ERR:
            self.log_sample("PSU0_Enabled", 1 if psu0 else 0)
            self.log_sample("PSU1_Enabled", 1 if psu1 else 0)
        status, enabled = self.get_device_enable()
        if status == self.NO_ERR:
            self.log_sample("Device_Enabled", 1 if enabled else 0)

    def _hk_psu_data(self):
        for psu_num, name in ((self.PSU_POS, "PSU0"), (self.PSU_NEG, "PSU1")):
            status, voltage, current, volt_dropout = self.get_psu_data(psu_num)
            if status != self.NO_ERR:
                self.log_event("warning", f"get_psu_data({psu_num}) returned {status}")
                continue
            self.log_sample(f"{name}_Voltage", voltage, "V", ".3f")
            self.log_sample(f"{name}_Current", current * 1000.0, "mA", ".3f")
            self.log_sample(f"{name}_Dropout", volt_dropout, "V", ".2f")

    # =========================================================================
    #     Curated reads (simulated in test mode)
    # =========================================================================

    def _sim_output_on(self, psu_num) -> bool:
        return self._sim_device_enable and self._sim_psu_enable.get(psu_num, False)

    def get_housekeeping(self):
        if self.test_mode:
            return (
                self.NO_ERR,
                self._sim_uniform(23.5, 24.5),     # volt_rect
                self._sim_uniform(4.9, 5.1),       # volt_5v0
                self._sim_uniform(3.25, 3.35),     # volt_3v3
                self._sim_uniform(30.0, 40.0, 1),  # temp_cpu
            )
        return PSUBase.get_housekeeping(self)

    def get_sensor_data(self):
        if self.test_mode:
            return (
                self.NO_ERR,
                self._sim_uniform(25.0, 35.0, 1),
                self._sim_uniform(25.0, 35.0, 1),
                self._sim_uniform(25.0, 35.0, 1),
            )
        return PSUBase.get_sensor_data(self)

    def get_fan_data(self):
        if self.test_mode:
            rpm = [self._sim_uniform(2900, 3100, 0) for _ in range(self.FAN_COUNT)]
            return (
                self.NO_ERR,
                [True] * self.FAN_COUNT,
                [False] * self.FAN_COUNT,
                [3000] * self.FAN_COUNT,
                rpm,
                [500] * self.FAN_COUNT,
            )
        return PSUBase.get_fan_data(self)

    def get_cpu_data(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_uniform(0.05, 0.20, 3), 168e6
        return PSUBase.get_cpu_data(self)

    def get_main_state(self):
        if self.test_mode:
            if self._sim_device_enable:
                return self.NO_ERR, hex(0), self.MAIN_STATE[0]  # STATE_ON
            return self.NO_ERR, hex(0x8005), self.MAIN_STATE[0x8005]  # PSU_DIS
        return PSUBase.get_main_state(self)

    def get_device_state(self):
        if self.test_mode:
            if self._sim_device_enable:
                return self.NO_ERR, hex(0), ["DEVST_OK"]
            value = 1 << 0x0F  # DEVST_PSU_DIS
            return self.NO_ERR, hex(value), ["DEVST_PSU_DIS"]
        return PSUBase.get_device_state(self)

    def get_psu_state(self):
        if self.test_mode:
            value = 0
            names = []
            if self._sim_psu_enable[self.PSU_POS]:
                value |= 1 << 20
                names.append("ST_PSU0_ENB_ACT")
            if self._sim_psu_enable[self.PSU_NEG]:
                value |= 1 << 21
                names.append("ST_PSU1_ENB_ACT")
            return self.NO_ERR, hex(value), names
        return PSUBase.get_psu_state(self)

    def get_psu_enable(self):
        if self.test_mode:
            return (
                self.NO_ERR,
                self._sim_psu_enable[self.PSU_POS],
                self._sim_psu_enable[self.PSU_NEG],
            )
        return PSUBase.get_psu_enable(self)

    def get_device_enable(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_device_enable
        return PSUBase.get_device_enable(self)

    def get_psu_data(self, psu_num):
        """Returns (status, voltage [V], current [A], volt_dropout [V]).
        Simulated readback tracks the target while device + output are
        enabled; the simulated load draws ~0.2 mA per volt."""
        if self.test_mode:
            if psu_num not in self._sim_v_target:
                return self.ERR_ARGUMENT, 0.0, 0.0, 0.0
            if self._sim_output_on(psu_num):
                target = self._sim_v_target[psu_num]
                voltage = target + self._sim_uniform(-0.05, 0.05, 3)
                current = target * 2e-4 + self._sim_uniform(0.0, 1e-4, 6)
                return self.NO_ERR, voltage, current, self._sim_uniform(2.0, 4.0)
            return self.NO_ERR, 0.0, 0.0, 0.0
        return PSUBase.get_psu_data(self, psu_num)

    def get_psu_output_voltage(self, psu_num):
        if self.test_mode:
            status, voltage, _, _ = self.get_psu_data(psu_num)
            return status, voltage
        return PSUBase.get_psu_output_voltage(self, psu_num)

    def get_psu_set_output_voltage(self, psu_num):
        if self.test_mode:
            if psu_num not in self._sim_v_target:
                return self.ERR_ARGUMENT, 0.0, 0.0
            return self.NO_ERR, self._sim_v_target[psu_num], 350.0
        return PSUBase.get_psu_set_output_voltage(self, psu_num)

    # =========================================================================
    #     Curated controls (logging + test-mode simulation)
    # =========================================================================

    def set_psu_output_voltage(self, psu_num, voltage):
        """Set one output's voltage setpoint in volts. Returns the status."""
        self.log_event(
            "info", f"setting PSU{psu_num} output voltage to {float(voltage):.3f} V"
        )
        if self.test_mode:
            self.check_U_format(voltage)
            if psu_num not in self._sim_v_target:
                return self.ERR_ARGUMENT
            self._sim_v_target[psu_num] = float(voltage)
            return self.NO_ERR
        status = PSUBase.set_psu_output_voltage(self, psu_num, voltage)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to set PSU{psu_num} output voltage: status {status}",
            )
        return status

    def set_psu_output_current(self, psu_num, current_ma):
        """Set one output's current limit in **mA** (lab-layer unit; the
        DLL underneath takes ampere). Returns the status."""
        current_a = float(current_ma) / 1000.0
        self.log_event(
            "info",
            f"setting PSU{psu_num} output current to {float(current_ma):.3f} mA",
        )
        if self.test_mode:
            self.check_I_format(current_a)
            if psu_num not in self._sim_i_limit_ma:
                return self.ERR_ARGUMENT
            self._sim_i_limit_ma[psu_num] = float(current_ma)
            return self.NO_ERR
        status = PSUBase.set_psu_output_current(self, psu_num, current_a)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to set PSU{psu_num} output current: status {status}",
            )
        return status

    def get_psu_output_current(self, psu_num):
        """Returns (status, current [mA]) — lab-layer unit is mA."""
        if self.test_mode:
            status, _, current_a, _ = self.get_psu_data(psu_num)
            return status, current_a * 1000.0
        status, current_a = PSUBase.get_psu_output_current(self, psu_num)
        return status, current_a * 1000.0

    def get_psu_set_output_current(self, psu_num):
        """Returns (status, current_set [mA], current_limit [mA])."""
        if self.test_mode:
            if psu_num not in self._sim_i_limit_ma:
                return self.ERR_ARGUMENT, 0.0, 0.0
            limit = self._sim_i_limit_ma[psu_num]
            return self.NO_ERR, limit, limit
        status, set_a, limit_a = PSUBase.get_psu_set_output_current(self, psu_num)
        return status, set_a * 1000.0, limit_a * 1000.0

    # mA aliases (the base's per-output aliases would dispatch back into
    # the mA-taking overrides with ampere semantics — keep them explicit).

    def set_psu0_output_current(self, current_ma):
        """Set PSU0 (positive) output current limit in mA."""
        return self.set_psu_output_current(self.PSU_POS, current_ma)

    def set_psu1_output_current(self, current_ma):
        """Set PSU1 (negative) output current limit in mA."""
        return self.set_psu_output_current(self.PSU_NEG, current_ma)

    def get_psu0_output_current(self):
        """Get PSU0 (positive) output current in mA."""
        return self.get_psu_output_current(self.PSU_POS)

    def get_psu1_output_current(self):
        """Get PSU1 (negative) output current in mA."""
        return self.get_psu_output_current(self.PSU_NEG)

    def get_psu0_set_output_current(self):
        """Get PSU0 (positive) set & limit output current in mA."""
        return self.get_psu_set_output_current(self.PSU_POS)

    def get_psu1_set_output_current(self):
        """Get PSU1 (negative) set & limit output current in mA."""
        return self.get_psu_set_output_current(self.PSU_NEG)

    def set_psu_enable(self, psu0, psu1):
        """Enable/disable both outputs in one call. Returns the status."""
        self.log_event("info", f"setting PSU enable to psu0={psu0}, psu1={psu1}")
        if self.test_mode:
            self._sim_psu_enable[self.PSU_POS] = bool(psu0)
            self._sim_psu_enable[self.PSU_NEG] = bool(psu1)
            return self.NO_ERR
        status = PSUBase.set_psu_enable(self, psu0, psu1)
        if status != self.NO_ERR:
            self.log_event("error", f"failed to set PSU enable: status {status}")
        return status

    def set_device_enable(self, enable):
        """Set the device enable state. Returns the status."""
        self.log_event("info", f"setting device enable to {enable}")
        if self.test_mode:
            self._sim_device_enable = bool(enable)
            return self.NO_ERR
        status = PSUBase.set_device_enable(self, enable)
        if status != self.NO_ERR:
            self.log_event("error", f"failed to set device enable: status {status}")
        return status

    def load_current_config(self, config_number):
        """Load one NVM config slot (campaign code prefers the curated
        slots over raw setpoints, [[cgc-psu]]). Returns the status."""
        self.log_event("info", f"loading config slot {config_number}")
        if self.test_mode:
            self._sim_config = int(config_number)
            return self.NO_ERR
        status = PSUBase.load_current_config(self, config_number)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to load config {config_number}: status {status}"
            )
        return status

    def save_current_config(self, config_number):
        """Save the current settings to one NVM config slot."""
        self.log_event("info", f"saving config slot {config_number}")
        if self.test_mode:
            self._sim_config = int(config_number)
            return self.NO_ERR
        status = PSUBase.save_current_config(self, config_number)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to save config {config_number}: status {status}"
            )
        return status

    def restart(self):
        """Restart the controller (real hardware only)."""
        self.log_event("info", "restarting PSU controller")
        status = PSUBase.restart(self)
        if status != self.NO_ERR:
            self.log_event("error", f"controller restart failed: status {status}")
        return status
