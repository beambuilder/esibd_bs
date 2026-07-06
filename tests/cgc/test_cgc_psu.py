"""
PSU (HV-PSU-CTRL-2D) tests: base marshalling (incl. the dll_port rename
regression), lab layer on CGCDevice against a fake WinDLL, and the sim
layer (test_mode never loads the DLL). The lab layer keeps the pre-P6
mA current semantics — notebooks 011-023 depend on them.
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
from devices.cgc import PSU, CGCStatusError
from devices.cgc.psu.psu_base import PSUBase


@pytest.fixture
def sink(tmp_path):
    with SQLiteSink(tmp_path / "telemetry.db") as s:
        yield s


def _samples(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT device, channel, value, sim FROM samples"
        ).fetchall()


def _channels(db_path):
    return {c for _, c, _, _ in _samples(db_path)}


# =============================================================================
#     Base layer (pure ctypes wrapper)
# =============================================================================

def test_psubase_construction_loads_dll_and_error_dict(dll_factory):
    base = PSUBase(com=15, port=2)
    assert dll_factory.paths[-1].endswith("COM-HVPSU2D.dll")
    assert base.err_dict["-2"] == "Error opening port"
    assert base.dll_port == 2


def test_psubase_open_port_arg_order_is_port_then_com(dll_factory):
    base = PSUBase(com=15, port=2)
    base.open_port(15, 2)
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_HVPSU2D_Open"
    assert args == (2, 15)  # DLL wants (port index, COM number)


def test_psubase_close_port_uses_dll_port_index(dll_factory):
    # Rename regression: DeviceBase.port is the "COM15" label; the DLL
    # index must come from dll_port, never from the label.
    base = PSUBase(com=15, port=3)
    base.close_port()
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_HVPSU2D_Close"
    assert args == (3,)


def test_psubase_set_comspeed_byref_uint32_status_only(dll_factory):
    base = PSUBase(com=15, port=0)
    result = base.set_comspeed(230400)
    assert result == 0  # plain status, no tuple (unlike SW/SWHR)
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_HVPSU2D_SetBaudRate"
    assert args[1]._obj.value == 230400


def test_psubase_get_housekeeping_5_tuple_unpack(dll_factory):
    base = PSUBase(com=15, port=0)

    def handler(port, v_rect, v5, v3, t_cpu):
        v_rect._obj.value = 24.1
        v5._obj.value = 5.02
        v3._obj.value = 3.31
        t_cpu._obj.value = 36.5
        return 0

    dll_factory.last.handlers["COM_HVPSU2D_GetHousekeeping"] = handler
    status, volt_rect, volt_5v0, volt_3v3, temp_cpu = base.get_housekeeping()
    assert (status, volt_rect, volt_5v0, volt_3v3, temp_cpu) == (
        0, 24.1, 5.02, 3.31, 36.5
    )


def test_psubase_get_psu_data_multi_out_unpack(dll_factory):
    base = PSUBase(com=15, port=0)

    def handler(port, psu_num, voltage, current, dropout):
        voltage._obj.value = 50.0
        current._obj.value = 0.15
        dropout._obj.value = 2.5
        return 0

    dll_factory.last.handlers["COM_HVPSU2D_GetPSUData"] = handler
    status, voltage, current, volt_dropout = base.get_psu_data(base.PSU_POS)
    assert (status, voltage, current, volt_dropout) == (0, 50.0, 0.15, 2.5)


def test_psubase_get_psu_enable_bool_pair(dll_factory):
    base = PSUBase(com=15, port=0)

    def handler(port, psu0, psu1):
        psu0._obj.value = True
        psu1._obj.value = False
        return 0

    dll_factory.last.handlers["COM_HVPSU2D_GetPSUEnable"] = handler
    assert base.get_psu_enable() == (0, True, False)


def test_psubase_get_fan_data_arrays(dll_factory):
    base = PSUBase(com=15, port=0)

    def handler(port, enabled, failed, set_rpm, measured_rpm, pwm):
        for i in range(3):
            enabled[i] = True
            measured_rpm[i] = 3000 + i
        return 0

    dll_factory.last.handlers["COM_HVPSU2D_GetFanData"] = handler
    status, enabled, failed, set_rpm, measured_rpm, pwm = base.get_fan_data()
    assert status == 0
    assert enabled == [True, True, True]
    assert measured_rpm == [3000, 3001, 3002]


# =============================================================================
#     Lab layer (CGCDevice) against the fake DLL
# =============================================================================

def test_ctor_and_status_contract(dll_factory):
    logger, _ = capture_logger()
    psu = PSU("PSU1", 15, port=0, logger=logger)
    status = psu.get_status()
    assert status["device_id"] == "PSU1"
    assert status["port"] == "COM15"  # canonical label, NOT the DLL index
    assert status["com"] == 15
    assert status["dll_port"] == 0
    assert status["baudrate"] == 230400
    assert status["test_mode"] is False
    assert psu.hk_interval == 5.0


def test_connect_opens_indexed_port_then_comspeed(dll_factory):
    logger, records = capture_logger()
    psu = PSU("PSU3", 17, port=2, logger=logger)
    assert psu.connect() is True
    names = dll_factory.last.call_names()
    assert names[0] == "COM_HVPSU2D_Open"
    assert names[1] == "COM_HVPSU2D_SetBaudRate"
    assert dll_factory.last.calls[0][1] == (2, 17)
    assert any("connected (vendor DLL, 230400 baud)" in r for r in records)


def test_two_psus_in_one_process_use_distinct_dll_ports(dll_factory):
    # 4 physical supplies = 4 PSU instances; the DLL separates them by
    # the index in every export (multi-device-aware, unlike AMPR).
    logger, _ = capture_logger()
    psu1 = PSU("PSU1", 15, port=0, logger=logger)
    psu2 = PSU("PSU2", 16, port=1, logger=logger)
    assert psu1.connect() is True
    assert psu2.connect() is True
    opens = [
        args
        for dll in dll_factory.dlls
        for name, args in dll.calls
        if name == "COM_HVPSU2D_Open"
    ]
    assert opens == [(0, 15), (1, 16)]


def test_comspeed_failure_warns_but_connects(dll_factory):
    logger, records = capture_logger()
    psu = PSU("PSU1", 15, logger=logger)
    dll_factory.last.handlers["COM_HVPSU2D_SetBaudRate"] = lambda *a: -16
    assert psu.connect() is True
    assert any("set_comspeed returned -16" in r for r in records)


def test_connect_failure_never_simulates(dll_factory, sink, tmp_path):
    logger, records = capture_logger()
    psu = PSU("PSU1", 15, logger=logger, sink=sink)
    dll_factory.last.handlers["COM_HVPSU2D_Open"] = lambda *a: -2
    assert psu.connect() is False
    assert psu.is_connected is False
    assert any("connect FAILED" in r and "Error opening port" in r for r in records)
    assert _samples(tmp_path / "telemetry.db") == []


def test_reconnect_reruns_bringup(dll_factory):
    logger, _ = capture_logger()
    psu = PSU("PSU1", 15, logger=logger)
    assert psu.connect() is True
    assert psu.reconnect() is True
    names = dll_factory.last.call_names()
    assert names.count("COM_HVPSU2D_Open") == 2
    assert names.count("COM_HVPSU2D_SetBaudRate") == 2
    assert names.index("COM_HVPSU2D_Close") < names.index("COM_HVPSU2D_Open", 1)


def test_hk_monitor_writes_canonical_samples(dll_factory, sink, tmp_path):
    logger, _ = capture_logger()
    psu = PSU("PSU1", 15, logger=logger, sink=sink)

    def psu_data(port, psu_num, voltage, current, dropout):
        voltage._obj.value = 50.0
        current._obj.value = 0.15  # ampere at the DLL boundary
        dropout._obj.value = 2.5
        return 0

    dll_factory.last.handlers["COM_HVPSU2D_GetPSUData"] = psu_data
    assert psu.connect() is True
    psu.hk_monitor()
    rows = _samples(tmp_path / "telemetry.db")
    channels = _channels(tmp_path / "telemetry.db")
    assert {
        "Volt_Rect", "Volt_5V0", "Volt_3V3", "Temp_CPU",
        "Temp_Sensor0", "Temp_Sensor1", "Temp_Sensor2",
        "Fan0_RPM", "Fan1_RPM", "Fan2_RPM", "CPU_Load",
        "PSU0_Enabled", "PSU1_Enabled", "Device_Enabled",
        "PSU0_Voltage", "PSU0_Current", "PSU0_Dropout",
        "PSU1_Voltage", "PSU1_Current", "PSU1_Dropout",
    } <= channels
    # State strings log only, never into the db.
    assert "Main_State" not in channels
    # Current lands in mA (0.15 A -> 150 mA).
    current_rows = [v for _, c, v, _ in rows if c == "PSU0_Current"]
    assert current_rows == [pytest.approx(150.0)]
    assert all(sim == 0 for _, _, _, sim in rows)


def test_set_current_takes_ma_dll_gets_ampere(dll_factory):
    logger, _ = capture_logger()
    psu = PSU("PSU1", 15, logger=logger)
    assert psu.connect() is True
    psu.set_psu_output_current(psu.PSU_POS, 300)
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_HVPSU2D_SetPSUOutputCurrent"
    assert args[2].value == pytest.approx(0.3)  # 300 mA -> 0.3 A


def test_check_raises_cgc_status_error(dll_factory):
    logger, _ = capture_logger()
    psu = PSU("PSU1", 15, logger=logger)
    with pytest.raises(CGCStatusError) as excinfo:
        psu._check(-7, "send_command")
    assert excinfo.value.status == -7
    assert "Error sending command" in str(excinfo.value)


# =============================================================================
#     Sim layer (test_mode=True never loads the DLL)
# =============================================================================

@pytest.fixture
def forbid_windll(monkeypatch):
    def boom(path):
        raise AssertionError(f"test_mode must not load the vendor DLL ({path})")

    monkeypatch.setattr(ctypes, "WinDLL", boom)


def test_sim_construct_connect_reconnect_without_dll(forbid_windll):
    logger, records = capture_logger()
    psu = PSU("PSU1", 15, port=0, logger=logger, test_mode=True)
    assert psu.connect() is True
    assert psu.get_status()["test_mode"] is True
    assert psu.get_status()["dll_port"] == 0
    assert any("connected (simulated, no hardware)" in r for r in records)
    assert psu.reconnect() is True


def test_sim_voltage_readback_gated_on_both_enables(forbid_windll):
    logger, _ = capture_logger()
    psu = PSU("PSU1", 15, logger=logger, test_mode=True)
    psu.connect()
    psu.set_psu_output_voltage(psu.PSU_POS, 50.0)
    # Output stays dead until device AND output are enabled.
    status, voltage, current, _ = psu.get_psu_data(psu.PSU_POS)
    assert (voltage, current) == (0.0, 0.0)
    psu.set_device_enable(True)
    psu.set_psu_enable(True, False)
    status, voltage, current, _ = psu.get_psu_data(psu.PSU_POS)
    assert voltage == pytest.approx(50.0, abs=0.2)
    assert current > 0
    # The negative output was not enabled.
    status, voltage, current, _ = psu.get_psu_data(psu.PSU_NEG)
    assert (voltage, current) == (0.0, 0.0)


def test_sim_load_config_models_working_set(forbid_windll):
    # A config is the FULL working set incl. enables (campaign 2026-07-06:
    # bare enables arm nothing; slot 0 = standby, 63 = 10 V / 100 mA all
    # on). The sim must model that or a simulated config bring-up reads
    # 0 V forever (P6.10 plugin Test Mode).
    logger, _ = capture_logger()
    psu = PSU("PSU1", 15, logger=logger, test_mode=True)
    psu.connect()
    assert psu.load_current_config(63) == psu.NO_ERR
    assert psu.get_device_enable() == (psu.NO_ERR, True)
    assert psu.get_psu_enable() == (psu.NO_ERR, True, True)
    status, voltage, current, _ = psu.get_psu_data(psu.PSU_POS)
    assert voltage == pytest.approx(10.0, abs=0.2)
    assert psu.get_psu_set_output_current(psu.PSU_POS)[1] == 100.0
    # standby parks everything
    assert psu.load_current_config(0) == psu.NO_ERR
    assert psu.get_device_enable() == (psu.NO_ERR, False)
    assert psu.get_psu_enable() == (psu.NO_ERR, False, False)
    status, voltage, current, _ = psu.get_psu_data(psu.PSU_POS)
    assert (voltage, current) == (0.0, 0.0)


def test_sim_current_limit_roundtrip_in_ma(forbid_windll):
    logger, _ = capture_logger()
    psu = PSU("PSU1", 15, logger=logger, test_mode=True)
    psu.connect()
    assert psu.set_psu_output_current(psu.PSU_POS, 150) == psu.NO_ERR
    status, set_ma, limit_ma = psu.get_psu_set_output_current(psu.PSU_POS)
    assert (set_ma, limit_ma) == (150.0, 150.0)
    assert psu.set_psu0_output_current(250) == psu.NO_ERR
    assert psu.get_psu0_set_output_current()[1] == 250.0


def test_sim_hk_channels_and_sim_flag(forbid_windll, sink, tmp_path):
    logger, records = capture_logger()
    psu = PSU("PSU2", 16, port=1, logger=logger, sink=sink, test_mode=True)
    psu.connect()
    psu.hk_monitor()
    rows = _samples(tmp_path / "telemetry.db")
    assert rows
    assert all(sim == 1 for _, _, _, sim in rows)
    assert {"Volt_Rect", "PSU0_Voltage", "PSU1_Current"} <= _channels(
        tmp_path / "telemetry.db"
    )
    assert any(r.startswith("[SIM] PSU2") for r in records)


def test_sim_raw_dll_exports_are_real_hardware_only(forbid_windll):
    logger, _ = capture_logger()
    psu = PSU("PSU1", 15, logger=logger, test_mode=True)
    psu.connect()
    with pytest.raises(AttributeError):
        psu.get_adc_housekeeping(0)  # raw export, not curated
