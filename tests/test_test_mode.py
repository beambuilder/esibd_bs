"""
Cross-family tests for explicit test mode (simulators), the canonical log
format, and the never-auto-simulate rule.
"""

import logging
import re
import sqlite3
import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devices import Chiller, PumpArduino, TrafoArduino, SQLiteSink
from devices.pfeiffer.hipacebus import HiPace80Bus, HiPace300Bus
from devices.pfeiffer.hiscroll12 import HiScroll12
from devices.pfeiffer.tpg366 import TPG366, TPG366TCP
from devices.syringe_pump import SyringePump

# One factory per family; every device gets sink + test_mode injected.
DEVICE_FACTORIES = [
    lambda **kw: Chiller("Chiller_A", port="COM90", **kw),
    lambda **kw: PumpArduino("pump_ard", port="COM91", **kw),
    lambda **kw: TrafoArduino("trafo_ard", port="COM92", **kw),
    lambda **kw: TPG366("TPG366", port="COM93", **kw),
    lambda **kw: TPG366TCP("TPG366_tcp", host="127.0.0.1", **kw),
    lambda **kw: HiScroll12("HiScroll_T", port="COM94", **kw),
    lambda **kw: HiPace300Bus("HiPace_QMS", port="COM95", gauge1_address=5, **kw),
    lambda **kw: HiPace80Bus("HiPace_LL1", port="COM96", gauge1_address=5, **kw),
    lambda **kw: SyringePump("syringe", port="COM97", **kw),
]

# HiPace turbo pump bus factories, for tests specific to their heating readback.
HIPACE_FACTORIES = [
    lambda **kw: HiPace300Bus("HiPace_QMS", port="COM95", gauge1_address=5, **kw),
    lambda **kw: HiPace80Bus("HiPace_LL1", port="COM96", gauge1_address=5, **kw),
]

# TPG366 factories (serial + TCP), for tests specific to per-channel sensor on/off.
TPG_FACTORIES = [
    lambda **kw: TPG366("TPG366", port="COM93", **kw),
    lambda **kw: TPG366TCP("TPG366_tcp", host="127.0.0.1", **kw),
]

# Canonical sample line: "[SIM] device  port  channel  value [unit]"
SAMPLE_LINE_RE = re.compile(
    r"^\[SIM\] \S+\s+\S+\s+\S+\s+\S.*$"
)


@pytest.fixture
def sink(tmp_path):
    with SQLiteSink(tmp_path / "telemetry.db") as s:
        yield s


def _read_samples(sink):
    conn = sqlite3.connect(sink.db_path)
    rows = conn.execute("SELECT device, channel, value, sim FROM samples").fetchall()
    conn.close()
    return rows


def _read_events(sink):
    conn = sqlite3.connect(sink.db_path)
    rows = conn.execute("SELECT source, level, message FROM events").fetchall()
    conn.close()
    return rows


