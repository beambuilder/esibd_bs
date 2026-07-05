"""
ESI lab-layer tests (P6.5-ESI slice): ESI on CGCDevice against a fake
WinDLL — ctor/status contract, nb-024 bring-up order, the process-wide
SINGLE-INSTANCE guard (the ESI-CTRL DLL takes no port argument),
reconnect re-running the bring-up, canonical hk samples, and the
test-mode simulator (no DLL load, stateful HV target/readback).
"""
import ctypes
import sqlite3
import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from conftest import capture_logger
from devices import SQLiteSink
from devices.cgc import CGCStatusError
from devices.cgc.esi import ESI
from devices.cgc.esi.esi import SIM_MODULES


@pytest.fixture
def sink(tmp_path):
    with SQLiteSink(tmp_path / "telemetry.db") as s:
        yield s


def _samples(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT device, channel, value, sim FROM samples"
        ).fetchall()


# --- ctor / bring-up (fake DLL, test_mode=False) --------------------------------

def test_ctor_and_status_contract(dll_factory):
    logger, _ = capture_logger()
    esi = ESI("ESI", 14, logger=logger)
    status = esi.get_status()
    assert status["device_id"] == "ESI"
    assert status["port"] == "COM14"
    assert status["com"] == 14
    assert status["baudrate"] == 230400
    assert status["test_mode"] is False
    assert "timeout" not in status  # DLL transport has no serial timeout


def test_bringup_order_open_comspeed_enable(dll_factory):
    logger, records = capture_logger()
    esi = ESI("ESI", 14, logger=logger)
    assert esi.connect() is True
    names = dll_factory.last.call_names()
    assert names[:3] == [
        "COM_ESI_CTRL_Open",
        "COM_ESI_CTRL_SetBaudRate",
        "COM_ESI_CTRL_SetEnable",
    ]
    open_args = dll_factory.last.calls[0][1]
    assert open_args[0].value == 14
    assert any("connected (vendor DLL, 230400 baud)" in r for r in records)


def test_comspeed_failure_warns_but_connects(dll_factory):
    logger, records = capture_logger()
    esi = ESI("ESI", 14, logger=logger)
    dll_factory.last.handlers["COM_ESI_CTRL_SetBaudRate"] = lambda *a: -16
    assert esi.connect() is True
    assert any("set_comspeed returned -16" in r for r in records)


def test_bringup_failure_closes_port_and_releases_guard(dll_factory):
    logger, records = capture_logger()
    esi = ESI("ESI", 14, logger=logger)
    dll_factory.last.handlers["COM_ESI_CTRL_SetEnable"] = lambda *a: -101
    assert esi.connect() is False
    assert esi.is_connected is False
    assert "COM_ESI_CTRL_Close" in dll_factory.last.call_names()
    assert ESI._connected_instance is None  # slot free for a retry
    # never auto-simulates
    assert any("connect FAILED" in r for r in records)
    # a retry with the failure gone succeeds (guard did not stick)
    dll_factory.last.handlers.pop("COM_ESI_CTRL_SetEnable")
    assert esi.connect() is True


def test_connect_failure_never_simulates(dll_factory, sink, tmp_path):
    logger, records = capture_logger()
    esi = ESI("ESI", 14, logger=logger, sink=sink)
    dll_factory.last.handlers["COM_ESI_CTRL_Open"] = lambda *a: -2
    assert esi.connect() is False
    assert esi.is_connected is False
    assert any("connect FAILED" in r for r in records)
    assert _samples(tmp_path / "telemetry.db") == []


def test_reconnect_reruns_full_bringup(dll_factory):
    logger, _ = capture_logger()
    esi = ESI("ESI", 14, logger=logger)
    assert esi.connect() is True
    assert esi.reconnect() is True
    names = dll_factory.last.call_names()
    assert names.count("COM_ESI_CTRL_Open") == 2
    assert names.count("COM_ESI_CTRL_SetEnable") == 2
    # The stale handle is closed before the reopen.
    assert names.index("COM_ESI_CTRL_Close") < names.index("COM_ESI_CTRL_Open", 1)


# --- single-instance guard -------------------------------------------------------

def test_second_instance_cannot_connect_while_first_holds_the_dll(dll_factory):
    logger, records = capture_logger()
    first = ESI("ESI", 14, logger=logger)
    second = ESI("ESI_notebook", 14, logger=logger)
    assert first.connect() is True
    assert second.connect() is False
    assert any(
        "connect FAILED" in r and "single-instance" in r for r in records
    )
    # the second instance never touched its DLL (no Open call)
    assert "COM_ESI_CTRL_Open" not in dll_factory.dlls[1].call_names()

    # once the holder disconnects, the slot frees up
    assert first.disconnect() is True
    assert second.connect() is True


def test_holder_reconnect_does_not_trip_its_own_guard(dll_factory):
    logger, _ = capture_logger()
    esi = ESI("ESI", 14, logger=logger)
    assert esi.connect() is True
    assert esi.reconnect() is True
    assert ESI._connected_instance is esi


# --- housekeeping (canonical samples from a scripted fake DLL) --------------------

