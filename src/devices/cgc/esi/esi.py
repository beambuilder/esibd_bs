"""
ESI controller (electrospray HV supply + heater) on the shared CGC lab layer.

``ESI`` combines the pure ctypes wrapper (``ESIBase``, DLL 1-00) with
``CGCDevice`` (canonical log line, telemetry sink, housekeeping worker +
poke, responding/reconnect, explicit test mode).

Firmware 1-00 workflow (lead-engineer email 2026-07-21, user-verified
2026-07-23): select one of the NVM configurations (sets heater
temperature + limits, interlock mask, module enables and HV target
voltages — DLL slots are 0-based, cfg-file ``[ConfigurationN]`` = slot
N-1: 0=Off, 1=Standby, 9-24=Heat 30-175 degC, 99+=HV presets), then
tweak the
heater temperature and HV target voltages live. **A working config takes
effect immediately on load — heating starts and HV is applied with no
further enable step.** Device-level activation state is GONE in 1-00 —
the main state now reports ON vs STANDBY and the hk channel
``Activated`` derives from it (name kept so the Explorer sink piggyback
survives).

Config-file gotchas (user, 2026-07-23): ``HVPSxMaxVoltStep`` must be
nonzero (good value 10 V) — at 0 no voltage gets applied at all;
``InterlockEnable`` must be exactly ``Y,N,N,Y`` for the lab setup
(Front, Rear, ESI-Ilock1, ESI-Ilock2). Both are config-blob fields with
no dedicated DLL setter besides the interlock mask.

The working DLL is the 32-bit build in ``ESI-CTRL_1-00/`` (x64 build
broken, manufacturer 2026-07-23); ``ESIBase`` reaches it through a
32-bit bridge process (``esi_bridge``/``esi_server32``) — first connect
in a process takes a few extra seconds for server startup.

The controller carries up to 4 modules: heat controller HTCTRL-24-10 on
address 0, HV supplies on addresses 1..3 (lab: 2x HVPS-3kB on addresses
2 and 3, user-confirmed 2026-07-21 — same as on firmware 0-00; the
shipped config presets' "HV1"/"HV2" name the supplies, not addresses).

Bring-up lives in ``_open_transport()`` so ``reconnect()`` re-runs it:
open_port -> set_comspeed -> set_enable(True). Configuration selection,
module activation and target voltages are operator actions and never
part of bring-up.

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

#: HV-module addresses simulated in test mode (the lab's populated
#: slots, 2 = inlet, 3 = emitter; user-confirmed on firmware 1-00).
SIM_MODULES = (2, 3)

#: NVM config slots simulated in test mode, mirroring the device NVM.
#: DLL slot numbering is 0-based (hardware observation 2026-07-23):
#: cfg-file section [ConfigurationN] = DLL slot N-1. 0=Off, 1=Standby
#: (device disabled, HV modules enabled), 9..24 = heat setpoints
#: (DeviceEnable=Y).
SIM_CONFIG_NAMES = {0: "Off", 1: "Standby"}
SIM_CONFIG_HEAT = {}
for _slot, _temp in zip(range(9, 24), range(30, 180, 10)):
    SIM_CONFIG_NAMES[_slot] = f"Heat {_temp}deg"
    SIM_CONFIG_HEAT[_slot] = float(_temp)
SIM_CONFIG_NAMES[24] = "Heat 175deg"
SIM_CONFIG_HEAT[24] = 175.0

#: Per-config HV target presets simulated in test mode
#: (address -> volts). Mirrors the user-edited cfg where working heat
#: configs carry preset HV voltages (slot 11 "Heat 50deg" = file
#: [Configuration12]: HVPS2Voltage=60, HVPS3Voltage=65; HVPS key N
#: assumed to drive address N — HVPS1 slot is unpopulated in the lab).
SIM_CONFIG_HV = {11: {2: 60.0, 3: 65.0}}


class ESI(CGCDevice, ESIBase):
    """
    ESI controller with canonical logging, telemetry and test mode.

    Curated high-level methods (simulated in test mode): housekeeping
    reads, state reads, ``set_enable()``/``get_enable()``,
    ``load_current_config()``/``save_current_config()`` + config
    name/list, ``set_module_activation_state()``/
    ``get_module_activation_state()``, HV target voltage set/read, V/I
    readback, measurement ranges, heater target temperature and heater
    monitoring. Raw DLL exports are real-hardware-only.

    Example:
        esi = ESI("ESI", com=14, sink=sink)
        esi.connect()            # open + comspeed + enable (single-instance guard)
        esi.load_current_config(9)    # "Heat 30deg": heater on, HV modules enabled
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
        # Simulated state (test mode only): device enable, ON/STANDBY
        # (config-driven since 1-00), per-module activation + HV targets
        # (readback tracks the target while active), measurement ranges,
        # loaded config slot and heater target.
        self._sim_enabled = False
        self._sim_activated = False
        self._sim_module_active = {addr: False for addr in SIM_MODULES}
        self._sim_hv_target = {addr: 0.0 for addr in SIM_MODULES}
        self._sim_meas_ranges = {addr: (False, False) for addr in SIM_MODULES}
        self._sim_config = None
        self._sim_heater_target = 0.0
        self._sim_config_names = dict(SIM_CONFIG_NAMES)
        if not test_mode:
            ESIBase.__init__(self, com=com, log=None, idn=device_id)

    # =========================================================================
    #     Transport (bring-up; reconnect() re-runs it)
    # =========================================================================

    def _open_transport(self) -> None:
        """ESI bring-up: claim the single-instance slot, then open_port ->
        set_comspeed -> set_enable(True). A comspeed failure is a warning;
        any other failure releases the slot, closes the port best-effort
        and raises."""
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
        states, heater and HV modules. Blocks are individually guarded so
        one failing read does not silence the others."""
        with self.thread_lock:
            for block in (
                self._hk_general_housekeeping,
                self._hk_cpu,
                self._hk_fan,
                self._hk_states,
                self._hk_heater,
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
            # 1-00 dropped the device activation state; ON vs STANDBY on
            # the main state replaces it. Channel name kept for the
            # dashboard/Explorer sink piggyback.
            self.log_sample("Activated", 1 if state_name == "STATE_ON" else 0)
        status, state_hex, names = self.get_device_state()
        if status == self.NO_ERR:
            self.log_sample("Device_State", ", ".join(names))
        status, enabled = self.get_enable()
        if status == self.NO_ERR:
            self.log_sample("Enabled", 1 if enabled else 0)

    def _hk_heater(self):
        # Heat controller is optional hardware (address 0); skip quietly
        # when the read fails or reports invalid.
        try:
            status, valid, vout, vheat, iout, theat = self.get_heat_ctrl_monitoring()
        except Exception:
            return
        if status == self.NO_ERR and valid:
            self.log_sample("Temp_Heater", theat, "degC", ".1f")

    def _hk_modules(self):
        status, valid, max_module, presence = self.get_module_presence()
        if status != self.NO_ERR:
            return
        # HV supplies live on addresses 1..3; address 0 is the heat
        # controller and has no V/I readback.
        hv_addresses = [
            addr for addr in range(1, self.MODULE_NUM)
            if presence[addr] == self.MODULE_PRESENT
        ]
        self.log_sample("Modules_Present", len(hv_addresses))
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
        """ON when the loaded configuration activates the device (1-00:
        replaces the removed device activation state), STANDBY otherwise."""
        if self.test_mode:
            sv = 0x0000 if self._sim_activated else 0x0001
            return self.NO_ERR, hex(sv), self.MAIN_STATE[sv]
        return ESIBase.get_main_state(self)

    def get_device_state(self):
        if self.test_mode:
            return self.NO_ERR, hex(0), ["DEVST_OK"]
        return ESIBase.get_device_state(self)

    def get_module_presence(self):
        if self.test_mode:
            presence = [self.MODULE_NOT_FOUND] * (self.MODULE_NUM + 1)
            presence[self.ADDR_HTCTRL] = self.MODULE_PRESENT  # heat controller
            for addr in SIM_MODULES:
                presence[addr] = self.MODULE_PRESENT
            presence[self.PRESENCE_BASE] = self.MODULE_PRESENT
            return self.NO_ERR, True, max(SIM_MODULES), presence
        return ESIBase.get_module_presence(self)

    def get_enable(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_enabled
        return ESIBase.get_enable(self)

    def get_module_activation_state(self, address):
        if self.test_mode:
            return self.NO_ERR, self._sim_module_active.get(address, False)
        return ESIBase.get_module_activation_state(self, address)

    def get_hv_supply_meas_ranges(self, address):
        if self.test_mode:
            if address not in self._sim_meas_ranges:
                return self.ERR_ARGUMENT, False, False
            volt_neg, curr_high = self._sim_meas_ranges[address]
            return self.NO_ERR, volt_neg, curr_high
        return ESIBase.get_hv_supply_meas_ranges(self, address)

    def get_hv_supply_target_output_voltage(self, address):
        if self.test_mode:
            return self.NO_ERR, self._sim_hv_target.get(address, 0.0)
        return ESIBase.get_hv_supply_target_output_voltage(self, address)

    def get_hv_supply_output_voltage(self, address):
        """Returns (status, valid, voltage). Simulated readback tracks the
        target (small noise) while the module is activated and the device
        is ON, 0 V otherwise."""
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

    def get_heat_ctrl_heater_temperature(self):
        if self.test_mode:
            return self.NO_ERR, self._sim_heater_target
        return ESIBase.get_heat_ctrl_heater_temperature(self)

    def get_heat_ctrl_monitoring(self):
        """Returns (status, valid, volt_out, volt_heat, curr_out,
        temp_heat). Simulated heater temperature sits at the target while
        heating (device ON, target > 0), near ambient otherwise."""
        if self.test_mode:
            heating = self._sim_activated and self._sim_heater_target > 0
            if heating:
                temp = self._sim_heater_target + self._sim_uniform(-0.3, 0.3, 1)
                return self.NO_ERR, True, 12.0, 11.8, 1.5, temp
            return self.NO_ERR, True, 0.0, 0.0, 0.0, self._sim_uniform(21.0, 23.0, 1)
        return ESIBase.get_heat_ctrl_monitoring(self)

    def get_config_name(self, config_number):
        if self.test_mode:
            return self.NO_ERR, self._sim_config_names.get(config_number, "")
        return ESIBase.get_config_name(self, config_number)

    def list_configs(self):
        """List NVM configurations. Returns (status, active_slots,
        valid_slots) as sorted slot-number lists (unlike the raw
        ``get_config_list``, which returns two MAX_CONFIG bool lists)."""
        if self.test_mode:
            slots = sorted(self._sim_config_names)
            return self.NO_ERR, slots, slots
        status, active, valid = ESIBase.get_config_list(self)
        active_slots = [n for n, a in enumerate(active) if a]
        valid_slots = [n for n, v in enumerate(valid) if v]
        return status, active_slots, valid_slots

    # =========================================================================
    #     Curated controls (logging + test-mode simulation)
    # =========================================================================

    def set_enable(self, enable):
        """Enable/disable the device. Returns the DLL status code."""
        self.log_event("info", f"setting device enable to {enable}")
        if self.test_mode:
            self._sim_enabled = bool(enable)
            return self.NO_ERR
        status = ESIBase.set_enable(self, enable)
        if status != self.NO_ERR:
            self.log_event("error", f"failed to set device enable: status {status}")
        return status

    def load_current_config(self, config_number):
        """Load configuration from NVM slot (the 1-00 operator workflow:
        select a config — heater temperature, interlocks, module enables,
        HV targets — then tweak heater temperature and HV voltages). A
        working config takes effect immediately: heating starts and HV is
        applied, no further enable step (user-verified 2026-07-23).
        Returns the status."""
        self.log_event("info", f"loading NVM config {config_number}")
        if self.test_mode:
            if config_number not in self._sim_config_names:
                self.log_event(
                    "error",
                    f"failed to load NVM config {config_number}: "
                    f"status {self.ERR_ARGUMENT}",
                )
                return self.ERR_ARGUMENT
            self._sim_config = config_number
            # Mirrors the lab cfg: slot 0 "Off" disables everything,
            # slot 1 "Standby" keeps the device off with HV modules
            # enabled, heat slots activate the device and may carry
            # preset HV targets (SIM_CONFIG_HV).
            self._sim_activated = config_number in SIM_CONFIG_HEAT
            module_on = config_number != 0
            hv_presets = SIM_CONFIG_HV.get(config_number, {})
            for addr in SIM_MODULES:
                self._sim_module_active[addr] = module_on
                self._sim_hv_target[addr] = hv_presets.get(addr, 0.0)
            self._sim_heater_target = SIM_CONFIG_HEAT.get(config_number, 0.0)
            return self.NO_ERR
        status = ESIBase.load_current_config(self, config_number)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to load NVM config {config_number}: status {status}",
            )
        return status

    def save_current_config(self, config_number):
        """Save the current device settings to an NVM slot (PSU/SW-style
        config persistence; name the slot via ``set_config_name``).
        Returns the status."""
        self.log_event("info", f"saving current config to NVM slot {config_number}")
        if self.test_mode:
            self._sim_config_names.setdefault(
                config_number, f"Saved config {config_number}"
            )
            return self.NO_ERR
        status = ESIBase.save_current_config(self, config_number)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to save NVM config {config_number}: status {status}",
            )
        return status

    def set_config_name(self, config_number, name):
        """Set the name of an NVM config slot. Returns the status."""
        self.log_event(
            "info", f"naming NVM config slot {config_number} '{name}'"
        )
        if self.test_mode:
            self._sim_config_names[config_number] = str(name)
            return self.NO_ERR
        status = ESIBase.set_config_name(self, config_number, name)
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to name NVM config {config_number}: status {status}",
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

    def set_hv_supply_meas_ranges(self, address, volt_neg, curr_high):
        """Set one HV module's measurement ranges (volt_neg: regulate the
        negative output; curr_high: ~1.7 mA range instead of ~170 uA).
        Returns the status."""
        self.log_event(
            "info",
            f"setting HV module {address} meas ranges: "
            f"volt_neg={volt_neg}, curr_high={curr_high}",
        )
        if self.test_mode:
            if address not in self._sim_meas_ranges:
                return self.ERR_ARGUMENT
            self._sim_meas_ranges[address] = (bool(volt_neg), bool(curr_high))
            return self.NO_ERR
        status = ESIBase.set_hv_supply_meas_ranges(
            self, address, volt_neg, curr_high
        )
        if status != self.NO_ERR:
            self.log_event(
                "error",
                f"failed to set HV module {address} meas ranges: status {status}",
            )
        return status

    def set_heat_ctrl_heater_temperature(self, heater_temp):
        """Set the target heater temperature (negative turns temperature
        control off). Returns (status, set_value)."""
        self.log_event("info", f"setting heater target to {heater_temp:.1f} degC")
        if self.test_mode:
            self._sim_heater_target = float(heater_temp)
            return self.NO_ERR, float(heater_temp)
        status, set_value = ESIBase.set_heat_ctrl_heater_temperature(
            self, heater_temp
        )
        if status != self.NO_ERR:
            self.log_event(
                "error", f"failed to set heater target: status {status}"
            )
        return status, set_value

    def restart(self):
        """Restart the controller (real hardware only)."""
        self.log_event("info", "restarting ESI controller")
        status = ESIBase.restart(self)
        if status != self.NO_ERR:
            self.log_event("error", f"controller restart failed: status {status}")
        return status
