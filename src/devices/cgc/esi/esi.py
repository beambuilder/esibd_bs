"""
ESI controller (electrospray HV supply) on the shared CGC lab layer.

``ESI`` combines the pure ctypes wrapper (``ESIBase``) with ``CGCDevice``
(canonical log line, telemetry sink, housekeeping worker + poke,
responding/reconnect, explicit test mode).

The controller carries up to 4 modules (HV supplies + optionally the heat
controller on address 0); the lab uses HV modules on addresses 2 and 3
(notebook 024, [[cgc-esi]]). Heat-controller functions stay raw DLL
exports (out of scope until a lab use case exists).

Bring-up (notebook 024) lives in ``_open_transport()`` so ``reconnect()``
re-runs it: open_port -> set_comspeed -> set_enable(True). Module
activation and target voltages are operator actions and never part of
bring-up.

SINGLE-INSTANCE: unlike the other CGC DLLs the ESI-CTRL exports take no
port argument — one ESI controller per process, enforced by a class-level
guard on connect (second connect logs an error and returns False). Never
run the Explorer ESI plugin and an ESI notebook simultaneously.
"""
from typing import Optional
import logging
import threading

from ..cgc_device import CGCDevice
from .esi_base import ESIBase

#: HV-module addresses simulated in test mode (the lab's populated slots).
SIM_MODULES = (2, 3)


