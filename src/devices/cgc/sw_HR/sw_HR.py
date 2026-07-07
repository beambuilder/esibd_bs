"""
SWHR (HV-AMX-CTRL-4EDH high-resolution switch controller, unit "swA") on
the shared CGC lab layer.

``SWHR`` combines the pure ctypes wrapper (``SWHRBase``) with ``CGCDevice``
(canonical log line, telemetry sink, housekeeping worker + poke,
responding/reconnect, explicit test mode). This is the deliberate THIN
rewrite of the abandoned 522-line copy-paste subclass (P6.8): the curated
lab layer covers housekeeping, enable, oscillators/timers, coarse + fine
switch delays and NVM configs; everything else stays a raw DLL export
(real hardware only, traceable via ``trace_dll_calls()``).

The 4EDH manages 4 high-voltage switches with PLLs, clocks, dividers,
counters, timers, mapping engines and 11 ps fine delay steps
(``SWITCH_DELAY_FINE_SCALE``); the DLL carries a device index
(``stream=``) in every export.

SAFETY ([[cgc-sw]], CGC email): per-switch-channel dissipation < 100 W,
current <= 300 mA at 350 V; ramp voltage at 1 kHz FIRST, then frequency.
swA's NVM carries its own SwitchSym RF ladder (python 269-277 + HF
279-288; 277 = 1 MHz, the 023-proven campaign baseline). swA sensor 2 is
broken — construct with ``skip_sensors=(2,)``.
"""
from typing import Optional
import logging
import threading

from ..cgc_device import CGCDevice
from .sw_HR_base import SWHRBase


