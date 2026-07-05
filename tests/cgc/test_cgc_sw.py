"""
SW (HV-AMX-CTRL-4ED, "swB") + SWHR (HV-AMX-CTRL-4EDH, "swA") tests:
base marshalling (incl. the SW dll_port rename regression and SWHR
stream addressing), lab layer on CGCDevice against a fake WinDLL, and
the sim layer — including the frequency/duty-cycle conveniences the
campaign ramps rely on and the broken-sensor skip
(swA sensor 2 / swB sensor 0, [[cgc-sw]]).
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
from devices.cgc import SW, SWHR
from devices.cgc.sw.sw_base import SWBase
from devices.cgc.sw_HR.sw_HR_base import SWHRBase


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
#     Base layer (pure ctypes wrappers)
# =============================================================================

def test_swbase_construction_loads_dll_and_error_dict(dll_factory):
    base = SWBase(com=19, port=0)
    assert dll_factory.paths[-1].endswith("COM-HVAMX4ED.dll")
    assert base.err_dict["-2"] == "Error opening port"
    assert base.dll_port == 0


def test_swbase_open_port_defaults_to_dll_port(dll_factory):
    # Rename regression: the implicit device index must come from
    # dll_port (DeviceBase.port is the "COM19" label).
    base = SWBase(com=19, port=1)
    base.open_port(19)
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_HVAMX4ED_Open"
    assert args == (1, 19)


def test_swbase_set_comspeed_byref_roundtrip(dll_factory):
    base = SWBase(com=19, port=0)

    def handler(port, baud):
        baud._obj.value = 115200  # device negotiated down
        return 0

    dll_factory.last.handlers["COM_HVAMX4ED_SetBaudRate"] = handler
    assert base.set_comspeed(230400) == (0, 115200)


def test_swbase_get_oscillator_period_byref(dll_factory):
    base = SWBase(com=19, port=0)

    def handler(port, period):
        period._obj.value = 99998
        return 0

    dll_factory.last.handlers["COM_HVAMX4ED_GetOscillatorPeriod"] = handler
    assert base.get_oscillator_period() == (0, 99998)


def test_swhrbase_construction_and_stream_addressing(dll_factory):
    base = SWHRBase(com=20, stream=1)
    assert dll_factory.paths[-1].endswith("COM-HVAMX4EDH.dll")
    assert base.stream == 1
    assert base.ERR_STREAM_RANGE == -1
    base.open_port(20)
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_HVAMX4EDH_Open"
    assert args == (1, 20)
    base.close_port()
    assert dll_factory.last.calls[-1] == ("COM_HVAMX4EDH_Close", (1,))


def test_swhrbase_get_housekeeping_9_tuple_unpack(dll_factory):
    base = SWHRBase(com=20, stream=0)

    def handler(stream, v12, vfans, v5, v3, v3p, v25, vc, tcpu):
        for ref, value in (
            (v12, 12.0), (vfans, 11.9), (v5, 5.0), (v3, 3.3),
            (v3p, 3.31), (v25, 2.5), (vc, 1.2), (tcpu, 38.5),
        ):
            ref._obj.value = value
        return 0

    dll_factory.last.handlers["COM_HVAMX4EDH_GetHousekeeping"] = handler
    result = base.get_housekeeping()
    assert result == (0, 12.0, 11.9, 5.0, 3.3, 3.31, 2.5, 1.2, 38.5)


def test_swhrbase_fine_delay_marshals_uint16(dll_factory):
    base = SWHRBase(com=20, stream=0)
    base.set_switch_rise_delay_fine(2, 0x150)
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_HVAMX4EDH_SetSwitchRiseDelayFine"
    assert args[0] == 0
    assert args[1] == 2
    assert args[2].value == 0x150


# =============================================================================
#     Lab layer (CGCDevice) against the fake DLL
# =============================================================================

def test_sw_ctor_and_status_contract(dll_factory):
    logger, _ = capture_logger()
    sw = SW("swB", 19, port=0, logger=logger, skip_sensors=(0,))
    status = sw.get_status()
    assert status["device_id"] == "swB"
    assert status["port"] == "COM19"
    assert status["com"] == 19
    assert status["dll_port"] == 0
    assert status["skip_sensors"] == [0]


def test_swhr_ctor_and_status_contract(dll_factory):
    logger, _ = capture_logger()
    swhr = SWHR("swA", 20, stream=0, logger=logger, skip_sensors=(2,))
    status = swhr.get_status()
    assert status["device_id"] == "swA"
    assert status["port"] == "COM20"
    assert status["stream"] == 0
    assert status["skip_sensors"] == [2]


def test_sw_connect_opens_then_comspeed(dll_factory):
    logger, records = capture_logger()
    sw = SW("swB", 19, logger=logger)
    assert sw.connect() is True
    names = dll_factory.last.call_names()
    assert names[0] == "COM_HVAMX4ED_Open"
    assert names[1] == "COM_HVAMX4ED_SetBaudRate"
    assert dll_factory.last.calls[0][1] == (0, 19)
    assert any("connected (vendor DLL, 230400 baud)" in r for r in records)


def test_swhr_connect_opens_then_comspeed(dll_factory):
    logger, _ = capture_logger()
    swhr = SWHR("swA", 20, logger=logger)
    assert swhr.connect() is True
    names = dll_factory.last.call_names()
    assert names[0] == "COM_HVAMX4EDH_Open"
    assert names[1] == "COM_HVAMX4EDH_SetBaudRate"


def test_sw_comspeed_failure_warns_but_connects(dll_factory):
    logger, records = capture_logger()
    sw = SW("swB", 19, logger=logger)
    dll_factory.last.handlers["COM_HVAMX4ED_SetBaudRate"] = lambda *a: -16
    assert sw.connect() is True
    assert any("set_comspeed returned -16" in r for r in records)


def test_sw_connect_failure_never_simulates(dll_factory, sink, tmp_path):
    logger, records = capture_logger()
    sw = SW("swB", 19, logger=logger, sink=sink)
    dll_factory.last.handlers["COM_HVAMX4ED_Open"] = lambda *a: -2
    assert sw.connect() is False
    assert any("connect FAILED" in r and "Error opening port" in r for r in records)
    assert _samples(tmp_path / "telemetry.db") == []


def test_swhr_reconnect_reruns_bringup(dll_factory):
    logger, _ = capture_logger()
    swhr = SWHR("swA", 20, logger=logger)
    assert swhr.connect() is True
    assert swhr.reconnect() is True
    names = dll_factory.last.call_names()
    assert names.count("COM_HVAMX4EDH_Open") == 2
    assert names.count("COM_HVAMX4EDH_SetBaudRate") == 2
    assert names.index("COM_HVAMX4EDH_Close") < names.index(
        "COM_HVAMX4EDH_Open", 1
    )


def test_sw_hk_monitor_skips_broken_sensor_and_derives_freq(
    dll_factory, sink, tmp_path
):
    logger, _ = capture_logger()
    sw = SW("swB", 19, logger=logger, sink=sink, skip_sensors=(0,))

    def osc_handler(port, period):
        period._obj.value = 99998  # 1 kHz
        return 0

    dll_factory.last.handlers["COM_HVAMX4ED_GetOscillatorPeriod"] = osc_handler
    assert sw.connect() is True
    sw.hk_monitor()
    channels = _channels(tmp_path / "telemetry.db")
    assert {
        "Volt_12V", "Volt_5V0", "Volt_3V3", "Temp_CPU",
        "Temp_Sensor1", "Temp_Sensor2",
        "Fan0_RPM", "CPU_Load", "Osc_Period", "Osc_Freq", "Device_Enabled",
    } <= channels
    assert "Temp_Sensor0" not in channels  # broken swB sensor, skipped
    freq = [v for _, c, v, _ in _samples(tmp_path / "telemetry.db")
            if c == "Osc_Freq"]
    assert freq == [pytest.approx(1000.0)]


def test_swhr_hk_monitor_rails_and_skip(dll_factory, sink, tmp_path):
    logger, _ = capture_logger()
    swhr = SWHR("swA", 20, logger=logger, sink=sink, skip_sensors=(2,))
    assert swhr.connect() is True
    swhr.hk_monitor()
    channels = _channels(tmp_path / "telemetry.db")
    assert {
        "Volt_12V", "Volt_Fans", "Volt_5V0", "Volt_3V3", "Volt_3V3P",
        "Volt_2V5P", "Volt_VC", "Temp_CPU",
        "Temp_Sensor0", "Temp_Sensor1",
        "Fan0_RPM", "CPU_Load", "Device_Enabled",
    } <= channels
    assert "Temp_Sensor2" not in channels  # broken swA sensor, skipped


# =============================================================================
#     Sim layer (test_mode=True never loads the DLL)
# =============================================================================

@pytest.fixture
def forbid_windll(monkeypatch):
    def boom(path):
        raise AssertionError(f"test_mode must not load the vendor DLL ({path})")

    monkeypatch.setattr(ctypes, "WinDLL", boom)


def test_sim_construct_connect_reconnect_without_dll(forbid_windll):
    for factory in (
        lambda logger: SW("swB", 19, logger=logger, test_mode=True),
        lambda logger: SWHR("swA", 20, logger=logger, test_mode=True),
    ):
        logger, records = capture_logger()
        device = factory(logger)
        assert device.connect() is True
        assert any("connected (simulated, no hardware)" in r for r in records)
        assert device.reconnect() is True


def test_sw_sim_frequency_and_duty_cycle_roundtrip(forbid_windll):
    # The campaign ramp helpers run on exactly this path in the dry-run.
    logger, _ = capture_logger()
    sw = SW("swB", 19, logger=logger, test_mode=True)
    sw.connect()
    assert sw.set_frequency_khz(100) == sw.NO_ERR
    status, period = sw.get_oscillator_period()
    assert period == round(sw.CLOCK / 100e3 - sw.OSC_OFFSET)  # 998
    assert sw.set_duty_cycle(0, 0.5) == sw.NO_ERR
    status, width = sw.get_pulser_width(0)
    assert width == round(0.5 * (period + sw.OSC_OFFSET) - sw.PULSER_WIDTH_OFFSET)
    # Invalid arguments are rejected without touching state.
    assert sw.set_frequency_khz(0) == sw.ERR_ARGUMENT
    assert sw.set_duty_cycle(0, 1.5) == sw.ERR_ARGUMENT
    assert sw.set_delay_minimum(0) == sw.NO_ERR
    assert sw.get_pulser_delay(0) == (sw.NO_ERR, 1)


def test_sw_sim_enable_drives_controller_state(forbid_windll):
    logger, _ = capture_logger()
    sw = SW("swB", 19, logger=logger, test_mode=True)
    sw.connect()
    assert sw.get_device_enable() == (sw.NO_ERR, False)
    sw.set_device_enable(True)
    assert sw.get_device_enable() == (sw.NO_ERR, True)
    status, state_hex, names = sw.get_controller_state()
    assert "ENB" in names


def test_swhr_sim_fine_delay_and_frequency_roundtrip(forbid_windll):
    logger, _ = capture_logger()
    swhr = SWHR("swA", 20, logger=logger, test_mode=True)
    swhr.connect()
    assert swhr.set_switch_rise_delay_fine(0, 0x120) == swhr.NO_ERR
    assert swhr.get_switch_rise_delay_fine(0) == (swhr.NO_ERR, 0x120)
    assert swhr.set_switch_fall_delay_fine(0, 0x80) == swhr.NO_ERR
    assert swhr.get_switch_fall_delay_fine(0) == (swhr.NO_ERR, 0x80)
    assert swhr.set_switch_delay(1, 3, 5) == swhr.NO_ERR
    assert swhr.get_switch_delay(1) == (swhr.NO_ERR, 3, 5)
    assert swhr.set_frequency_khz(0, 1000) == swhr.NO_ERR
    status, period = swhr.get_oscillator_period(0)
    assert period == round(swhr.DEF_CLOCK / 1e6 - swhr.OSC_OFFSET)  # 98


def test_sim_hk_channels_and_sim_flag(forbid_windll, sink, tmp_path):
    logger, records = capture_logger()
    sw = SW("swB", 19, logger=logger, sink=sink, test_mode=True,
            skip_sensors=(0,))
    sw.connect()
    sw.hk_monitor()
    rows = _samples(tmp_path / "telemetry.db")
    assert rows
    assert all(sim == 1 for _, _, _, sim in rows)
    assert "Temp_Sensor0" not in _channels(tmp_path / "telemetry.db")
    assert any(r.startswith("[SIM] swB") for r in records)


def test_sim_raw_dll_exports_are_real_hardware_only(forbid_windll):
    logger, _ = capture_logger()
    sw = SW("swB", 19, logger=logger, test_mode=True)
    swhr = SWHR("swA", 20, logger=logger, test_mode=True)
    sw.connect()
    swhr.connect()
    with pytest.raises(AttributeError):
        sw.get_switch_trigger_config(0)  # raw export, not curated
    with pytest.raises(AttributeError):
        swhr.get_pll_source(0)  # raw export, not curated
