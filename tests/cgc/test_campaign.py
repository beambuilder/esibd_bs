"""
Switch-campaign tooling tests (devices.cgc.campaign): the soft PSU
watchdog against fake readings (the P6.8 "watchdog vs fake PSU readings"
gate) and the recipe-enforcing ramp helpers, all on test_mode devices —
no DLL, no hardware, no sleeping (injected no-op sleep).
"""
import ctypes
import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from conftest import capture_logger
from devices.cgc import PSU, SW, SWHR
from devices.cgc.campaign import (
    PSUWatchdog, WatchdogBreach, ramp_voltage_at_1khz, ramp_frequency,
    I_LIMIT_MA, P_LIMIT_W, RAMP_FREQ_KHZ,
)


@pytest.fixture(autouse=True)
def forbid_windll(monkeypatch):
    def boom(path):
        raise AssertionError(f"campaign tests must never load a DLL ({path})")

    monkeypatch.setattr(ctypes, "WinDLL", boom)


def _sim_psu(device_id="PSU1", com=15, port=0):
    logger, records = capture_logger()
    psu = PSU(device_id, com, port=port, logger=logger, test_mode=True)
    psu.connect()
    return psu, records


def _fake_reading(psu, voltage_v, current_ma):
    """Patch one PSU instance's readback to a fixed V/I on both outputs."""
    psu.get_psu_data = lambda psu_num: (
        psu.NO_ERR, voltage_v, current_ma / 1000.0, 3.0
    )


# =============================================================================
#     Watchdog
# =============================================================================

def test_watchdog_all_clear_when_within_limits(monkeypatch):
    psu, _ = _sim_psu()
    _fake_reading(psu, 350.0, 280.0)  # 280 mA, 98 W: inside both limits
    dog = PSUWatchdog([psu])
    assert dog.check() == []


def test_watchdog_current_breach_steps_setpoint_down(monkeypatch):
    psu, records = _sim_psu()
    psu.set_psu_output_voltage(psu.PSU_POS, 100.0)
    _fake_reading(psu, 100.0, 350.0)  # 350 mA > 300 mA (35 W: power fine)
    dog = PSUWatchdog([psu])
    breaches = dog.check()
    assert len(breaches) == 2  # both outputs report the fake reading
    assert all(b["over_i"] and not b["over_p"] for b in breaches)
    # Default action: 10 % step-down on the setpoint.
    status, v_set, _ = psu.get_psu_set_output_voltage(psu.PSU_POS)
    assert v_set == pytest.approx(90.0)
    assert any("WATCHDOG BREACH" in r for r in records)


def test_watchdog_power_breach_without_current_breach(monkeypatch):
    psu, _ = _sim_psu()
    _fake_reading(psu, 350.0, 290.0)  # 290 mA under, 101.5 W over
    dog = PSUWatchdog([psu])
    breaches = dog.check()
    assert breaches
    assert all(b["over_p"] and not b["over_i"] for b in breaches)


def test_watchdog_second_consecutive_breach_disables_outputs(monkeypatch):
    psu, records = _sim_psu()
    psu.set_device_enable(True)
    psu.set_psu_enable(True, True)
    psu.set_psu_output_voltage(psu.PSU_POS, 100.0)
    _fake_reading(psu, 100.0, 400.0)
    dog = PSUWatchdog([psu])
    dog.check()  # first breach: step-down only, outputs stay on
    assert psu.get_psu_enable() == (psu.NO_ERR, True, True)
    dog.check()  # second consecutive breach: abort
    assert psu.get_psu_enable() == (psu.NO_ERR, False, False)
    assert any("disabling both outputs" in r for r in records)


def test_watchdog_recovery_resets_consecutive_counter(monkeypatch):
    psu, _ = _sim_psu()
    psu.set_device_enable(True)
    psu.set_psu_enable(True, True)
    dog = PSUWatchdog([psu])
    _fake_reading(psu, 100.0, 400.0)
    dog.check()  # breach #1
    _fake_reading(psu, 100.0, 100.0)
    assert dog.check() == []  # recovered -> counter reset
    _fake_reading(psu, 100.0, 400.0)
    dog.check()  # counts as #1 again, NOT #2
    assert psu.get_psu_enable() == (psu.NO_ERR, True, True)


def test_watchdog_custom_on_breach_replaces_default_action(monkeypatch):
    psu, _ = _sim_psu()
    psu.set_psu_output_voltage(psu.PSU_POS, 100.0)
    _fake_reading(psu, 100.0, 400.0)
    seen = []
    dog = PSUWatchdog(
        [psu], on_breach=lambda p, n, reading, consecutive: seen.append(n)
    )
    dog.check()
    assert seen == [psu.PSU_POS, psu.PSU_NEG]
    # Default step-down must NOT have run.
    assert psu.get_psu_set_output_voltage(psu.PSU_POS)[1] == pytest.approx(100.0)


def test_watchdog_limits_are_the_cgc_numbers():
    assert I_LIMIT_MA == 300.0
    assert P_LIMIT_W == 100.0