class SWHR(CGCDevice, SWHRBase):
    """
    HV-AMX-CTRL-4EDH high-resolution switch controller with canonical
    logging, telemetry and test mode.

    Curated high-level methods (simulated in test mode): housekeeping/
    sensor/fan/CPU reads, combined device state, device enable,
    per-oscillator period, timer delay/width, coarse switch delay +
    rise/fall fine delays, NVM config save/load, frequency convenience.
    Raw DLL exports are real-hardware-only.

    Example:
        swhr = SWHR("swA", com=20, stream=0, sink=sink, skip_sensors=(2,))
        swhr.connect()             # open + comspeed
        swhr.set_device_enable(True)
        swhr.set_switch_rise_delay_fine(0, 0x100)
        swhr.disconnect()
    """

    FAMILY = "SWHR"
    DLL_BASE = SWHRBase
    # Timer count is device-queried (get_timer_count); 4 matches every
    # other 4EDH resource block (clocks/PLLs/dividers/counters) and the
    # campaign hardware. Used for argument validation and the sim dicts.
    TIMER_NUM = 4

    def __init__(
        self,
        device_id: str,
        com: int,
        stream: int = 0,
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
        Initialize a high-resolution switch controller (see
        ``CGCDevice.__init__`` for the shared parameters). ``stream`` is
        the DLL device index; ``skip_sensors`` lists broken
        temperature-sensor indices (0-2) that housekeeping must never
        log. In test mode the vendor DLL is never loaded.
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
        # DLL device index; SWHRBase.__init__ sets it too, but test mode
        # skips that call and close_port()/extra_status() still need it.
        self.stream = stream
        self.skip_sensors = tuple(skip_sensors)
        # Simulated state (test mode only). Oscillator default = 1 kHz.
        self._sim_device_enable = False
        self._sim_osc_period = {
            i: int(self.DEF_CLOCK / 1000.0 - self.OSC_OFFSET)
            for i in range(self.CLOCK_NUM)
        }
        self._sim_timer_delay = {i: 1 for i in range(self.TIMER_NUM)}
        self._sim_timer_width = {i: 0 for i in range(self.TIMER_NUM)}
        self._sim_switch_delay = {
            i: (0, 0) for i in range(self.SWITCH_NUM)
        }
        self._sim_rise_fine = {i: 0 for i in range(self.SWITCH_NUM)}
        self._sim_fall_fine = {i: 0 for i in range(self.SWITCH_NUM)}
        self._sim_config = None
        if not test_mode:
            SWHRBase.__init__(self, com=com, stream=stream, log=None, idn=device_id)

    # =========================================================================
    #     Transport (bring-up; reconnect() re-runs it)
    # =========================================================================

    def _open_transport(self) -> None:
        """SWHR bring-up: open the DLL stream index on the COM port, then
        negotiate the baud rate (a comspeed failure is a warning, the
        device stays usable at its default)."""
        self._check(self.open_port(self.com, self.stream), "open_port")
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
        status["stream"] = self.stream
        if self.skip_sensors:
            status["skip_sensors"] = list(self.skip_sensors)
        return status

    # =========================================================================
    #     Housekeeping (one canonical log_sample() line per channel)
    # =========================================================================

    def hk_monitor(self) -> None:
        """One housekeeping cycle: controller rails/temps, sensors
        (minus the broken ones), fans, CPU and states. Blocks are
        individually guarded so one failing read does not silence the
        others. PLL/timer/delay configuration reads stay out of
        housekeeping — those are notebook/campaign territory."""
        with self.thread_lock:
            for block in (
                self._hk_general_housekeeping,
                self._hk_sensors,
                self._hk_fans,
                self._hk_cpu,
                self._hk_states,
            ):
                try:
                    block()
                except Exception as e:
                    self.log_event(
                        "error", f"housekeeping block {block.__name__} failed: {e}"
                    )

    def _hk_general_housekeeping(self):
        (status, volt_12v, volt_fans, volt_5v0, volt_3v3, volt_3v3p,
         volt_2v5p, volt_vc, temp_cpu) = self.get_housekeeping()
        if status != self.NO_ERR:
            self.log_event("warning", f"get_housekeeping returned {status}")
            return
        self.log_sample("Volt_12V", volt_12v, "V", ".2f")
        self.log_sample("Volt_Fans", volt_fans, "V", ".2f")
        self.log_sample("Volt_5V0", volt_5v0, "V", ".2f")
        self.log_sample("Volt_3V3", volt_3v3, "V", ".2f")
        self.log_sample("Volt_3V3P", volt_3v3p, "V", ".2f")
        self.log_sample("Volt_2V5P", volt_2v5p, "V", ".2f")
        self.log_sample("Volt_VC", volt_vc, "V", ".2f")
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

    def _hk_states(self):
        (status, main_hex, main_name, dev_hex, dev_names,
         temp_hex, temp_names) = self.get_device_state()
        if status == self.NO_ERR:
            self.log_sample("Main_State", main_name)
            self.log_sample("Device_State", ", ".join(dev_names))
            self.log_sample("Temperature_State", ", ".join(temp_names))
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
                self._sim_uniform(11.8, 12.2),     # volt_fans
                self._sim_uniform(4.9, 5.1),       # volt_5v0
                self._sim_uniform(3.25, 3.35),     # volt_3v3
                self._sim_uniform(3.25, 3.35),     # volt_3v3p
                self._sim_uniform(2.45, 2.55),     # volt_2v5p
                self._sim_uniform(1.15, 1.25),     # volt_vc
                self._sim_uniform(30.0, 45.0, 1),  # temp_cpu
            )
        return SWHRBase.get_housekeeping(self)

    def get_sensor_data(self):
        if self.test_mode:
            return (
                self.NO_ERR,
                self._sim_uniform(25.0, 40.0, 1),
                self._sim_uniform(25.0, 40.0, 1),
                self._sim_uniform(25.0, 40.0, 1),
            )
        return SWHRBase.get_sensor_data(self)

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
        return SWHRBase.get_fan_data(self)

    def get_cpu_data(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_uniform(0.05, 0.20, 3), 168e6
        return SWHRBase.get_cpu_data(self)

    def get_device_state(self):
        """Returns the base's 7-tuple: (status, main_hex, main_name,
        dev_hex, dev_names, temp_hex, temp_names)."""
        if self.test_mode:
            main = 1 if self._sim_device_enable else 0
            return (
                self.NO_ERR,
                hex(main), self.MAIN_STATE[main],
                hex(0), ["DEVST_OK"],
                hex(0), ["TMPST_OK"],
            )
        return SWHRBase.get_device_state(self)

    def get_device_enable(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_device_enable
        return SWHRBase.get_device_enable(self)

    def get_oscillator_period(self, oscillator):
        if self.test_mode:
            if oscillator not in self._sim_osc_period:
                return self.ERR_ARGUMENT, 0
            return self.NO_ERR, self._sim_osc_period[oscillator]
        return SWHRBase.get_oscillator_period(self, oscillator)

    def get_timer_delay(self, timer):
        if self.test_mode:
            if timer not in self._sim_timer_delay:
                return self.ERR_ARGUMENT, 0
            return self.NO_ERR, self._sim_timer_delay[timer]
        return SWHRBase.get_timer_delay(self, timer)

    def get_timer_width(self, timer):
        if self.test_mode:
            if timer not in self._sim_timer_width:
                return self.ERR_ARGUMENT, 0
            return self.NO_ERR, self._sim_timer_width[timer]
        return SWHRBase.get_timer_width(self, timer)

    def get_switch_delay(self, switch_no):
        if self.test_mode:
            if switch_no not in self._sim_switch_delay:
                return self.ERR_ARGUMENT, 0, 0
            rise, fall = self._sim_switch_delay[switch_no]
            return self.NO_ERR, rise, fall
        return SWHRBase.get_switch_delay(self, switch_no)

    def get_switch_rise_delay_fine(self, switch_no):
        if self.test_mode:
            if switch_no not in self._sim_rise_fine:
                return self.ERR_ARGUMENT, 0
            return self.NO_ERR, self._sim_rise_fine[switch_no]
        return SWHRBase.get_switch_rise_delay_fine(self, switch_no)

    def get_switch_fall_delay_fine(self, switch_no):
        if self.test_mode:
            if switch_no not in self._sim_fall_fine:
                return self.ERR_ARGUMENT, 0
            return self.NO_ERR, self._sim_fall_fine[switch_no]
        return SWHRBase.get_switch_fall_delay_fine(self, switch_no)

    # =========================================================================
    #     Curated controls (logging + test-mode simulation)
    # =========================================================================

    def set_device_enable(self, enable):
        """Set the device enable state. Returns the status."""
        self.log_event("info", f"setting device enable to {enable}")
        if self.test_mode:
            self._sim_device_enable = bool(enable)
            return self.NO_ERR
        status = SWHRBase.set_device_enable(self, enable)
        if status != self.NO_ERR:
            self.log_event("error", f"failed to set device enable: status {status}")
        return status

    def set_oscillator_period(self, oscillator, period):
        """Set one oscillator's period register. Returns the status."""
        freq = self.DEF_CLOCK / (period + self.OSC_OFFSET) if period > 0 else 0
        self.log_event(
            "info",
            f"setting oscillator {oscillator} period to {period} (~{freq:.1f} Hz)",
        )
        if self.test_mode:
            if oscillator not in self._sim_osc_period:
                return self.ERR_ARGUMENT
            self._sim_osc_period[oscillator] = int(period)
            return self.NO_ERR
        status = SWHRBase.set_oscillator_period(self, oscillator, period)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to set oscillator {oscillator} period: status {status}",
            )
        return status

    def set_timer_delay(self, timer, delay):
        """Set one timer's delay register. Returns the status."""
        self.log_event("info", f"setting timer {timer} delay to {delay}")
        if self.test_mode:
            if timer not in self._sim_timer_delay:
                return self.ERR_ARGUMENT
            self._sim_timer_delay[timer] = int(delay)
            return self.NO_ERR
        status = SWHRBase.set_timer_delay(self, timer, delay)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set timer {timer} delay: status {status}"
            )
        return status

    def set_timer_width(self, timer, width):
        """Set one timer's width register. Returns the status."""
        self.log_event("info", f"setting timer {timer} width to {width}")
        if self.test_mode:
            if timer not in self._sim_timer_width:
                return self.ERR_ARGUMENT
            self._sim_timer_width[timer] = int(width)
            return self.NO_ERR
        status = SWHRBase.set_timer_width(self, timer, width)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set timer {timer} width: status {status}"
            )
        return status

    def set_switch_delay(self, switch_no, rise_delay, fall_delay):
        """Set one switch's coarse rise/fall delays (5 ns steps).
        Returns the status."""
        self.log_event(
            "info",
            f"setting switch {switch_no} delay: rise={rise_delay}, "
            f"fall={fall_delay}",
        )
        if self.test_mode:
            if switch_no not in self._sim_switch_delay:
                return self.ERR_ARGUMENT
            self._sim_switch_delay[switch_no] = (int(rise_delay), int(fall_delay))
            return self.NO_ERR
        status = SWHRBase.set_switch_delay(self, switch_no, rise_delay, fall_delay)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set switch {switch_no} delay: status {status}"
            )
        return status

    def set_switch_rise_delay_fine(self, switch_no, delay):
        """Set one switch's fine rise delay (11 ps steps, 0 to
        SWITCH_DELAY_FINE_MAX). Returns the status."""
        self.log_event(
            "info", f"setting switch {switch_no} fine rise delay to {delay}"
        )
        if self.test_mode:
            if switch_no not in self._sim_rise_fine:
                return self.ERR_ARGUMENT
            self._sim_rise_fine[switch_no] = int(delay)
            return self.NO_ERR
        status = SWHRBase.set_switch_rise_delay_fine(self, switch_no, delay)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to set switch {switch_no} fine rise delay: "
                f"status {status}",
            )
        return status

    def set_switch_fall_delay_fine(self, switch_no, delay):
        """Set one switch's fine fall delay (11 ps steps). Returns the
        status."""
        self.log_event(
            "info", f"setting switch {switch_no} fine fall delay to {delay}"
        )
        if self.test_mode:
            if switch_no not in self._sim_fall_fine:
                return self.ERR_ARGUMENT
            self._sim_fall_fine[switch_no] = int(delay)
            return self.NO_ERR
        status = SWHRBase.set_switch_fall_delay_fine(self, switch_no, delay)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to set switch {switch_no} fine fall delay: "
                f"status {status}",
            )
        return status

    def load_current_config(self, config_number):
        """Load one NVM config slot (swA's SwitchSym RF ladder: 0=Standby,
        269-277 = 1 kHz - 1 MHz, 279-288 = HF, [[cgc-sw]])."""
        self.log_event("info", f"loading config slot {config_number}")
        if self.test_mode:
            self._sim_config = int(config_number)
            return self.NO_ERR
        status = SWHRBase.load_current_config(self, config_number)
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
        status = SWHRBase.save_current_config(self, config_number)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to save config {config_number}: status {status}"
            )
        return status

    def restart(self):
        """Restart the controller (real hardware only)."""
        self.log_event("info", "restarting SWHR controller")
        status = SWHRBase.restart(self)
        if status != self.NO_ERR:
            self.log_event("error", f"controller restart failed: status {status}")
        return status

    # =========================================================================
    #     Conveniences (work in sim too — the campaign dry-run uses them)
    # =========================================================================

    def set_frequency_khz(self, oscillator, frequency_khz):
        """
        Set one oscillator's frequency in kHz via the period register:
        ``Period_register = DEF_CLOCK / (f_khz * 1000) - OSC_OFFSET``.
        Returns the status.
        """
        if frequency_khz <= 0:
            self.log_event(
                "error", f"invalid frequency: {frequency_khz} kHz (must be > 0)"
            )
            return self.ERR_ARGUMENT
        period = round(self.DEF_CLOCK / (frequency_khz * 1000) - self.OSC_OFFSET)
        if period < 1 or period > 0xFFFFFFFF:
            self.log_event(
                "error",
                f"frequency {frequency_khz} kHz gives out-of-range period "
                f"register {period}",
            )
            return self.ERR_ARGUMENT
        return self.set_oscillator_period(oscillator, period)

    def set_rf(self, frequency_khz, duty=0.5, oscillator=0, timer=0):
        """
        Symmetric frequency move — the timer-width mirror of ``SW.set_rf``
        (the EDH drives its switches from timers, not pulsers; register
        offsets are identical to the ED, [[cgc-sw]]): the NVM configs fix
        the width REGISTER (50 % only at their own period — hardware-
        confirmed in M5-A, where the campaign swept constant ~500 ns
        pulses), so the width must be re-fit after every period change —
        width goes minimal first so width >= period (stuck-HIGH output)
        can never happen mid-move, then the period moves, then the duty
        is re-fit.

        Validates before touching the device: oscillator/timer/duty/
        frequency ranges, the stuck-HIGH trap (current delay 0 with a
        nonzero width) and the monoflop rule
        ``Period+2 > (Delay+3) + (Width+2)`` against the NEW period and
        the CURRENT delay — a violated rule means silently ignored
        triggers ([[cgc-sw]]).

        Each step runs via ``call_with_retry`` (locked, purge-retry on
        EMI serial corruption); the caller must NOT hold ``thread_lock``.
        Returns the first nonzero status, or ``NO_ERR``.
        """
        if oscillator < 0 or oscillator >= self.CLOCK_NUM:
            self.log_event(
                "error",
                f"invalid oscillator number: {oscillator} "
                f"(must be 0-{self.CLOCK_NUM - 1})",
            )
            return self.ERR_ARGUMENT
        if timer < 0 or timer >= self.TIMER_NUM:
            self.log_event(
                "error",
                f"invalid timer number: {timer} "
                f"(must be 0-{self.TIMER_NUM - 1})",
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
        period = round(self.DEF_CLOCK / (frequency_khz * 1000) - self.OSC_OFFSET)
        if period < 1 or period > 0xFFFFFFFF:
            self.log_event(
                "error",
                f"frequency {frequency_khz} kHz gives out-of-range period "
                f"register {period}",
            )
            return self.ERR_ARGUMENT
        width = max(
            1, round(duty * (period + self.OSC_OFFSET) - self.TIMER_WIDTH_OFFSET)
        )
        status, delay = self.call_with_retry(self.get_timer_delay, timer)
        if status != self.NO_ERR:
            return status
        if delay == 0:
            self.log_event(
                "error",
                f"timer {timer} delay register is 0 — a nonzero width "
                "would stick the output HIGH (DC on the load); set a "
                "delay >= 1 first",
            )
            return self.ERR_ARGUMENT
        if (period + self.OSC_OFFSET) <= (
            (delay + self.TIMER_DELAY_OFFSET) + (width + self.TIMER_WIDTH_OFFSET)
        ):
            self.log_event(
                "error",
                f"monoflop rule violated for {frequency_khz} kHz at duty "
                f"{duty}: period+{self.OSC_OFFSET} = {period + self.OSC_OFFSET} "
                f"must exceed (delay+{self.TIMER_DELAY_OFFSET}) + "
                f"(width+{self.TIMER_WIDTH_OFFSET}) = "
                f"{delay + self.TIMER_DELAY_OFFSET + width + self.TIMER_WIDTH_OFFSET}"
                " — triggers would be silently ignored",
            )
            return self.ERR_ARGUMENT
        status = self.call_with_retry(self.set_timer_width, timer, 1)
        if status != self.NO_ERR:
            return status
        status = self.call_with_retry(self.set_frequency_khz, oscillator, frequency_khz)
        if status != self.NO_ERR:
            return status
        return self.call_with_retry(self.set_duty_cycle, timer, duty, oscillator)

    def set_delay_minimum(self, timer):
        """Set one timer's delay to the minimum (register 1 =
        ``(1 + TIMER_DELAY_OFFSET) * 10`` ns). Returns the status."""
        if timer < 0 or timer >= self.TIMER_NUM:
            self.log_event(
                "error",
                f"invalid timer number: {timer} "
                f"(must be 0-{self.TIMER_NUM - 1})",
            )
            return self.ERR_ARGUMENT
        return self.set_timer_delay(timer, 1)

    def set_duty_cycle(self, timer, duty_cycle, oscillator=0):
        """
        Set one timer's duty cycle relative to one oscillator's current
        period: ``Width_register = duty * (Period_register + OSC_OFFSET)
        - TIMER_WIDTH_OFFSET``. Returns the status.
        """
        if timer < 0 or timer >= self.TIMER_NUM:
            self.log_event(
                "error",
                f"invalid timer number: {timer} "
                f"(must be 0-{self.TIMER_NUM - 1})",
            )
            return self.ERR_ARGUMENT
        if duty_cycle <= 0.0 or duty_cycle >= 1.0:
            self.log_event(
                "error",
                f"invalid duty cycle: {duty_cycle} "
                "(must be in exclusive range 0.0 to 1.0)",
            )
            return self.ERR_ARGUMENT
        status, period = self.get_oscillator_period(oscillator)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to read oscillator period: status {status}"
            )
            return status
        width = duty_cycle * (period + self.OSC_OFFSET) - self.TIMER_WIDTH_OFFSET
        width = max(1, round(width))
        return self.set_timer_width(timer, width)
