"""
AMPR (AMPR-12 amplifier) device controller on the shared CGC lab layer.

``AMPR`` combines the pure ctypes wrapper (``AMPRBase``) with ``CGCDevice``
(canonical log line, telemetry sink, housekeeping worker + poke,
responding/reconnect, explicit test mode). Both lab units (AMPR1000 and
AMPR500) are AMPR-12 hardware and use this one class.

The AMPR-12 manages up to 12 modules, each holding up to 4 individual
voltage supplies.
"""
from typing import Optional
import logging
import threading

from ..cgc_device import CGCDevice
from .ampr_base import AMPRBase


class AMPR(CGCDevice, AMPRBase):
    """
    AMPR-12 amplifier with canonical logging, telemetry and test mode.

    Curated high-level methods (simulated in test mode): housekeeping
    reads, state reads, ``enable_psu()``, ``set_module_voltage()``,
    ``get_module_voltages()``, ``get_measured_module_output_voltages()``.
    Raw DLL exports are real-hardware-only.

    Example:
        ampr = AMPR("AMPR1000", com=8, sink=sink)
        ampr.connect()
        ampr.start_housekeeping()
        ampr.set_module_voltage(0, 1, 12.5)
        ampr.disconnect()
    """

    FAMILY = "AMPR"
    DLL_BASE = AMPRBase

    def __init__(
        self,
        device_id: str,
        com: int,
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
        Initialize an AMPR-12 device (see ``CGCDevice.__init__`` for the
        shared parameters). In test mode the vendor DLL is never loaded.
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
        # Simulated state (test mode only): PSU enable flag and per-
        # (address, channel) voltage setpoints.
        self._sim_psu_enabled = False
        self._sim_voltages = {}
        if not test_mode:
            AMPRBase.__init__(self, com=com, log=None, idn=device_id)

    # =========================================================================
    #     Transport (bring-up sequence; reconnect() re-runs it)
    # =========================================================================

    def _open_transport(self) -> None:
        """AMPR bring-up: open the DLL port, then negotiate the baud rate
        (a baud failure is a warning, the device stays usable at its
        default — matches established notebook behavior)."""
        self._check(self.open_port(self.com), "open_port")
        baud_status, actual_baud = self.set_baud_rate(self.baudrate)
        if baud_status == self.NO_ERR:
            self.log_event("info", f"baud rate set to {actual_baud}")
        else:
            self.log_event(
                "warning",
                f"set_baud_rate returned {baud_status}; continuing at device default",
            )

    # =========================================================================
    #     Housekeeping (one canonical log_sample() line per channel)
    # =========================================================================

    def hk_monitor(self) -> None:
        """One housekeeping cycle: controller rails/temps, states, fan,
        CPU and module presence. Blocks are individually guarded so one
        failing read does not silence the others."""
        with self.thread_lock:
            for block in (
                self._hk_general_housekeeping,
                self._hk_states,
                self._hk_fan,
                self._hk_cpu,
                self._hk_modules,
            ):
                try:
                    block()
                except Exception as e:
                    self.log_event(
                        "error", f"housekeeping block {block.__name__} failed: {e}"
                    )

    def _hk_general_housekeeping(self):
        (status, volt_12v, volt_5v0, volt_3v3, volt_agnd, volt_12vp, volt_12vn,
         volt_hvp, volt_hvn, temp_cpu, temp_adc, temp_av, temp_hvp, temp_hvn,
         line_freq) = self.get_housekeeping()
        if status != self.NO_ERR:
            self.log_event("warning", f"get_housekeeping returned {status}")
            return
        self.log_sample("Volt_12V", volt_12v, "V", ".2f")
        self.log_sample("Volt_5V0", volt_5v0, "V", ".2f")
        self.log_sample("Volt_3V3", volt_3v3, "V", ".2f")
        self.log_sample("Volt_AGND", volt_agnd, "V", ".2f")
        self.log_sample("Volt_12Va_P", volt_12vp, "V", ".2f")
        self.log_sample("Volt_12Va_N", volt_12vn, "V", ".2f")
        self.log_sample("Volt_HV_P", volt_hvp, "V", ".2f")
        self.log_sample("Volt_HV_N", volt_hvn, "V", ".2f")
        self.log_sample("Temp_CPU", temp_cpu, "degC", ".1f")
        self.log_sample("Temp_ADC", temp_adc, "degC", ".1f")
        self.log_sample("Temp_AV", temp_av, "degC", ".1f")
        self.log_sample("Temp_HV_P", temp_hvp, "degC", ".1f")
        self.log_sample("Temp_HV_N", temp_hvn, "degC", ".1f")
        self.log_sample("Line_Freq", line_freq, "Hz", ".1f")

    def _hk_states(self):
        status, state_hex, state_name = self.get_state()
        if status == self.NO_ERR:
            self.log_sample("Main_State", state_name)
        status, state_hex, names = self.get_device_state()
        if status == self.NO_ERR:
            self.log_sample("Device_State", ", ".join(names))
            self.log_sample("PSU_Enabled", 1 if int(state_hex, 16) & 1 else 0)
        status, state_hex, names = self.get_voltage_state()
        if status == self.NO_ERR:
            self.log_sample("Voltage_State", ", ".join(names))
        status, state_hex, names = self.get_temperature_state()
        if status == self.NO_ERR:
            self.log_sample("Temperature_State", ", ".join(names))
        status, state_hex, names = self.get_interlock_state()
        if status == self.NO_ERR:
            self.log_sample("Interlock_State", ", ".join(names))

    def _hk_fan(self):
        status, failed, max_rpm, set_rpm, measured_rpm, pwm = self.get_fan_data()
        if status == self.NO_ERR:
            self.log_sample("Fan_RPM", measured_rpm, "rpm")
            if failed:
                self.log_event("warning", "fan reports FAILED")

    def _hk_cpu(self):
        status, load, frequency = self.get_cpu_data()
        if status == self.NO_ERR:
            self.log_sample("CPU_Load", load * 100, "%", ".1f")

    def _hk_modules(self):
        status, valid, max_module, presence_list = self.get_module_presence()
        if status == self.NO_ERR:
            present = [
                i for i, p in enumerate(presence_list) if p == self.MODULE_PRESENT
            ]
            self.log_sample("Modules_Present", len(present))

    # =========================================================================
    #     Curated reads (simulated in test mode)
    # =========================================================================

    def get_housekeeping(self):
        if self.test_mode:
            return (
                self.NO_ERR,
                self._sim_uniform(11.8, 12.2),    # volt_12v
                self._sim_uniform(4.9, 5.1),      # volt_5v0
                self._sim_uniform(3.25, 3.35),    # volt_3v3
                self._sim_uniform(-0.05, 0.05),   # volt_agnd
                self._sim_uniform(11.8, 12.2),    # volt_12vp
                self._sim_uniform(-12.2, -11.8),  # volt_12vn
                self._sim_uniform(495.0, 505.0),  # volt_hvp
                self._sim_uniform(-505.0, -495.0),  # volt_hvn
                self._sim_uniform(35.0, 45.0, 1),   # temp_cpu
                self._sim_uniform(30.0, 40.0, 1),   # temp_adc
                self._sim_uniform(30.0, 40.0, 1),   # temp_av
                self._sim_uniform(30.0, 40.0, 1),   # temp_hvp
                self._sim_uniform(30.0, 40.0, 1),   # temp_hvn
                self._sim_uniform(49.9, 50.1, 1),   # line_freq
            )
        return AMPRBase.get_housekeeping(self)

    def get_state(self):
        if self.test_mode:
            value = 0 if self._sim_psu_enabled else 2
            return self.NO_ERR, hex(value), self.MAIN_STATE[value]
        return AMPRBase.get_state(self)

    def get_device_state(self):
        if self.test_mode:
            value = 1 if self._sim_psu_enabled else 0
            names = ["DS_PSU_ENB"] if self._sim_psu_enabled else ["DEVICE_OK"]
            return self.NO_ERR, hex(value), names
        return AMPRBase.get_device_state(self)

    def get_voltage_state(self):
        if self.test_mode:
            return self.NO_ERR, hex(0), ["VOLTAGE_OK"]
        return AMPRBase.get_voltage_state(self)

    def get_temperature_state(self):
        if self.test_mode:
            return self.NO_ERR, hex(0), ["TEMPERATURE_OK"]
        return AMPRBase.get_temperature_state(self)

    def get_interlock_state(self):
        if self.test_mode:
            value = 1 << 0xF  # SI_ILOCK_ENB
            return self.NO_ERR, hex(value), ["SI_ILOCK_ENB"]
        return AMPRBase.get_interlock_state(self)

    def get_fan_data(self):
        if self.test_mode:
            rpm = int(self._sim_uniform(2900, 3100, 0))
            return self.NO_ERR, False, 6000, 3000, rpm, 5000
        return AMPRBase.get_fan_data(self)

    def get_cpu_data(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_uniform(0.05, 0.20, 3), 168e6
        return AMPRBase.get_cpu_data(self)

    def get_module_presence(self):
        if self.test_mode:
            presence = [self.MODULE_NOT_FOUND] * (self.MODULE_NUM + 1)
            for addr in (0, 1, 2):
                presence[addr] = self.MODULE_PRESENT
            return self.NO_ERR, True, 2, presence
        return AMPRBase.get_module_presence(self)

    def get_measured_module_output_voltages(self, address):
        if self.test_mode:
            voltages = [
                self._sim_voltages.get((address, ch), 0.0)
                + self._sim_uniform(-0.05, 0.05, 3)
                for ch in range(self.MODULE_CHANNEL_NUM)
            ]
            return self.NO_ERR, voltages
        return AMPRBase.get_measured_module_output_voltages(self, address)

    def get_module_output_voltage(self, address, channel):
        if self.test_mode:
            return self.NO_ERR, self._sim_voltages.get((address, channel), 0.0)
        return AMPRBase.get_module_output_voltage(self, address, channel)

    # =========================================================================
    #     Curated controls (logging + test-mode simulation)
    # =========================================================================

    def enable_psu(self, enable):
        """Enable/disable the HV PSUs. Returns (status, enable_value)."""
        self.log_event("info", f"setting PSU enable to {enable}")
        if self.test_mode:
            self._sim_psu_enabled = bool(enable)
            return self.NO_ERR, bool(enable)
        status, enable_value = AMPRBase.enable_psu(self, enable)
        if status == self.NO_ERR:
            self.log_event("info", f"PSU enable set to {enable_value}")
        else:
            self.log_event("error", f"failed to set PSU enable: status {status}")
        return status, enable_value

    def set_module_voltage(self, address, channel, voltage):
        """Set one module output voltage. Returns the DLL status code."""
        self.log_event(
            "info",
            f"setting module {address} channel {channel} voltage to {voltage:.3f} V",
        )
        if self.test_mode:
            self._sim_voltages[(address, channel)] = float(voltage)
            return self.NO_ERR
        status = AMPRBase.set_module_output_voltage(self, address, channel, voltage)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to set module {address} channel {channel} voltage: "
                f"status {status}",
            )
        return status

    def get_module_voltages(self, address):
        """All channels of one module as {channel: {'setpoint', 'measured'}}."""
        if self.test_mode:
            meas_status, measured = self.get_measured_module_output_voltages(address)
            return {
                ch: {
                    "setpoint": self._sim_voltages.get((address, ch), 0.0),
                    "measured": measured[ch],
                }
                for ch in range(self.MODULE_CHANNEL_NUM)
            }
        return AMPRBase.get_all_module_voltages(self, address)

    def set_module_voltages(self, address, voltages):
        """Set several channels of one module (list or {channel: voltage})."""
        if self.test_mode:
            results = {}
            items = (
                enumerate(voltages[: self.MODULE_CHANNEL_NUM])
                if isinstance(voltages, list)
                else voltages.items()
            )
            for channel, voltage in items:
                if voltage is not None and 0 <= channel < self.MODULE_CHANNEL_NUM:
                    results[channel] = self.set_module_voltage(
                        address, channel, voltage
                    )
            return results
        results = AMPRBase.set_all_module_voltages(self, address, voltages)
        for channel, status in results.items():
            if status != self.NO_ERR:
                self.log_event(
                    "error",
                    f"failed to set module {address} channel {channel}: "
                    f"status {status}",
                )
        return results

    # =========================================================================
    #     Convenience (real-hardware-only)
    # =========================================================================

    def scan_modules(self):
        """Scan all connected modules and log what was found."""
        modules = AMPRBase.scan_all_modules(self)
        if modules:
            for addr, info in modules.items():
                self.logger.info(
                    f"{self._prefix()}module {addr}: "
                    f"product {info.get('product_no', '?')}, "
                    f"FW {info.get('fw_version', '?')}, "
                    f"state {info.get('state', '?')}"
                )
        else:
            self.log_event("warning", "no modules found")
        return modules

    def get_module_info(self, address):
        """Detailed info dict for one module (ids, housekeeping, voltages)."""
        info = {}
        status, product_no = AMPRBase.get_module_product_no(self, address)
        if status == self.NO_ERR:
            info["product_no"] = product_no
        status, fw_version = AMPRBase.get_module_fw_version(self, address)
        if status == self.NO_ERR:
            info["fw_version"] = fw_version
        status, hw_type = AMPRBase.get_module_hw_type(self, address)
        if status == self.NO_ERR:
            info["hw_type"] = hw_type
        status, hw_version = AMPRBase.get_module_hw_version(self, address)
        if status == self.NO_ERR:
            info["hw_version"] = hw_version
        status, state = AMPRBase.get_module_state(self, address)
        if status == self.NO_ERR:
            info["state"] = state
        hk = AMPRBase.get_module_housekeeping(self, address)
        if hk[0] == self.NO_ERR:
            info["housekeeping"] = {
                "volt_24vp": hk[1], "volt_24vn": hk[2],
                "volt_12vp": hk[3], "volt_12vn": hk[4],
                "volt_5v0": hk[5], "volt_3v3": hk[6],
                "temp_psu": hk[7], "temp_board": hk[8],
                "volt_ref": hk[9],
            }
        info["voltages"] = self.get_module_voltages(address)
        return info

    def restart(self):
        """Restart the controller."""
        self.log_event("info", "restarting AMPR controller")
        status = AMPRBase.restart(self)
        if status != self.NO_ERR:
            self.log_event("error", f"controller restart failed: status {status}")
        return status

    def restart_module(self, address):
        """Restart one module."""
        self.log_event("info", f"restarting module {address}")
        status = AMPRBase.restart_module(self, address)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"module {address} restart failed: status {status}"
            )
        return status