def test_watchdog_purges_and_retries_on_bad_status():
    # Poisoned-RX-buffer recovery (bench 2026-07-06): a nonzero status on
    # real hardware purges the port and retries the read once.
    psu, records = _sim_psu()
    psu.test_mode = False  # take the real-hardware path in _read
    calls = []
    readings = iter([(-13, 0.0, 0.0, 0.0), (psu.NO_ERR, 100.0, 0.1, 3.0)])
    psu.get_psu_data = lambda psu_num: next(readings)
    psu.purge = lambda: calls.append("purge") or 0
    dog = PSUWatchdog([psu])
    reading = dog._read(psu, psu.PSU_POS)
    assert calls == ["purge"]
    assert reading is not None
    assert reading["voltage_v"] == pytest.approx(100.0)
    assert any("purging + retrying" in r for r in records)


def test_watchdog_gives_up_after_failed_purge_retry():
    psu, records = _sim_psu()
    psu.test_mode = False
    psu.get_psu_data = lambda psu_num: (-13, 0.0, 0.0, 0.0)
    psu.purge = lambda: 0
    dog = PSUWatchdog([psu])
    assert dog._read(psu, psu.PSU_POS) is None
    assert dog.check() == []  # bad reads never count as breaches
    assert any("returned -13" in r for r in records)


def test_watchdog_never_purges_in_test_mode():
    # purge() is a raw DLL export — real-hardware-only. Simulated
    # devices must never reach it, even on a nonzero status.
    psu, _ = _sim_psu()
    psu.get_psu_data = lambda psu_num: (psu.ERR_ARGUMENT, 0.0, 0.0, 0.0)
    dog = PSUWatchdog([psu])
    assert dog._read(psu, psu.PSU_POS) is None  # no AttributeError


# =============================================================================
#     Ramp helpers (recipe order: voltage at 1 kHz first, then frequency)
# =============================================================================

def test_ramp_voltage_sets_1khz_first_then_steps_to_target():
    psu, _ = _sim_psu()
    logger, _ = capture_logger()
    sw = SW("swB", 19, logger=logger, test_mode=True)
    sw.connect()
    sw.set_frequency_khz(500)  # deliberately wrong frequency before ramp
    final = ramp_voltage_at_1khz(
        sw, psu, psu.PSU_POS, 50.0, step_v=10.0, dwell_s=0,
        sleep=lambda s: None,
    )
    assert final == 50.0
    # Recipe: the switch was forced back to 1 kHz before any voltage step.
    status, period = sw.get_oscillator_period()
    assert period == round(sw.CLOCK / (RAMP_FREQ_KHZ * 1000) - sw.OSC_OFFSET)
    assert psu.get_psu_set_output_voltage(psu.PSU_POS)[1] == pytest.approx(50.0)


def test_ramp_voltage_rejects_targets_above_ceiling():
    psu, _ = _sim_psu()
    logger, _ = capture_logger()
    sw = SW("swB", 19, logger=logger, test_mode=True)
    sw.connect()
    with pytest.raises(ValueError):
        ramp_voltage_at_1khz(sw, psu, psu.PSU_POS, 400.0, sleep=lambda s: None)


def test_ramp_voltage_stops_on_watchdog_breach():
    psu, _ = _sim_psu()
    psu.set_device_enable(True)
    psu.set_psu_enable(True, True)
    _fake_reading(psu, 100.0, 400.0)  # every poll breaches
    logger, _ = capture_logger()
    sw = SW("swB", 19, logger=logger, test_mode=True)
    sw.connect()
    dog = PSUWatchdog([psu])
    with pytest.raises(WatchdogBreach):
        ramp_voltage_at_1khz(
            sw, psu, psu.PSU_POS, 100.0, step_v=10.0, dwell_s=0,
            watchdog=dog, sleep=lambda s: None,
        )
    # The watchdog acted before the ramp aborted: setpoint stepped down.
    assert psu.get_psu_set_output_voltage(psu.PSU_POS)[1] < 10.0


def test_ramp_frequency_doubles_to_target():
    logger, _ = capture_logger()
    sw = SW("swB", 19, logger=logger, test_mode=True)
    sw.connect()
    final = ramp_frequency(sw, 100.0, dwell_s=0, sleep=lambda s: None)
    assert final == 100.0
    status, period = sw.get_oscillator_period()
    assert period == round(sw.CLOCK / 100e3 - sw.OSC_OFFSET)


def test_ramp_frequency_stops_on_watchdog_breach():
    psu, _ = _sim_psu()
    _fake_reading(psu, 350.0, 400.0)
    logger, _ = capture_logger()
    sw = SW("swB", 19, logger=logger, test_mode=True)
    sw.connect()
    dog = PSUWatchdog([psu])
    with pytest.raises(WatchdogBreach):
        ramp_frequency(sw, 1000.0, dwell_s=0, watchdog=dog,
                       sleep=lambda s: None)


def test_ramp_helpers_dispatch_swhr_oscillator_argument():
    psu, _ = _sim_psu()
    logger, _ = capture_logger()
    swhr = SWHR("swA", 20, logger=logger, test_mode=True)
    swhr.connect()
    ramp_voltage_at_1khz(
        swhr, psu, psu.PSU_POS, 20.0, step_v=10.0, dwell_s=0,
        oscillator=0, sleep=lambda s: None,
    )
    status, period = swhr.get_oscillator_period(0)
    assert period == round(swhr.DEF_CLOCK / 1000.0 - swhr.OSC_OFFSET)
    final = ramp_frequency(swhr, 8.0, dwell_s=0, oscillator=0,
                           sleep=lambda s: None)
    assert final == 8.0
    status, period = swhr.get_oscillator_period(0)
    assert period == round(swhr.DEF_CLOCK / 8000.0 - swhr.OSC_OFFSET)