class TestTestMode:
    """Simulators: same channels, same log format, sim=1 everywhere."""

    @pytest.mark.parametrize("factory", DEVICE_FACTORIES)
    def test_sim_connect_and_hk_cycle(self, factory, sink, caplog):
        device = factory(sink=sink, test_mode=True)
        device.logger.setLevel(logging.INFO)

        assert device.connect() is True
        assert device.is_connected is True

        device.hk_monitor()

        rows = _read_samples(sink)
        assert rows, f"{device.device_id}: hk cycle produced no samples"
        assert all(sim == 1 for _, _, _, sim in rows), "simulated samples must carry sim=1"
        assert all(device.device_id == dev for dev, _, _, _ in rows)

        # Every sample line follows the canonical [SIM]-marked aligned format.
        sample_lines = [
            record.getMessage()
            for record in caplog.records
            if record.levelno == logging.INFO
            and re.search(r"\d|True|False|OK|RUNNING|stopped|pumping", record.getMessage())
        ]
        assert sample_lines
        for line in sample_lines:
            assert line.startswith("[SIM] "), f"missing [SIM] marker: {line!r}"

        assert device.disconnect() is True

    @pytest.mark.parametrize("factory", DEVICE_FACTORIES)
    def test_repeated_cycles_stable(self, factory, sink):
        """Simulators must survive many housekeeping cycles."""
        device = factory(sink=sink, test_mode=True)
        device.connect()
        for _ in range(5):
            device.hk_monitor()
        # 5 cycles, each writing at least one sample
        assert len(_read_samples(sink)) >= 5

    def test_log_format_matches_canonical(self, sink, caplog):
        """Spot-check the exact canonical layout on one device."""
        chiller = Chiller("Chiller_A", port="COM90", sink=sink, test_mode=True)
        chiller.logger.setLevel(logging.INFO)
        chiller.connect()
        chiller.hk_monitor()

        cur_temp_lines = [
            record.getMessage()
            for record in caplog.records
            if "Cur_Temp" in record.getMessage()
        ]
        assert len(cur_temp_lines) == 1
        line = cur_temp_lines[0]
        assert SAMPLE_LINE_RE.match(line)
        # aligned columns: device, port, channel, value + unit
        assert re.match(
            r"^\[SIM\] Chiller_A\s+COM90\s+Cur_Temp\s+\d+\.\d{2} degC$", line
        )

    def test_chiller_running_channel_follows_start_stop(self, sink):
        """Numeric Running channel (dashboard run/standby switch): the sim
        starts RUNNING, stop_device flips it to standby, start_device back."""
        chiller = Chiller("Chiller_A", port="COM90", sink=sink, test_mode=True)
        chiller.connect()
        chiller.hk_monitor()
        chiller.stop_device()
        chiller.hk_monitor()
        chiller.start_device()
        chiller.hk_monitor()

        values = [row[2] for row in _read_samples(sink) if row[1] == "Running"]
        assert values == [1.0, 0.0, 1.0]

    @pytest.mark.parametrize("factory", HIPACE_FACTORIES)
    def test_heating_enabled_in_sim_hk_cycle(self, factory, sink):
        """HiPace heating readback: Heating_Enabled channel is part of the
        simulated housekeeping cycle."""
        device = factory(sink=sink, test_mode=True)
        device.connect()
        device.hk_monitor()

        rows = _read_samples(sink)
        heating_rows = [row for row in rows if row[1] == "Heating_Enabled"]
        assert heating_rows, f"{device.device_id}: Heating_Enabled missing from sim hk cycle"
        assert heating_rows[0][2] == 0
        assert heating_rows[0][3] == 1


