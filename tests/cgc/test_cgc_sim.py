"""
Sim-layer tests: AMPR/PA in explicit test mode. ctypes.WinDLL is patched
to explode — proving the vendor DLL is never loaded in test mode. Covers
the [SIM] marker + sim=1 sink rows, the curated simulated methods
(stateful voltage setpoints, PSU/module enable, get_current drain cycle)
and the documented real-hardware-only behavior of raw DLL exports.
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
from devices.cgc import AMPR, PA
from devices.cgc.pA.pA import SIM_MODULES


@pytest.fixture(autouse=True)
def forbid_windll(monkeypatch):
    def boom(path):
        raise AssertionError(f"test_mode must not load the vendor DLL ({path})")

    monkeypatch.setattr(ctypes, "WinDLL", boom)


@pytest.fixture
def sink(tmp_path):
    with SQLiteSink(tmp_path / "telemetry.db") as s:
        yield s


def _samples(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT device, channel, value, sim FROM samples"
        ).fetchall()


def test_sim_construct_connect_reconnect_without_dll():
    for factory in (
        lambda logger: AMPR("AMPR1000", 8, logger=logger, test_mode=True),
        lambda logger: PA("dmmr8_esibd", 7, logger=logger, test_mode=True),
    ):
        logger, records = capture_logger()
        device = factory(logger)
        assert device.connect() is True
        assert device.get_status()["test_mode"] is True
        assert any("connected (simulated, no hardware)" in r for r in records)
        assert device.reconnect() is True


def test_sim_marker_and_sim_flag_in_sink(sink, tmp_path):
    logger, records = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger, sink=sink, test_mode=True)
    ampr.connect()
    ampr.hk_monitor()
    rows = _samples(tmp_path / "telemetry.db")
    assert rows
    assert all(sim == 1 for _, _, _, sim in rows)
    assert any(r.startswith("[SIM] AMPR1000") for r in records)


def test_ampr_sim_hk_channels(sink, tmp_path):
    logger, _ = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger, sink=sink, test_mode=True)
    ampr.connect()
    ampr.hk_monitor()
    by_channel = {ch: value for _, ch, value, _ in _samples(tmp_path / "telemetry.db")}
    expected = {
        "Volt_12V", "Volt_5V0", "Volt_3V3", "Volt_AGND",
        "Volt_12Va_P", "Volt_12Va_N", "Volt_HV_P", "Volt_HV_N",
        "Temp_CPU", "Temp_ADC", "Temp_AV", "Temp_HV_P", "Temp_HV_N",
        "Line_Freq", "Fan_RPM", "CPU_Load", "PSU_Enabled", "Modules_Present",
    }
    assert expected <= set(by_channel)
    assert by_channel["Modules_Present"] == 3
    assert 11.8 <= by_channel["Volt_12V"] <= 12.2
    assert by_channel["PSU_Enabled"] == 0


def test_pa_sim_hk_channels(sink, tmp_path):
    logger, _ = capture_logger()
    pa = PA("dmmr8_esibd", 7, logger=logger, sink=sink, test_mode=True)
    pa.connect()
    pa.hk_monitor()
    by_channel = {ch: value for _, ch, value, _ in _samples(tmp_path / "telemetry.db")}
    expected = {
        "Volt_12V", "Volt_5V0", "Volt_3V3", "Temp_CPU", "Base_Temp",
        "Fan_RPM", "CPU_Load", "Enabled", "Modules_Present",
    }
    assert expected <= set(by_channel)
    assert by_channel["Modules_Present"] == len(SIM_MODULES)
    assert by_channel["Enabled"] == 0


def test_ampr_sim_voltage_roundtrip():
    logger, _ = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger, test_mode=True)
    ampr.connect()
    assert ampr.set_module_voltage(0, 1, 12.5) == ampr.NO_ERR
    voltages = ampr.get_module_voltages(0)
    assert voltages[1]["setpoint"] == 12.5
    assert abs(voltages[1]["measured"] - 12.5) < 0.2
    assert voltages[0]["setpoint"] == 0.0
    status, measured = ampr.get_measured_module_output_voltages(0)
    assert status == ampr.NO_ERR
    assert len(measured) == ampr.MODULE_CHANNEL_NUM
    assert ampr.get_module_output_voltage(0, 1) == (ampr.NO_ERR, 12.5)
    results = ampr.set_module_voltages(0, [1.0, None, 3.0, 4.0])
    assert results == {0: ampr.NO_ERR, 2: ampr.NO_ERR, 3: ampr.NO_ERR}


def test_ampr_sim_enable_psu_drives_state():
    logger, _ = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger, test_mode=True)
    ampr.connect()
    assert ampr.get_state()[2] == "ST_STBY"
    assert ampr.enable_psu(True) == (ampr.NO_ERR, True)
    assert ampr.get_state()[2] == "ST_ON"
    assert ampr.get_device_state()[2] == ["DS_PSU_ENB"]
    assert ampr.enable_psu(False) == (ampr.NO_ERR, False)
    assert ampr.get_state()[2] == "ST_STBY"


def test_pa_sim_get_current_drain_and_refill():
    logger, _ = capture_logger()
    pa = PA("dmmr8_esibd", 7, logger=logger, test_mode=True)
    pa.connect()

    def drain():
        seen = []
        for _ in range(len(SIM_MODULES) + 1):
            status, address, current, meas_range, ts = pa.get_current()
            if status == pa.NO_DATA:
                return seen
            assert status == pa.NO_ERR
            low = (address + 1) * 0.8e-12
            high = (address + 1) * 1.2e-12
            assert low <= current <= high
            seen.append(address)
        raise AssertionError("drain cycle never returned NO_DATA")

    assert drain() == list(SIM_MODULES)
    # The queue refills after NO_DATA — the plugin's poll loop keeps working.
    assert drain() == list(SIM_MODULES)


def test_pa_sim_enable_roundtrips():
    logger, _ = capture_logger()
    pa = PA("dmmr8_esibd", 7, logger=logger, test_mode=True)
    pa.connect()
    assert pa.set_enable(True) == pa.NO_ERR
    assert pa.get_enable() == (pa.NO_ERR, True)
    assert pa.set_automatic_current(True) == pa.NO_ERR
    assert pa.get_automatic_current() == (pa.NO_ERR, True)
    assert pa.set_enable(False) == pa.NO_ERR
    assert pa.get_enable() == (pa.NO_ERR, False)


def test_pa_sim_module_current():
    logger, _ = capture_logger()
    pa = PA("dmmr8_esibd", 7, logger=logger, test_mode=True)
    pa.connect()
    status, current, meas_range = pa.get_module_current(3)
    assert status == pa.NO_ERR
    assert 3.2e-12 <= current <= 4.8e-12


def test_sim_raw_dll_exports_are_real_hardware_only():
    logger, _ = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger, test_mode=True)
    with pytest.raises(AttributeError):
        ampr.purge()
    pa = PA("dmmr8_esibd", 7, logger=logger, test_mode=True)
    with pytest.raises(AttributeError):
        pa.device_purge()