def _install_hk_handlers(dll):
    def housekeeping(v24, v5, v3, tcpu, tpsu):
        v24._obj.value = 24.1
        v5._obj.value = 5.02
        v3._obj.value = 3.31
        tcpu._obj.value = 41.5
        tpsu._obj.value = 36.2
        return 0

    def presence(valid, max_mod, arr):
        valid._obj.value = True
        max_mod._obj.value = 3
        for addr in (2, 3):
            arr[addr] = 1  # MODULE_PRESENT
        arr[4] = 1  # base module
        return 0

    def hv_voltage(addr, valid, v):
        valid._obj.value = True
        v._obj.value = 300.0 + addr.value
        return 0

    def hv_current(addr, valid, i):
        valid._obj.value = True
        i._obj.value = 2.5e-10
        return 0

    def enabled(en):
        en._obj.value = True
        return 0

    dll.handlers["COM_ESI_CTRL_GetHousekeeping"] = housekeeping
    dll.handlers["COM_ESI_CTRL_GetModulePresence"] = presence
    dll.handlers["COM_ESI_CTRL_GetHVsupplyOutputVoltage"] = hv_voltage
    dll.handlers["COM_ESI_CTRL_GetHVsupplyOutputCurrent"] = hv_current
    dll.handlers["COM_ESI_CTRL_GetEnable"] = enabled
    dll.handlers["COM_ESI_CTRL_GetActivationState"] = enabled


def test_hk_monitor_writes_canonical_samples(dll_factory, sink, tmp_path):
    logger, _ = capture_logger()
    esi = ESI("ESI", 14, logger=logger, sink=sink)
    _install_hk_handlers(dll_factory.last)
    assert esi.connect() is True
    esi.hk_monitor()
    rows = _samples(tmp_path / "telemetry.db")
    by_channel = {channel: value for _, channel, value, _ in rows}
    assert by_channel["Volt_24V"] == 24.1
    assert by_channel["Temp_CPU"] == 41.5
    assert by_channel["Temp_PSU"] == 36.2
    assert by_channel["Enabled"] == 1
    assert by_channel["Activated"] == 1
    assert by_channel["Modules_Present"] == 2
    assert by_channel["HV2_Voltage"] == 302.0
    assert by_channel["HV3_Voltage"] == 303.0
    assert by_channel["HV2_Current"] == 2.5e-10
    # strings (Main_State etc.) never reach the numeric samples table
    assert "Main_State" not in by_channel
    assert all(sim == 0 for *_, sim in rows)


def test_check_raises_cgc_status_error(dll_factory):
    logger, _ = capture_logger()
    esi = ESI("ESI", 14, logger=logger)
    with pytest.raises(CGCStatusError) as excinfo:
        esi._check(-13, "set_enable")
    assert excinfo.value.status == -13
    assert "set_enable failed" in str(excinfo.value)


# --- test mode (vendor DLL never loaded) -------------------------------------------

@pytest.fixture
def forbid_windll(monkeypatch):
    def boom(path):
        raise AssertionError(f"test_mode must not load the vendor DLL ({path})")

    monkeypatch.setattr(ctypes, "WinDLL", boom)


def test_sim_construct_connect_reconnect_without_dll(forbid_windll):
    logger, records = capture_logger()
    esi = ESI("ESI", 14, logger=logger, test_mode=True)
    assert esi.connect() is True
    assert esi.get_status()["test_mode"] is True
    assert any("connected (simulated, no hardware)" in r for r in records)
    assert esi.reconnect() is True


def test_sim_hv_target_and_readback_roundtrip(forbid_windll):
    logger, _ = capture_logger()
    esi = ESI("ESI", 14, logger=logger, test_mode=True)
    esi.connect()
    address = SIM_MODULES[0]
    # inactive module reads back 0 V regardless of target
    assert esi.set_hv_supply_target_output_voltage(address, 300.0) == esi.NO_ERR
    status, valid, volts = esi.get_hv_supply_output_voltage(address)
    assert (status, valid, volts) == (esi.NO_ERR, True, 0.0)
    # activated (device + module) -> readback tracks the target
    assert esi.set_activation_state(True) == esi.NO_ERR
    assert esi.set_module_activation_state(address, True) == esi.NO_ERR
    status, valid, volts = esi.get_hv_supply_output_voltage(address)
    assert status == esi.NO_ERR and valid
    assert abs(volts - 300.0) <= 0.5
    status, t = esi.get_hv_supply_target_output_voltage(address)
    assert (status, t) == (esi.NO_ERR, 300.0)
    # currents appear only while activated, in the nb-024 1e-10 A range
    status, valid, amps = esi.get_hv_supply_output_current(address)
    assert status == esi.NO_ERR and valid
    assert 0.5e-10 <= amps <= 1.5e-10
    # unknown module address -> argument error, never a crash
    status, valid, _ = esi.get_hv_supply_output_voltage(0)
    assert (status, valid) == (esi.ERR_ARGUMENT, False)


def test_sim_hk_channels(forbid_windll, sink, tmp_path):
    logger, _ = capture_logger()
    esi = ESI("ESI", 14, logger=logger, sink=sink, test_mode=True)
    esi.connect()
    esi.hk_monitor()
    rows = _samples(tmp_path / "telemetry.db")
    channels = {channel for _, channel, _, _ in rows}
    assert {"Volt_24V", "Volt_5V0", "Volt_3V3", "Temp_CPU", "Temp_PSU",
            "CPU_Load", "Fan_RPM", "Enabled", "Activated",
            "Modules_Present"} <= channels
    # both lab HV modules report while activated
    esi.set_activation_state(True)
    for addr in SIM_MODULES:
        esi.set_module_activation_state(addr, True)
        esi.set_hv_supply_target_output_voltage(addr, 100.0 * addr)
    esi.hk_monitor()
    channels = {channel for _, channel, _, _ in _samples(tmp_path / "telemetry.db")}
    for addr in SIM_MODULES:
        assert f"HV{addr}_Voltage" in channels
        assert f"HV{addr}_Current" in channels
    assert all(sim == 1 for *_, sim in rows)


def test_sim_raw_dll_exports_are_real_hardware_only(forbid_windll):
    logger, _ = capture_logger()
    esi = ESI("ESI", 14, logger=logger, test_mode=True)
    with pytest.raises(AttributeError):
        esi.get_uptime()  # raw export needs self.esi_dll -> real HW only