class TestTPG366SensorControl:
    """TPG366/TPG366TCP per-channel sensor on/off — explicit-caller only, never automatic."""

    @pytest.mark.parametrize("factory", TPG_FACTORIES)
    def test_sensor_on_states_in_sim_hk_cycle(self, factory, sink):
        """Sim hk cycle logs Sensor_CH1_On..Sensor_CH6_On (sim default:
        CH1-3 on, CH4-6 off) and pressure samples only for the on channels
        (off channels read 0.0 and are skipped, like hardware)."""
        device = factory(sink=sink, test_mode=True)
        device.connect()
        device.hk_monitor()

        rows = _read_samples(sink)
        on_rows = {row[1]: row for row in rows if row[1].endswith("_On")}
        assert set(on_rows) == {f"Sensor_CH{n}_On" for n in range(1, 7)}
        for n in range(1, 7):
            row = on_rows[f"Sensor_CH{n}_On"]
            assert row[2] == (1 if n <= 3 else 0)
            assert row[3] == 1

        press_channels = {row[1] for row in rows if row[1].endswith("_Press")}
        assert press_channels == {f"Sensor_CH{n}_Press" for n in (1, 2, 3)}

    @pytest.mark.parametrize("factory", TPG_FACTORIES)
    def test_sensor_on_off_flips_sim_state(self, factory):
        """sensor_on/off must drive the simulated state so the dashboard
        buttons have the same visible effect as on hardware."""
        device = factory(test_mode=True)
        device.connect()
        assert device.get_sensor_on(1) is True   # sim default: CH1-3 on
        assert device.get_sensor_on(4) is False  # sim default: CH4-6 off

        device.sensor_off(1)
        assert device.get_sensor_on(1) is False
        assert device.read_pressure_value(1) == 0.0

        device.sensor_on(4)
        assert device.get_sensor_on(4) is True
        assert device.read_pressure_value(4) > 0.0

    @pytest.mark.parametrize("method", ["sensor_on", "sensor_off", "get_sensor_on"])
    @pytest.mark.parametrize("channel", [0, 7, "3"])
    @pytest.mark.parametrize("factory", TPG_FACTORIES)
    def test_invalid_channel_raises_value_error(self, factory, channel, method):
        device = factory(test_mode=True)
        device.connect()
        with pytest.raises(ValueError):
            getattr(device, method)(channel)

    @pytest.mark.parametrize("factory", TPG_FACTORIES)
    def test_zero_pressure_excluded_from_hk_cycle(self, factory, monkeypatch, sink):
        """Zero mantissa (sensor off / no measurement) must not reach the sink."""
        original_read = TPG366.read_pressure_value

        def patched(self, channel):
            if channel == 3:
                return 0.0
            return original_read(self, channel)

        monkeypatch.setattr(TPG366, "read_pressure_value", patched)

        device = factory(sink=sink, test_mode=True)
        device.connect()
        for channel in range(1, 7):  # all sensors on; only the 0.0 patch excludes
            device.sensor_on(channel)
        device.hk_monitor()

        rows = _read_samples(sink)
        press_channels = {row[1] for row in rows if row[1].endswith("_Press")}
        assert "Sensor_CH3_Press" not in press_channels
        for ch in (1, 2, 4, 5, 6):
            assert f"Sensor_CH{ch}_Press" in press_channels

    @pytest.mark.parametrize("factory", TPG_FACTORIES)
    def test_frozen_register_off_sensor_not_logged(self, factory, monkeypatch, sink):
        """The actual hardware bug (found overnight on the real TPG366,
        2026-07-03): a deactivated sensor returns its LAST measured value,
        frozen, instead of the zero-mantissa telegram. hk_monitor must gate
        the pressure read/log on get_sensor_on(), not on value==0.0 — before
        the fix, this test fails because the stale non-zero value gets
        logged for the off channel every cycle."""
        original_get_sensor_on = TPG366.get_sensor_on

        def patched_get_sensor_on(self, channel):
            if channel == 2:
                return False
            return original_get_sensor_on(self, channel)

        monkeypatch.setattr(TPG366, "get_sensor_on", patched_get_sensor_on)
        # Every channel's register is "frozen" on a stale non-zero reading,
        # like the hardware CH4/CH5 the pressure was frozen on overnight.
        monkeypatch.setattr(TPG366, "read_pressure_value", lambda self, channel: 4.2e-8)

        device = factory(sink=sink, test_mode=True)
        device.connect()
        device.hk_monitor()

        rows = _read_samples(sink)
        on_rows = {row[1]: row[2] for row in rows if row[1].endswith("_On")}
        assert on_rows["Sensor_CH2_On"] == 0

        press_channels = {row[1] for row in rows if row[1].endswith("_Press")}
        assert "Sensor_CH2_Press" not in press_channels

    @pytest.mark.parametrize("factory", TPG_FACTORIES)
    def test_over_range_sentinel_not_logged(self, factory, monkeypatch, sink):
        """The 2026-07-06 hardware finding (Collision_Cell, same telegram
        format): a gauge with no valid measurement answers the all-nines
        u_expo_new sentinel "999999" (= 9.999e+79 hPa) in checksum-valid
        frames while reporting sensor ON. hk_monitor must skip it like the
        0.0 sensor-off value — before the fix it lands in telemetry and
        wrecks autoscaled pressure plots."""
        monkeypatch.setattr(TPG366, "read_pressure_value", lambda self, channel: 9.999e79)

        device = factory(sink=sink, test_mode=True)
        device.connect()
        device.hk_monitor()

        rows = _read_samples(sink)
        on_rows = {row[1]: row[2] for row in rows if row[1].endswith("_On")}
        assert on_rows  # sensor states still logged
        assert not any(row[1].endswith("_Press") for row in rows)

    @pytest.mark.parametrize("factory", TPG_FACTORIES)
    def test_state_read_failure_falls_back_to_pressure_read(self, factory, monkeypatch, sink):
        """A transient get_sensor_on() failure must not black-hole real
        pressure data: hk_monitor falls back to the old read-and-log
        behavior for that channel, plus a warning event recording the
        state-read failure."""

        def raising_get_sensor_on(self, channel):
            if channel == 2:
                raise TimeoutError("no response from CH2")
            return True

        monkeypatch.setattr(TPG366, "get_sensor_on", raising_get_sensor_on)
        monkeypatch.setattr(TPG366, "read_pressure_value", lambda self, channel: 4.2e-8)

        device = factory(sink=sink, test_mode=True)
        device.connect()
        device.hk_monitor()

        rows = _read_samples(sink)
        press_by_channel = {row[1]: row[2] for row in rows if row[1].endswith("_Press")}
        assert press_by_channel.get("Sensor_CH2_Press") == 4.2e-8

        events = _read_events(sink)
        assert any(
            level == "WARNING" and "Sensor_CH2_On read failed" in message
            for _, level, message in events
        )