class ESI(CGCDevice, ESIBase):
    """
    ESI controller with canonical logging, telemetry and test mode.

    Curated high-level methods (simulated in test mode): housekeeping
    reads, state reads, ``set_enable()``/``get_enable()``,
    ``set_activation_state()``/``get_activation_state()``,
    ``set_module_activation_state()``/``get_module_activation_state()``,
    HV target voltage set/read and V/I readback. Raw DLL exports are
    real-hardware-only.

    Example:
        esi = ESI("ESI", com=14, sink=sink)
        esi.connect()          # open + comspeed + enable (single-instance guard)
        esi.set_module_activation_state(2, True)
        esi.set_hv_supply_target_output_voltage(2, 300.0)
        status, valid, volts = esi.get_hv_supply_output_voltage(2)
        esi.disconnect()
    """

    FAMILY = "ESI"
    DLL_BASE = ESIBase

    #: Process-wide single-instance guard: the ESI-CTRL DLL has ONE
    #: implicit communication channel (no port handles), so only one
    #: connected ESI instance may exist per process.
    _instance_lock = threading.Lock()
    _connected_instance = None  # device_id currently holding the DLL channel

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
        Initialize an ESI controller (see ``CGCDevice.__init__`` for the
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
        # Simulated state (test mode only): enable/activation flags and
        # per-module HV targets; the readback tracks the target when the
        # module is activated.
        self._sim_enabled = False
        self._sim_activated = False
        self._sim_module_active = {addr: False for addr in SIM_MODULES}
        self._sim_hv_target = {addr: 0.0 for addr in SIM_MODULES}
        if not test_mode:
            ESIBase.__init__(self, com=com, log=None, idn=device_id)

    # =========================================================================
    #     Transport (nb-024 bring-up; reconnect() re-runs it)
    # =========================================================================

    def _open_transport(self) -> None:
        """ESI bring-up (notebook 024): claim the single-instance slot,
        then open_port -> set_comspeed -> set_enable(True). A comspeed
        failure is a warning; any other failure releases the slot, closes
        the port best-effort and raises."""
        with ESI._instance_lock:
            holder = ESI._connected_instance
            if holder is not None and holder is not self:
                raise RuntimeError(
                    "ESI-CTRL DLL is single-instance per process: "
                    f"'{holder.device_id}' already holds the channel "
                    "(close it first; never run plugin + notebook together)"
                )
            ESI._connected_instance = self
        try:
            self._check(self.open_port(self.com), "open_port")
            try:
                baud_status, actual_baud = self.set_comspeed(self.baudrate)
                if baud_status == self.NO_ERR:
                    self.log_event("info", f"comspeed set to {actual_baud}")
                else:
                    self.log_event(
                        "warning",
                        f"set_comspeed returned {baud_status}; "
                        "continuing at device default",
                    )
                self._check(self.set_enable(True), "set_enable(True)")
            except Exception:
                # Leave no half-initialized open port behind.
                try:
                    self.close_port()
                except Exception:
                    pass
                raise
        except Exception:
            with ESI._instance_lock:
                if ESI._connected_instance is self:
                    ESI._connected_instance = None
            raise

    def _close_transport(self) -> None:
        """Best-effort close, then release the single-instance slot."""
        try:
            CGCDevice._close_transport(self)
        finally:
            with ESI._instance_lock:
                if ESI._connected_instance is self:
                    ESI._connected_instance = None

    # =========================================================================
    #     Housekeeping (one canonical log_sample() line per channel)
    # =========================================================================

    def hk_monitor(self) -> None:
        """One housekeeping cycle: controller rails/temps, CPU, fan,
        states and HV modules. Blocks are individually guarded so one
        failing read does not silence the others."""
        with self.thread_lock:
            for block in (
                self._hk_general_housekeeping,
                self._hk_cpu,
                self._hk_fan,
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
        status, v24, v5, v3, tcpu, tpsu = self.get_housekeeping()
        if status != self.NO_ERR:
            self.log_event("warning", f"get_housekeeping returned {status}")
            return
        self.log_sample("Volt_24V", v24, "V", ".2f")
        self.log_sample("Volt_5V0", v5, "V", ".2f")
        self.log_sample("Volt_3V3", v3, "V", ".2f")
        self.log_sample("Temp_CPU", tcpu, "degC", ".1f")
        self.log_sample("Temp_PSU", tpsu, "degC", ".1f")

    def _hk_cpu(self):
        status, load, frequency = self.get_cpu_data()
        if status == self.NO_ERR:
            self.log_sample("CPU_Load", load * 100, "%", ".1f")

    def _hk_fan(self):
        status, failed, max_rpm, set_rpm, meas_rpm, pwm = self.get_fan_data()
        if status == self.NO_ERR:
            self.log_sample("Fan_RPM", meas_rpm, "rpm", ".0f")

    def _hk_states(self):
        status, state_hex, state_name = self.get_main_state()
        if status == self.NO_ERR:
            self.log_sample("Main_State", state_name)
        status, state_hex, names = self.get_device_state()
        if status == self.NO_ERR:
            self.log_sample("Device_State", ", ".join(names))
        status, enabled = self.get_enable()
        if status == self.NO_ERR:
            self.log_sample("Enabled", 1 if enabled else 0)
        status, activated = self.get_activation_state()
        if status == self.NO_ERR:
            self.log_sample("Activated", 1 if activated else 0)

    def _hk_modules(self):
        status, valid, max_module, presence = self.get_module_presence()
        if status != self.NO_ERR:
            return
        hv_addresses = [
            addr for addr in range(self.MODULE_NUM)
            if presence[addr] == self.MODULE_PRESENT
        ]
        self.log_sample("Modules_Present", len(hv_addresses))
        # Per-module V/I readback; a non-HV module (heat controller on
        # address 0) simply fails its reads and is skipped.
        for addr in hv_addresses:
            try:
                st, valid_v, volts = self.get_hv_supply_output_voltage(addr)
                if st == self.NO_ERR and valid_v:
                    self.log_sample(f"HV{addr}_Voltage", volts, "V", ".2f")
                st, valid_i, amps = self.get_hv_supply_output_current(addr)
                if st == self.NO_ERR and valid_i:
                    self.log_sample(f"HV{addr}_Current", amps, "A", ".3e")
            except Exception as e:
                self.log_event("warning", f"HV module {addr} read failed: {e}")

    # =========================================================================
    #     Curated reads (simulated in test mode)
    # =========================================================================

    def get_housekeeping(self):
        if self.test_mode:
            return (
                self.NO_ERR,
                self._sim_uniform(23.5, 24.5),   # volt_24v
                self._sim_uniform(4.9, 5.1),     # volt_5v0
                self._sim_uniform(3.25, 3.35),   # volt_3v3
                self._sim_uniform(30.0, 40.0, 1),  # temp_cpu
                self._sim_uniform(28.0, 38.0, 1),  # temp_psu
            )
        return ESIBase.get_housekeeping(self)

    def get_cpu_data(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_uniform(0.05, 0.20, 3), 168e6
        return ESIBase.get_cpu_data(self)

    def get_fan_data(self):
        if self.test_mode:
            rpm = self._sim_uniform(2400, 2600, 0)
            return self.NO_ERR, False, 6000, 2500, rpm, 0.42
        return ESIBase.get_fan_data(self)

    def get_main_state(self):
        if self.test_mode:
            return self.NO_ERR, hex(0), self.MAIN_STATE[0]  # STATE_ON
        return ESIBase.get_main_state(self)

    def get_device_state(self):
        if self.test_mode:
            return self.NO_ERR, hex(0), ["DEVST_OK"]
        return ESIBase.get_device_state(self)

    def get_module_presence(self):
        if self.test_mode:
            presence = [self.MODULE_NOT_FOUND] * (self.MODULE_NUM + 1)
            for addr in SIM_MODULES:
                presence[addr] = self.MODULE_PRESENT
            presence[self.PRESENCE_BASE] = self.MODULE_PRESENT
            return self.NO_ERR, True, max(SIM_MODULES), presence
        return ESIBase.get_module_presence(self)

    def get_enable(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_enabled
        return ESIBase.get_enable(self)

    def get_activation_state(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_activated
        return ESIBase.get_activation_state(self)

    def get_module_activation_state(self, address):
        if self.test_mode:
            return self.NO_ERR, self._sim_module_active.get(address, False)
        return ESIBase.get_module_activation_state(self, address)

    def get_hv_supply_target_output_voltage(self, address):
        if self.test_mode:
            return self.NO_ERR, self._sim_hv_target.get(address, 0.0)
        return ESIBase.get_hv_supply_target_output_voltage(self, address)

    def get_hv_supply_output_voltage(self, address):
        """Returns (status, valid, voltage). Simulated readback tracks the
        target (small noise) while the module is activated, 0 V otherwise
        — mirrors notebook 024's set-then-monitor pattern."""
        if self.test_mode:
            if address not in self._sim_hv_target:
                return self.ERR_ARGUMENT, False, 0.0
            if self._sim_module_active.get(address) and self._sim_activated:
                target = self._sim_hv_target[address]
                noise = self._sim_uniform(-0.5, 0.5)
                return self.NO_ERR, True, target + noise
            return self.NO_ERR, True, 0.0
        return ESIBase.get_hv_supply_output_voltage(self, address)

    def get_hv_supply_output_current(self, address):
        """Returns (status, valid, current [A]); nb-024 real currents sit
        in the 1e-10 A range."""
        if self.test_mode:
            if address not in self._sim_hv_target:
                return self.ERR_ARGUMENT, False, 0.0
            if self._sim_module_active.get(address) and self._sim_activated:
                return self.NO_ERR, True, self._sim_uniform(0.8, 1.2, 3) * 1e-10
            return self.NO_ERR, True, 0.0
        return ESIBase.get_hv_supply_output_current(self, address)

    # =========================================================================
    #     Curated controls (logging + test-mode simulation)
    # =========================================================================

    def set_enable(self, enable):
        """Enable/disable the modules. Returns the DLL status code."""
        self.log_event("info", f"setting module enable to {enable}")
        if self.test_mode:
            self._sim_enabled = bool(enable)
            return self.NO_ERR
        status = ESIBase.set_enable(self, enable)
        if status != self.NO_ERR:
            self.log_event("error", f"failed to set module enable: status {status}")
        return status

    def set_activation_state(self, activation_state):
        """Set device activation state (HV on/off). Returns the status."""
        self.log_event("info", f"setting activation state to {activation_state}")
        if self.test_mode:
            self._sim_activated = bool(activation_state)
            return self.NO_ERR
        status = ESIBase.set_activation_state(self, activation_state)
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set activation state: status {status}"
            )
        return status

    def set_module_activation_state(self, address, activation_state):
        """Set one module's activation state. Returns the status."""
        self.log_event(
            "info", f"setting module {address} activation to {activation_state}"
        )
        if self.test_mode:
            self._sim_module_active[address] = bool(activation_state)
            return self.NO_ERR
        status = ESIBase.set_module_activation_state(self, address, activation_state)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to set module {address} activation: status {status}",
            )
        return status

    def set_hv_supply_target_output_voltage(self, address, voltage):
        """Set one HV module's target output voltage. Returns the status."""
        self.log_event(
            "info", f"setting HV module {address} target to {voltage:.2f} V"
        )
        if self.test_mode:
            self._sim_hv_target[address] = float(voltage)
            return self.NO_ERR
        status = ESIBase.set_hv_supply_target_output_voltage(
            self, address, voltage
        )
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to set HV module {address} target: status {status}",
            )
        return status

    def restart(self):
        """Restart the controller (real hardware only)."""
        self.log_event("info", "restarting ESI controller")
        status = ESIBase.restart(self)
        if status != self.NO_ERR:
            self.log_event("error", f"controller restart failed: status {status}")
        return status
