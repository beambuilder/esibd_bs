"""
pA (Picoammeter DMMR-8) device controller on the shared CGC lab layer.

``PA`` combines the pure ctypes wrapper (``PABase``) with ``CGCDevice``
(canonical log line, telemetry sink, housekeeping worker + poke,
responding/reconnect, explicit test mode).

The DMMR-8 manages up to 8 DPA-1F current-measurement modules; the lab
unit has 5 populated modules on addresses 0-4.

Bring-up order is STRICT (notebook 017, [[cgc-pa]]) and lives in
``_open_transport()`` so ``reconnect()`` re-runs it correctly:
open_port -> set_baud_rate -> set_enable(True) -> set_automatic_current(True).
"""
from typing import Optional
import logging
import threading
import time

from ..cgc_device import CGCDevice
from .pA_base import PABase

#: Module addresses simulated in test mode (the lab's populated slots).
SIM_MODULES = (0, 1, 2, 3, 4)


class PA(CGCDevice, PABase):
    """
    DMMR-8 picoammeter with canonical logging, telemetry and test mode.

    Curated high-level methods (simulated in test mode): housekeeping
    reads, state reads, ``set_enable()``/``get_enable()``,
    ``set_automatic_current()``/``get_automatic_current()``,
    ``get_current()``, ``get_module_current()``. Raw DLL exports are
    real-hardware-only.

    Example:
        pa = PA("dmmr8_esibd", com=7, sink=sink)
        pa.connect()          # runs the full strict bring-up
        pa.start_housekeeping()
        status, addr, current, meas_range, t = pa.get_current()
        pa.disconnect()
    """

    FAMILY = "PA"
    DLL_BASE = PABase

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
        Initialize a DMMR-8 device (see ``CGCDevice.__init__`` for the
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
        # Simulated state (test mode only): enable flags and the get_current
        # drain queue (each cycle serves every module once, then NO_DATA).
        self._sim_enabled = False
        self._sim_auto_current = False
        self._sim_current_queue = list(SIM_MODULES)
        if not test_mode:
            PABase.__init__(self, com=com, log=None, idn=device_id)

    # =========================================================================
    #     Transport (STRICT bring-up order; reconnect() re-runs it)
    # =========================================================================

    def _open_transport(self) -> None:
        """DMMR-8 bring-up, strict order (notebook 017): open_port ->
        set_baud_rate -> set_enable(True) -> set_automatic_current(True).
        A baud failure is a warning; any other failure closes the port
        best-effort and raises."""
        self._check(self.open_port(self.com), "open_port")
        try:
            baud_status, actual_baud = self.set_baud_rate(self.baudrate)
            if baud_status == self.NO_ERR:
                self.log_event("info", f"baud rate set to {actual_baud}")
            else:
                self.log_event(
                    "warning",
                    f"set_baud_rate returned {baud_status}; "
                    "continuing at device default",
                )
            self._check(self.set_enable(True), "set_enable(True)")
            self._check(
                self.set_automatic_current(True), "set_automatic_current(True)"
            )
        except Exception:
            # Leave no half-initialized open port behind.
            try:
                self.close_port()
            except Exception:
                pass
            raise

    # =========================================================================
    #     Housekeeping (one canonical log_sample() line per channel)
    # =========================================================================

    def hk_monitor(self) -> None:
        """One housekeeping cycle: controller rails/temp, base device,
        fan, CPU, states and module presence. Blocks are individually
        guarded so one failing read does not silence the others."""
        with self.thread_lock:
            for block in (
                self._hk_general_housekeeping,
                self._hk_base,
                self._hk_fan,
                self._hk_cpu,
                self._hk_states,
                self._hk_modules,
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

    def _hk_base(self):
        status, base_temp = self.get_base_temp()
        if status == self.NO_ERR:
            self.log_sample("Base_Temp", base_temp, "degC", ".1f")

    def _hk_fan(self):
        status, rpm = self.get_base_fan_rpm()
        if status == self.NO_ERR:
            self.log_sample("Fan_RPM", rpm, "rpm", ".0f")

    def _hk_cpu(self):
        status, load, frequency = self.get_cpu_data()
        if status == self.NO_ERR:
            self.log_sample("CPU_Load", load * 100, "%", ".1f")

    def _hk_states(self):
        status, state_hex, state_name = self.get_state()
        if status == self.NO_ERR:
            self.log_sample("Main_State", state_name)
        status, state_hex, names = self.get_device_state()
        if status == self.NO_ERR:
            self.log_sample("Device_State", ", ".join(names))
        status, enabled = self.get_enable()
        if status == self.NO_ERR:
            self.log_sample("Enabled", 1 if enabled else 0)

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
                self._sim_uniform(11.8, 12.2),   # volt_12v
                self._sim_uniform(4.9, 5.1),     # volt_5v0
                self._sim_uniform(3.25, 3.35),   # volt_3v3
                self._sim_uniform(30.0, 40.0, 1),  # temp_cpu
            )
        return PABase.get_housekeeping(self)

    def get_base_temp(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_uniform(25.0, 35.0, 1)
        return PABase.get_base_temp(self)

    def get_base_fan_rpm(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_uniform(2400, 2600, 0)
        return PABase.get_base_fan_rpm(self)

    def get_cpu_data(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_uniform(0.05, 0.20, 3), 168e6
        return PABase.get_cpu_data(self)

    def get_state(self):
        if self.test_mode:
            return self.NO_ERR, hex(0), self.MAIN_STATE[0]  # ST_ON
        return PABase.get_state(self)

    def get_device_state(self):
        if self.test_mode:
            value = 1 if self._sim_enabled else 0
            names = ["DS_PSU_ENB"] if self._sim_enabled else ["DEVICE_OK"]
            return self.NO_ERR, hex(value), names
        return PABase.get_device_state(self)

    def get_module_presence(self):
        if self.test_mode:
            presence = [self.MODULE_NOT_FOUND] * self.MODULE_NUM
            for addr in SIM_MODULES:
                presence[addr] = self.MODULE_PRESENT
            return self.NO_ERR, True, max(SIM_MODULES), presence
        return PABase.get_module_presence(self)

    def _sim_module_current(self, address):
        """Plausible per-module current in A (~pA scale, address-keyed)."""
        return self._sim_uniform(
            (address + 1) * 0.8, (address + 1) * 1.2, 3
        ) * 1e-12

    def get_current(self):
        """
        Poll for new automatic current data: (status, address, current [A],
        meas_range, timestamp). In test mode each drain cycle serves every
        simulated module once, then returns NO_DATA and refills — mirrors
        the plugin's poll-until-NO_DATA read loop.
        """
        if self.test_mode:
            if not self._sim_current_queue:
                self._sim_current_queue = list(SIM_MODULES)
                return self.NO_DATA, 0, 0.0, 0, 0.0
            address = self._sim_current_queue.pop(0)
            return (
                self.NO_ERR,
                address,
                self._sim_module_current(address),
                2,
                time.time(),
            )
        return PABase.get_current(self)

    def get_module_current(self, address):
        if self.test_mode:
            return self.NO_ERR, self._sim_module_current(address), 2
        return PABase.get_module_current(self, address)

    def get_enable(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_enabled
        return PABase.get_enable(self)

    def get_automatic_current(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_auto_current
        return PABase.get_automatic_current(self)

    # =========================================================================
    #     Curated controls (logging + test-mode simulation)
    # =========================================================================

    def set_enable(self, enable):
        """Enable/disable the DPA-1F modules. Returns the DLL status code."""
        self.log_event("info", f"setting module enable to {enable}")
        if self.test_mode:
            self._sim_enabled = bool(enable)
            return self.NO_ERR
        status = PABase.set_enable(self, enable)
        if status != self.NO_ERR:
            self.log_event("error", f"failed to set module enable: status {status}")
        return status

    def set_automatic_current(self, automatic_current):
        """Enable/disable automatic current measurement. Returns the status."""
        self.log_event(
            "info", f"setting automatic current measurement to {automatic_current}"
        )
        if self.test_mode:
            self._sim_auto_current = bool(automatic_current)
            return self.NO_ERR
        status = PABase.set_automatic_current(self, automatic_current)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set automatic current: status {status}"
            )
        return status

    # =========================================================================
    #     Convenience (real-hardware-only)
    # =========================================================================

    def scan_modules(self):
        """Scan all connected modules and log what was found."""
        modules = PABase.scan_all_modules(self)
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
        """Detailed info dict for one module (ids, housekeeping, current)."""
        info = {}
        status, product_no = PABase.get_module_product_no(self, address)
        if status == self.NO_ERR:
            info["product_no"] = product_no
        status, fw_version = PABase.get_module_fw_version(self, address)
        if status == self.NO_ERR:
            info["fw_version"] = fw_version
        status, hw_type = PABase.get_module_hw_type(self, address)
        if status == self.NO_ERR:
            info["hw_type"] = hw_type
        status, hw_version = PABase.get_module_hw_version(self, address)
        if status == self.NO_ERR:
            info["hw_version"] = hw_version
        status, state = PABase.get_module_state(self, address)
        if status == self.NO_ERR:
            info["state"] = state
        hk = PABase.get_module_housekeeping(self, address)
        if hk[0] == self.NO_ERR:
            info["housekeeping"] = {
                "volt_3v3": hk[1], "temp_cpu": hk[2],
                "volt_5v0": hk[3], "volt_12v": hk[4],
                "volt_3v3i": hk[5], "temp_cpui": hk[6],
                "volt_2v5i": hk[7], "volt_36vn": hk[8],
                "volt_20vp": hk[9], "volt_20vn": hk[10],
                "volt_15vp": hk[11], "volt_15vn": hk[12],
                "volt_1v8p": hk[13], "volt_1v8n": hk[14],
                "volt_vrefp": hk[15], "volt_vrefn": hk[16],
            }
        cur_status, meas_current, meas_range = self.get_module_current(address)
        if cur_status == self.NO_ERR:
            info["current"] = {"value": meas_current, "range": meas_range}
        return info

    def restart(self):
        """Restart the controller."""
        self.log_event("info", "restarting DMMR-8 controller")
        status = PABase.restart(self)
        if status != self.NO_ERR:
            self.log_event("error", f"controller restart failed: status {status}")
        return status

    def restart_module(self, address):
        """Restart one module."""
        self.log_event("info", f"restarting module {address}")
        status = PABase.restart_module(self, address)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"module {address} restart failed: status {status}"
            )
        return status