class TestNeverAutoSimulate:
    """A failed real connect must stay a loud error — never fake data."""

    def test_failed_connect_returns_false(self, sink):
        chiller = Chiller("Chiller_real", port="COM_NO_SUCH_PORT", sink=sink)

        assert chiller.connect() is False
        assert chiller.is_connected is False
        assert chiller.test_mode is False

        # No samples may exist; the failure is recorded as an event.
        assert _read_samples(sink) == []
        conn = sqlite3.connect(sink.db_path)
        events = conn.execute(
            "SELECT level, message FROM events WHERE level='ERROR'"
        ).fetchall()
        conn.close()
        assert any("connect FAILED" in message for _, message in events)

    def test_housekeeping_refuses_when_not_connected(self, sink):
        chiller = Chiller("Chiller_real", port="COM_NO_SUCH_PORT", sink=sink)
        chiller.connect()

        assert chiller.start_housekeeping() is False
        assert chiller.do_housekeeping_cycle() is False
        assert _read_samples(sink) == []

    def test_pfeiffer_protocol_guard_in_test_mode(self):
        """Protocol-level access in test mode fails loudly, not silently."""
        pump = HiScroll12("HiScroll_T", port="COM94", test_mode=True)
        pump.connect()
        with pytest.raises(RuntimeError):
            pump.query_parameter(303)

    @pytest.mark.parametrize("factory", HIPACE_FACTORIES)
    def test_hipace_unsimulated_param_guard_in_test_mode(self, factory):
        """Parameters without a stateful simulation entry must still fail
        loudly in test mode (never silently fake a protocol read)."""
        pump = factory(test_mode=True)
        pump.connect()
        with pytest.raises(RuntimeError):
            pump.is_target_speed_reached()


