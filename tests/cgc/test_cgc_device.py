"""
Lab-layer tests: AMPR/PA on CGCDevice against a fake WinDLL (real path,
test_mode=False) — constructor/status contract, connect/bring-up (incl.
the pA STRICT order), never-auto-simulate, the status→exception adapter,
reconnect re-running the bring-up, canonical hk samples, hk poke and the
opt-in DLL call tracer.
"""
import sqlite3
import sys
import time
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from conftest import capture_logger
from devices import SQLiteSink
from devices.cgc import AMPR, PA, CGCStatusError


@pytest.fixture
def sink(tmp_path):
    with SQLiteSink(tmp_path / "telemetry.db") as s:
        yield s


def _samples(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT device, channel, value, sim FROM samples"
        ).fetchall()


def test_ctor_and_status_contract(dll_factory):
    logger, _ = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger)
    status = ampr.get_status()
    assert status["device_id"] == "AMPR1000"
    assert status["port"] == "COM8"
    assert status["com"] == 8
    assert status["baudrate"] == 230400
    assert status["external_lock"] is False
    assert status["test_mode"] is False
    assert "timeout" not in status  # DLL transport has no serial timeout
    assert ampr.hk_interval == 5.0


def test_ampr_connect_opens_port_and_sets_baud(dll_factory):
    logger, records = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger)
    assert ampr.connect() is True
    assert ampr.is_connected is True
    names = dll_factory.last.call_names()
    assert names[0] == "COM_AMPR_12_Open"
    assert names[1] == "COM_AMPR_12_SetBaudRate"
    open_args = dll_factory.last.calls[0][1]
    assert open_args[0].value == 8
    assert any("connected (vendor DLL, 230400 baud)" in r for r in records)


def test_two_amprs_in_one_process_drive_separate_channels(dll_factory):
    # The ampr12 plugin runs AMPR500 (COM6) and AMPR1000 (COM8) in ONE
    # Explorer process. The vendor DLL has one implicit channel per loaded
    # module, so each instance must end up on its own module — otherwise
    # the second connect() steals the first unit's channel (observed on
    # real hardware 2026-07-05: only one unit usable, sets went astray).
    logger, _ = capture_logger()
    a500 = AMPR("AMPR500", 6, logger=logger)
    a1000 = AMPR("AMPR1000", 8, logger=logger)
    assert a500.connect() is True
    assert a1000.connect() is True
    assert len(dll_factory.dlls) == 2
    first_opens = [args[0].value for name, args in dll_factory.dlls[0].calls if name == "COM_AMPR_12_Open"]
    second_opens = [args[0].value for name, args in dll_factory.dlls[1].calls if name == "COM_AMPR_12_Open"]
    assert first_opens == [6]
    assert second_opens == [8]
    # a command on one unit never reaches the other unit's channel
    a1000.set_module_voltage(0, 0, 12.5)
    assert "COM_AMPR_12_SetModuleOutputVoltage" in dll_factory.dlls[1].call_names()
    assert "COM_AMPR_12_SetModuleOutputVoltage" not in dll_factory.dlls[0].call_names()


def test_ampr_connect_failure_never_simulates(dll_factory, sink, tmp_path):
    logger, records = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger, sink=sink)
    dll_factory.last.handlers["COM_AMPR_12_Open"] = lambda *a: -2
    assert ampr.connect() is False
    assert ampr.is_connected is False
    assert any("connect FAILED" in r and "Error opening port" in r for r in records)
    assert _samples(tmp_path / "telemetry.db") == []


def test_ampr_baud_failure_warns_but_connects(dll_factory):
    logger, records = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger)
    dll_factory.last.handlers["COM_AMPR_12_SetBaudRate"] = lambda *a: -16
    assert ampr.connect() is True
    assert any("set_baud_rate returned -16" in r for r in records)


