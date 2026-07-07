"""
SW (HV-AMX-CTRL-4ED switch controller, unit "swB") on the shared CGC lab
layer.

``SW`` combines the pure ctypes wrapper (``SWBase``) with ``CGCDevice``
(canonical log line, telemetry sink, housekeeping worker + poke,
responding/reconnect, explicit test mode). The controller manages 4
high-voltage switches with configurable pulsers, digital I/O and
trigger/enable mappings; the DLL carries a device index (``port=``) in
every export, so multiple units share one loaded DLL.

SAFETY ([[cgc-sw]], CGC email): per-switch-channel dissipation < 100 W,
current <= 300 mA at 350 V. Ramp voltage at 1 kHz up to the target FIRST,
then ramp frequency at full voltage — helpers enforcing this live in
``devices.cgc.campaign``.

Known hardware quirk: swB sensor 0 is broken (swA sensor 2 on the SWHR
unit) — construct with ``skip_sensors=(0,)`` so housekeeping never logs
its garbage.
"""
from typing import Optional
import logging
import threading

from ..cgc_device import CGCDevice
from .sw_base import SWBase


class SW(CGCDevice, SWBase):
    """
    HV-AMX-CTRL-4ED switch controller with canonical logging, telemetry
    and test mode.

    Curated high-level methods (simulated in test mode): housekeeping/
    sensor/fan/CPU reads, state reads, device enable, oscillator period,
    pulser delay/width/burst, NVM config save/load, and the frequency/
    duty-cycle conveniences the campaign ramps use. Raw DLL exports are
    real-hardware-only.

    Example:
        sw = SW("swB", com=19, port=0, sink=sink, skip_sensors=(0,))
        sw.connect()             # open + comspeed
        sw.load_current_config(40)   # NVM slot: SwitchSym 1 kHz
        sw.set_device_enable(True)
        sw.disconnect()
    """

    FAMILY = "SW"
    DLL_BASE = SWBase

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
        skip_sensors=(),
        **kwargs,
    ):
        """
        Initialize a switch controller (see ``CGCDevice.__init__`` for the
        shared parameters). ``port`` is the DLL device index;
        ``skip_sensors`` lists broken temperature-sensor indices (0-2)
        that housekeeping must never log. In test mode the vendor DLL is
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
        self.dll_port = port
        self.skip_sensors = tuple(skip_sensors)
        # Simulated state (test mode only). Default oscillator period =
        # 1 kHz (period register = CLOCK/f - OSC_OFFSET), the safe ramp
        # frequency of the CGC recipe.
        self._sim_device_enable = False
        self._sim_osc_period = int(self.CLOCK / 1000.0 - self.OSC_OFFSET)
        self._sim_pulser_delay = {i: 1 for i in range(self.PULSER_NUM)}
        self._sim_pulser_width = {i: 0 for i in range(self.PULSER_NUM)}
        self._sim_pulser_burst = {i: 0 for i in range(self.PULSER_BURST_NUM)}
        self._sim_config = None
        if not test_mode:
            SWBase.__init__(self, com=com, port=port, log=None, idn=device_id)

    # =========================================================================
    #     Transport (notebook 023 bring-up; reconnect() re-runs it)
    # =========================================================================

    def _open_transport(self) -> None:
        """SW bring-up: open the DLL device index on the COM port, then
        negotiate the baud rate (a comspeed failure is a warning, the
        device stays usable at its default)."""
        self._check(self.open_port(self.com, self.dll_port), "open_port")
        baud_status, actual_baud = self.set_comspeed(self.baudrate)
        if baud_status == self.NO_ERR:
            self.log_event("info", f"comspeed set to {actual_baud}")
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
        if self.skip_sensors:
            status["skip_sensors"] = list(self.skip_sensors)
        return status

    # =========================================================================
    #     Housekeeping (one canonical log_sample() line per channel)
    # =========================================================================

    def hk_monitor(self) -> None:
        """One housekeeping cycle: controller rails/temps, sensors
        (minus the broken ones), fans, CPU, oscillator and states.
        Blocks are individually guarded so one failing read does not
        silence the others. Pulser/switch configuration reads stay out
        of housekeeping — those are notebook/campaign territory."""
        with self.thread_lock:
            for block in (
                self._hk_general_housekeeping,
                self._hk_sensors,
                self._hk_fans,
                self._hk_cpu,
                self._hk_oscillator,
                self._hk_states,
            ):
                try:
                    block()
                except Exception as e:
                    self.log_event(
                        "error", f"housekeeping block {block.__name__} failed: {e}"
                    )

    def _hk_general_housekeeping(self):
        status, volt_12v, volt_5v0, volt_3v3, temp_cpu = self.get_housekeeping()
        if status != self.NO_ERR:
            self.log_event("warning", f"get_housekeeping returned {status}")
            return
        self.log_sample("Volt_12V", volt_12v, "V", ".2f")
        self.log_sample("Volt_5V0", volt_5v0, "V", ".2f")
        self.log_sample("Volt_3V3", volt_3v3, "V", ".2f")
        self.log_sample("Temp_CPU", temp_cpu, "degC", ".1f")

    def _hk_sensors(self):
        status, temp0, temp1, temp2 = self.get_sensor_data()
        if status == self.NO_ERR:
            for i, temp in enumerate((temp0, temp1, temp2)):
                if i in self.skip_sensors:
                    continue
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

    def _hk_oscillator(self):
        status, period = self.get_oscillator_period()
        if status == self.NO_ERR:
            self.log_sample("Osc_Period", period)
            if period > 0:
                freq = self.CLOCK / (period + self.OSC_OFFSET)
                self.log_sample("Osc_Freq", freq, "Hz", ".1f")

    def _hk_states(self):
        status, state_hex, state_name = self.get_main_state()
        if status == self.NO_ERR:
            self.log_sample("Main_State", state_name)
        status, state_hex, names = self.get_device_state()
        if status == self.NO_ERR:
            self.log_sample("Device_State", ", ".join(names) if names else "NONE")
        status, state_hex, names = self.get_controller_state()
        if status == self.NO_ERR:
            self.log_sample(
                "Controller_State", ", ".join(names) if names else "NONE"
            )
        status, enabled = self.get_device_enable()
        if status == self.NO_ERR:
            self.log_sample("Device_Enabled", 1 if enabled else 0)

    # =========================================================================
    #     Curated reads (simulated in test mode)
    # =========================================================================

    def get_housekeeping(self):
        if self.test_mode:
            return (
                self.NO_ERR,
                self._sim_uniform(11.8, 12.2),     # volt_12v
                self._sim_uniform(4.9, 5.1),       # volt_5v0
                self._sim_uniform(3.25, 3.35),     # volt_3v3
                self._sim_uniform(30.0, 45.0, 1),  # temp_cpu
            )
        return SWBase.get_housekeeping(self)

    def get_sensor_data(self):
        if self.test_mode:
            return (
                self.NO_ERR,
                self._sim_uniform(25.0, 40.0, 1),
                self._sim_uniform(25.0, 40.0, 1),
                self._sim_uniform(25.0, 40.0, 1),
            )
        return SWBase.get_sensor_data(self)

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
        return SWBase.get_fan_data(self)

    def get_cpu_data(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_uniform(0.05, 0.20, 3), 168e6
        return SWBase.get_cpu_data(self)

    def get_main_state(self):
        if self.test_mode:
            return self.NO_ERR, hex(0), self.MAIN_STATE[0]  # STATE_ON
        return SWBase.get_main_state(self)

    def get_device_state(self):
        if self.test_mode:
            return self.NO_ERR, hex(0), ["DEVST_OK"]
        return SWBase.get_device_state(self)

    def get_controller_state(self):
        if self.test_mode:
            if self._sim_device_enable:
                value = 0b111  # ENB | ENB_OSC | ENB_PULSER
                return self.NO_ERR, hex(value), ["ENB", "ENB_OSC", "ENB_PULSER"]
            return self.NO_ERR, hex(0), []
        return SWBase.get_controller_state(self)

    def get_device_enable(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_device_enable
        return SWBase.get_device_enable(self)

    def get_oscillator_period(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_osc_period
        return SWBase.get_oscillator_period(self)

    def get_pulser_delay(self, pulser_no):
        if self.test_mode:
            if pulser_no not in self._sim_pulser_delay:
                return self.ERR_ARGUMENT, 0
            return self.NO_ERR, self._sim_pulser_delay[pulser_no]
        return SWBase.get_pulser_delay(self, pulser_no)

    def get_pulser_width(self, pulser_no):
        if self.test_mode:
            if pulser_no not in self._sim_pulser_width:
                return self.ERR_ARGUMENT, 0
            return self.NO_ERR, self._sim_pulser_width[pulser_no]
        return SWBase.get_pulser_width(self, pulser_no)

    def get_pulser_burst(self, pulser_no):
        if self.test_mode:
            if pulser_no not in self._sim_pulser_burst:
                return self.ERR_ARGUMENT, 0
            return self.NO_ERR, self._sim_pulser_burst[pulser_no]
        return SWBase.get_pulser_burst(self, pulser_no)

    # =========================================================================
    #     Curated controls (logging + test-mode simulation)
    # =========================================================================

    def set_device_enable(self, enable):
        """Set the device enable state. Returns the status."""
        self.log_event("info", f"setting device enable to {enable}")
        if self.test_mode:
            self._sim_device_enable = bool(enable)
            return self.NO_ERR
        status = SWBase.set_device_enable(self, enable)
        if status != self.NO_ERR:
            self.log_event("error", f"failed to set device enable: status {status}")
        return status

    def set_oscillator_period(self, period):
        """Set the oscillator period register. Returns the status."""
        freq = self.CLOCK / (period + self.OSC_OFFSET) if period > 0 else 0
        self.log_event(
            "info", f"setting oscillator period to {period} (~{freq:.1f} Hz)"
        )
        if self.test_mode:
            self._sim_osc_period = int(period)
            return self.NO_ERR
        status = SWBase.set_oscillator_period(self, period)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set oscillator period: status {status}"
            )
        return status

    def set_pulser_delay(self, pulser_no, delay):
        """Set one pulser's delay register. Returns the status."""
        self.log_event("info", f"setting pulser {pulser_no} delay to {delay}")
        if self.test_mode:
            if pulser_no not in self._sim_pulser_delay:
                return self.ERR_ARGUMENT
            self._sim_pulser_delay[pulser_no] = int(delay)
            return self.NO_ERR
        status = SWBase.set_pulser_delay(self, pulser_no, delay)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set pulser {pulser_no} delay: status {status}"
            )
        return status

    def set_pulser_width(self, pulser_no, width):
        """Set one pulser's width register. Returns the status."""
        self.log_event("info", f"setting pulser {pulser_no} width to {width}")
        if self.test_mode:
            if pulser_no not in self._sim_pulser_width:
                return self.ERR_ARGUMENT
            self._sim_pulser_width[pulser_no] = int(width)
            return self.NO_ERR
        status = SWBase.set_pulser_width(self, pulser_no, width)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set pulser {pulser_no} width: status {status}"
            )
        return status

    def set_pulser_burst(self, pulser_no, burst):
        """Set one pulser's burst size. Returns the status."""
        self.log_event("info", f"setting pulser {pulser_no} burst to {burst}")
        if self.test_mode:
            if pulser_no not in self._sim_pulser_burst:
                return self.ERR_ARGUMENT
            self._sim_pulser_burst[pulser_no] = int(burst)
            return self.NO_ERR
        status = SWBase.set_pulser_burst(self, pulser_no, burst)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set pulser {pulser_no} burst: status {status}"
            )
        return status

    def set_controller_config(self, config):
        """Set the controller configuration word. Returns the status."""
        self.log_event("info", f"setting controller config to 0x{config:02X}")
        if self.test_mode:
            self._sim_device_enable = bool(config & 1)  # ENB bit
            return self.NO_ERR
        status = SWBase.set_controller_config(self, config)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set controller config: status {status}"
            )
        return status

    def load_current_config(self, config_number):
        """Load one NVM config slot (swB's SwitchSym RF ladder: 1=Standby,
        40=1 kHz ... 90=1 MHz, 101-106=1.2-5 MHz, [[cgc-sw]])."""
        self.log_event("info", f"loading config slot {config_number}")
        if self.test_mode:
            self._sim_config = int(config_number)
            return self.NO_ERR
        status = SWBase.load_current_config(self, config_number)
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
        status = SWBase.save_current_config(self, config_number)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to save config {config_number}: status {status}"
            )
        return status

    def restart(self):
        """Restart the controller (real hardware only)."""
        self.log_event("info", "restarting SW controller")
        status = SWBase.restart(self)
        if status != self.NO_ERR:
            self.log_event("error", f"controller restart failed: status {status}")
        return status

    # =========================================================================
    #     Conveniences (work in sim too — the campaign dry-run uses them)
    # =========================================================================

    def set_frequency_khz(self, frequency_khz):
        """
        Set the oscillator frequency in kHz via the period register:
        ``Period_register = CLOCK / (f_khz * 1000) - OSC_OFFSET``.
        Returns the status.
        """
        if frequency_khz <= 0:
            self.log_event(
                "error", f"invalid frequency: {frequency_khz} kHz (must be > 0)"
            )
            return self.ERR_ARGUMENT
        period = round(self.CLOCK / (frequency_khz * 1000) - self.OSC_OFFSET)
        if period < 1 or period > 0xFFFFFFFF:
            self.log_event(
                "error",
                f"frequency {frequency_khz} kHz gives out-of-range period "
                f"register {period}",
            )
            return self.ERR_ARGUMENT
        return self.set_oscillator_period(period)

    def set_rf(self, frequency_khz, duty=0.5, pulser=0):
        """
        Symmetric frequency move (hoisted from notebook 025's
        ``swb_set_frequency``): the NVM configs fix the width REGISTER
        (50 % only at their own period), so the width must be re-fit
        after every period change — width goes minimal first so
        width >= period (stuck-HIGH output) can never happen mid-move,
        then the period moves, then the duty is re-fit.

        Validates before touching the device: pulser/duty/frequency
        ranges, the stuck-HIGH trap (current delay 0 with a nonzero
        width) and the monoflop rule ``Period+2 > (Delay+3) + (Width+2)``
        against the NEW period and the CURRENT delay — a violated rule
        means silently ignored triggers ([[cgc-sw]]).

        Each step runs via ``call_with_retry`` (locked, purge-retry on
        EMI serial corruption); the caller must NOT hold ``thread_lock``.
        Returns the first nonzero status, or ``NO_ERR``.
        """
        if pulser < 0 or pulser >= self.PULSER_NUM:
            self.log_event(
                "error",
                f"invalid pulser number: {pulser} "
                f"(must be 0-{self.PULSER_NUM - 1})",
            )
            return self.ERR_ARGUMENT
        if duty <= 0.0 or duty >= 1.0:
            self.log_event(
                "error",
                f"invalid duty cycle: {duty} "
                "(must be in exclusive range 0.0 to 1.0)",
            )
            return self.ERR_ARGUMENT
        if frequency_khz <= 0:
            self.log_event(
                "error", f"invalid frequency: {frequency_khz} kHz (must be > 0)"
            )
            return self.ERR_ARGUMENT
        period = round(self.CLOCK / (frequency_khz * 1000) - self.OSC_OFFSET)
        if period < 1 or period > 0xFFFFFFFF:
            self.log_event(
                "error",
                f"frequency {frequency_khz} kHz gives out-of-range period "
                f"register {period}",
            )
            return self.ERR_ARGUMENT
        width = max(
            1, round(duty * (period + self.OSC_OFFSET) - self.PULSER_WIDTH_OFFSET)
        )
        result = self.call_with_retry(self.get_pulser_delay, pulser)
        status, delay = result
        if status != self.NO_ERR:
            return status
        if delay == 0:
            self.log_event(
                "error",
                f"pulser {pulser} delay register is 0 — a nonzero width "
                "would stick the output HIGH (DC on the load); set a "
                "delay >= 1 first",
            )
            return self.ERR_ARGUMENT
        if (period + self.OSC_OFFSET) <= (
            (delay + self.PULSER_DELAY_OFFSET) + (width + self.PULSER_WIDTH_OFFSET)
        ):
            self.log_event(
                "error",
                f"monoflop rule violated for {frequency_khz} kHz at duty "
                f"{duty}: period+{self.OSC_OFFSET} = {period + self.OSC_OFFSET} "
                f"must exceed (delay+{self.PULSER_DELAY_OFFSET}) + "
                f"(width+{self.PULSER_WIDTH_OFFSET}) = "
                f"{delay + self.PULSER_DELAY_OFFSET + width + self.PULSER_WIDTH_OFFSET}"
                " — triggers would be silently ignored",
            )
            return self.ERR_ARGUMENT
        status = self.call_with_retry(self.set_pulser_width, pulser, 1)
        if status != self.NO_ERR:
            return status
        status = self.call_with_retry(self.set_frequency_khz, frequency_khz)
        if status != self.NO_ERR:
            return status
        return self.call_with_retry(self.set_duty_cycle, pulser, duty)

    def set_delay_minimum(self, pulser_no):
        """Set one pulser's delay to the minimum (register 1 =
        ``(1 + PULSER_DELAY_OFFSET) * 10`` ns). Returns the status."""
        if pulser_no < 0 or pulser_no >= self.PULSER_NUM:
            self.log_event(
                "error",
                f"invalid pulser number: {pulser_no} "
                f"(must be 0-{self.PULSER_NUM - 1})",
            )
            return self.ERR_ARGUMENT
        return self.set_pulser_delay(pulser_no, 1)

    def set_duty_cycle(self, pulser_no, duty_cycle):
        """
        Set one pulser's duty cycle relative to the current oscillator
        period: ``Width_register = duty * (Period_register + OSC_OFFSET)
        - PULSER_WIDTH_OFFSET``. Returns the status.
        """
        if pulser_no < 0 or pulser_no >= self.PULSER_NUM:
            self.log_event(
                "error",
                f"invalid pulser number: {pulser_no} "
                f"(must be 0-{self.PULSER_NUM - 1})",
            )
            return self.ERR_ARGUMENT
        if duty_cycle <= 0.0 or duty_cycle >= 1.0:
            self.log_event(
                "error",
                f"invalid duty cycle: {duty_cycle} "
                "(must be in exclusive range 0.0 to 1.0)",
            )
            return self.ERR_ARGUMENT
        status, period = self.get_oscillator_period()
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to read oscillator period: status {status}"
            )
            return status
        width = duty_cycle * (period + self.OSC_OFFSET) - self.PULSER_WIDTH_OFFSET
        width = max(1, round(width))
        return self.set_pulser_width(pulser_no, width)