class TestHiPaceSimState:
    """HiPace stateful simulation: the setters the ctrl API calls must have
    the same visible effect on simulated data as on hardware."""

    @pytest.mark.parametrize("factory", HIPACE_FACTORIES)
    def test_pump_stop_start_reflected_in_sim_hk(self, factory, sink):
        device = factory(sink=sink, test_mode=True)
        device.connect()

        device.disable_pumpStatn()
        assert device.get_pumpStatn_enabled() is False
        device.hk_monitor()
        rows = {row[1]: row[2] for row in _read_samples(sink)}
        assert rows["Pump_Station_Enabled"] == 0
        assert rows["Speed_Actual_RPM"] == 0

        device.enable_pumpStatn()
        assert device.get_pumpStatn_enabled() is True
        device.hk_monitor()
        rows = {row[1]: row[2] for row in _read_samples(sink)[len(rows):]}
        assert rows["Pump_Station_Enabled"] == 1
        assert rows["Speed_Actual_RPM"] > 0

    @pytest.mark.parametrize("factory", HIPACE_FACTORIES)
    def test_heating_toggle_reflected_in_sim(self, factory, sink):
        device = factory(sink=sink, test_mode=True)
        device.connect()
        assert device.get_heating_enabled() is False

        device.enable_heating()
        assert device.get_heating_enabled() is True
        device.hk_monitor()
        heating = [row for row in _read_samples(sink) if row[1] == "Heating_Enabled"]
        assert heating[-1][2] == 1

        device.disable_heating()
        assert device.get_heating_enabled() is False

    @pytest.mark.parametrize("factory", HIPACE_FACTORIES)
    def test_gauge_channels_in_sim_hk_cycle(self, factory, sink):
        """A configured OmniControl gauge logs Gauge_Sensor_On and (while on)
        Gauge_Pressure; set_SensOnOff(False) turns the pressure into a gap."""
        device = factory(sink=sink, test_mode=True)
        device.connect()

        assert device.get_SensOnOff() is True  # sim default: gauge measuring
        device.hk_monitor()
        rows = _read_samples(sink)
        by_channel = {row[1]: row for row in rows}
        assert by_channel["Gauge_Sensor_On"][2] == 1
        assert 0.0 < by_channel["Gauge_Pressure"][2] < 1e-5

        device.set_SensOnOff(False)
        assert device.get_SensOnOff() is False
        assert device.get_gauge_pressure() == 0.0
        before = len(rows)
        device.hk_monitor()
        new_rows = _read_samples(sink)[before:]
        new_by_channel = {row[1]: row for row in new_rows}
        assert new_by_channel["Gauge_Sensor_On"][2] == 0
        assert "Gauge_Pressure" not in new_by_channel

    @pytest.mark.parametrize("factory", HIPACE_FACTORIES)
    def test_gauge_frozen_register_off_not_logged(self, factory, monkeypatch, sink):
        """The same hardware bug as TPG366, for the OmniControl gauge: a
        deactivated gauge can return its last measured (non-zero) pressure,
        frozen, instead of 0.0. hk_monitor must gate the pressure read/log
        on get_SensOnOff(), not on pressure==0.0."""
        device = factory(sink=sink, test_mode=True)
        device.connect()

        device.set_SensOnOff(False)
        assert device.get_SensOnOff() is False
        # Register "frozen" on a stale non-zero reading despite being off.
        monkeypatch.setattr(type(device), "get_gauge_pressure", lambda self: 4.2e-8)

        device.hk_monitor()

        rows = _read_samples(sink)
        by_channel = {row[1]: row for row in rows}
        assert by_channel["Gauge_Sensor_On"][2] == 0
        assert "Gauge_Pressure" not in by_channel

    @pytest.mark.parametrize("factory", HIPACE_FACTORIES)
    def test_gauge_over_range_sentinel_not_logged(self, factory, monkeypatch, sink):
        """The 2026-07-06 hardware finding (Collision_Cell at atmosphere):
        the over-ranged cold-cathode gauge answers the all-nines u_expo_new
        sentinel "999999" (= 9.999e+79 hPa) in checksum-valid frames while
        Gauge_Sensor_On stays 1. hk_monitor must skip it like the 0.0
        sensor-off value — before the fix, 126 bogus samples landed in
        telemetry.db in one morning."""
        device = factory(sink=sink, test_mode=True)
        device.connect()

        assert device.get_SensOnOff() is True  # gauge reports measuring
        monkeypatch.setattr(type(device), "get_gauge_pressure", lambda self: 9.999e79)

        device.hk_monitor()

        rows = _read_samples(sink)
        by_channel = {row[1]: row for row in rows}
        assert by_channel["Gauge_Sensor_On"][2] == 1
        assert "Gauge_Pressure" not in by_channel

    @pytest.mark.parametrize(
        "factory",
        [
            lambda **kw: HiPace300Bus("HiPace_Transfer", port="COM95", **kw),
            lambda **kw: HiPace80Bus("HiPace_LL2", port="COM96", **kw),
        ],
    )
    def test_no_gauge_configured(self, factory, sink):
        """Without gauge1_address there are no Gauge_* channels, and the
        gauge accessors fail like on hardware (unknown channel)."""
        device = factory(sink=sink, test_mode=True)
        device.connect()
        device.hk_monitor()
        channels = {row[1] for row in _read_samples(sink)}
        assert not any(ch.startswith("Gauge_") for ch in channels)
        with pytest.raises(ValueError):
            device.set_SensOnOff(True)
        assert device.get_gauge_pressure() == 0.0  # off/no gauge reads zero