def test_check_raises_cgc_status_error(dll_factory):
    logger, _ = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger)
    with pytest.raises(CGCStatusError) as excinfo:
        ampr._check(-7, "send_command")
    assert excinfo.value.status == -7
    assert "send_command failed" in str(excinfo.value)
    assert "Error sending command" in str(excinfo.value)


def test_pa_bringup_strict_order(dll_factory):
    logger, _ = capture_logger()
    pa = PA("dmmr8_esibd", 7, logger=logger)
    assert pa.connect() is True
    names = dll_factory.last.call_names()
    assert names[:4] == [
        "COM_DMMR_8_Open",
        "COM_DMMR_8_SetBaudRate",
        "COM_DMMR_8_SetEnable",
        "COM_DMMR_8_SetAutomaticCurent",
    ]


def test_pa_bringup_failure_closes_port(dll_factory):
    logger, records = capture_logger()
    pa = PA("dmmr8_esibd", 7, logger=logger)
    dll_factory.last.handlers["COM_DMMR_8_SetEnable"] = lambda *a: -101
    assert pa.connect() is False
    assert pa.is_connected is False
    names = dll_factory.last.call_names()
    assert "COM_DMMR_8_Close" in names
    assert any("Device not ready" in r for r in records)


def test_pa_reconnect_reruns_full_bringup(dll_factory):
    logger, _ = capture_logger()
    pa = PA("dmmr8_esibd", 7, logger=logger)
    assert pa.connect() is True
    assert pa.reconnect() is True
    names = dll_factory.last.call_names()
    assert names.count("COM_DMMR_8_Open") == 2
    assert names.count("COM_DMMR_8_SetEnable") == 2
    assert names.count("COM_DMMR_8_SetAutomaticCurent") == 2
    # The stale handle is closed before the reopen.
    assert names.index("COM_DMMR_8_Close") < names.index("COM_DMMR_8_Open", 1)


def test_ampr_hk_monitor_writes_canonical_samples(dll_factory, sink, tmp_path):
    logger, records = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger, sink=sink)

    def fill_hk(*refs):
        for i, ref in enumerate(refs):
            ref._obj.value = float(i + 1)
        return 0

    dll_factory.last.handlers["COM_AMPR_12_GetHousekeeping"] = fill_hk
    assert ampr.connect() is True
    ampr.hk_monitor()
    rows = _samples(tmp_path / "telemetry.db")
    by_channel = {channel: value for _, channel, value, _ in rows}
    assert by_channel["Volt_12V"] == 1.0
    assert by_channel["Temp_CPU"] == 9.0
    assert by_channel["Line_Freq"] == 14.0
    assert {"Fan_RPM", "CPU_Load", "PSU_Enabled", "Modules_Present"} <= set(by_channel)
    assert all(sim == 0 for _, _, _, sim in rows)
    # Canonical aligned line: device, port, channel, value unit.
    assert any(
        "AMPR1000" in r and "COM8" in r and "Volt_12V" in r and "1.00 V" in r
        for r in records
    )


def test_pa_hk_poke_triggers_immediate_cycle(dll_factory, sink, tmp_path):
    logger, _ = capture_logger()
    pa = PA("dmmr8_esibd", 7, logger=logger, sink=sink, hk_interval=30.0)
    assert pa.connect() is True
    assert pa.start_housekeeping() is True
    try:
        deadline = time.time() + 5.0
        while not _samples(tmp_path / "telemetry.db") and time.time() < deadline:
            time.sleep(0.05)
        first_count = len(_samples(tmp_path / "telemetry.db"))
        assert first_count > 0
        pa.poke_housekeeping()
        deadline = time.time() + 3.0
        while (
            len(_samples(tmp_path / "telemetry.db")) <= first_count
            and time.time() < deadline
        ):
            time.sleep(0.05)
        assert len(_samples(tmp_path / "telemetry.db")) > first_count
    finally:
        pa.stop_housekeeping()


def test_trace_dll_calls_shadows_only_unoverridden_methods(dll_factory):
    logger, records = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger)
    ampr.trace_dll_calls()
    # Raw base method: shadowed on the instance.
    assert "get_buffer_state" in ampr.__dict__
    # Curated lab-layer overrides keep their own logging: never shadowed.
    assert "get_housekeeping" not in ampr.__dict__
    assert "enable_psu" not in ampr.__dict__
    ampr.get_buffer_state()
    assert any("TRACE get_buffer_state args=" in r for r in records)
    assert any("TRACE get_buffer_state ->" in r for r in records)
    ampr.trace_dll_calls(enable=False)
    assert "get_buffer_state" not in ampr.__dict__
    records.clear()
    ampr.get_buffer_state()
    assert not any("TRACE" in r for r in records)


# =============================================================================
#     call_with_retry (purge-retry net for setters, campaign 2026-07-06)
# =============================================================================

def test_call_with_retry_purges_between_attempts_and_recovers(dll_factory):
    from devices.cgc import PSU

    logger, records = capture_logger()
    psu = PSU("psu1", 15, port=0, logger=logger)
    attempts = []

    def flaky(*args):
        attempts.append(args)
        return -13 if len(attempts) == 1 else 0

    dll_factory.last.handlers["COM_HVPSU2D_SetPSUOutputVoltage"] = flaky
    status = psu.call_with_retry(psu.set_psu_output_voltage, 0, 10.0)
    assert status == 0
    names = dll_factory.last.call_names()
    assert names.count("COM_HVPSU2D_SetPSUOutputVoltage") == 2
    first_set = names.index("COM_HVPSU2D_SetPSUOutputVoltage")
    second_set = names.index("COM_HVPSU2D_SetPSUOutputVoltage", first_set + 1)
    assert first_set < names.index("COM_HVPSU2D_Purge") < second_set
    assert any(
        "set_psu_output_voltage returned -13 — purging port and retrying" in r
        for r in records
    )


def test_call_with_retry_gives_up_after_retries(dll_factory):
    from devices.cgc import PSU

    logger, records = capture_logger()
    psu = PSU("psu1", 15, port=0, logger=logger)
    dll_factory.last.handlers["COM_HVPSU2D_SetPSUOutputVoltage"] = lambda *a: -13
    status = psu.call_with_retry(psu.set_psu_output_voltage, 0, 10.0)
    assert status == -13
    names = dll_factory.last.call_names()
    assert names.count("COM_HVPSU2D_SetPSUOutputVoltage") == 2
    assert names.count("COM_HVPSU2D_Purge") == 1
    assert any(
        "set_psu_output_voltage returned -13 after 2 attempts" in r for r in records
    )


def test_call_with_retry_passes_tuple_results_through(dll_factory):
    from devices.cgc import PSU

    logger, _ = capture_logger()
    psu = PSU("psu1", 15, port=0, logger=logger)
    result = psu.call_with_retry(psu.get_psu_data, 0)
    assert isinstance(result, tuple)
    assert result[0] == 0
    assert "COM_HVPSU2D_Purge" not in dll_factory.last.call_names()


def test_call_with_retry_test_mode_skips_purge():
    from devices.cgc import PSU

    logger, records = capture_logger()
    psu = PSU("psu1", 15, port=0, logger=logger, test_mode=True)
    status = psu.call_with_retry(lambda: -13, what="stub_setter")
    assert status == -13
    # purge() is a raw DLL export (real-hardware-only) — the retry loop
    # must not touch it in test mode, and still reports the failure.
    assert any("stub_setter returned -13 after 2 attempts" in r for r in records)


def test_disconnect_close_failure_is_warning_only(dll_factory):
    logger, records = capture_logger()
    ampr = AMPR("AMPR1000", 8, logger=logger)
    assert ampr.connect() is True
    dll_factory.last.handlers["COM_AMPR_12_Close"] = lambda *a: -3
    assert ampr.disconnect() is True
    assert any("close_port returned -3" in r for r in records)
    assert ampr.is_connected is False
