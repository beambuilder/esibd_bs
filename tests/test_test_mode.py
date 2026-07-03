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
        """Sim hk cycle logs Sensor_CH1_On..Sensor_CH6_On (value 0, sim=1)
        alongside the pressure samples."""
        device = factory(sink=sink, test_mode=True)
        device.connect()
        device.hk_monitor()

        rows = _read_samples(sink)
        on_rows = {row[1]: row for row in rows if row[1].endswith("_On")}
        assert set(on_rows) == {f"Sensor_CH{n}_On" for n in range(1, 7)}
        for row in on_rows.values():
            assert row[2] == 0
            assert row[3] == 1

        press_rows = [row for row in rows if row[1].endswith("_Press")]
        assert press_rows, f"{device.device_id}: pressure samples missing from sim hk cycle"

    @pytest.mark.parametrize("factory", TPG_FACTORIES)
    def test_get_sensor_on_false_in_test_mode(self, factory):
        device = factory(test_mode=True)
        device.connect()
        assert device.get_sensor_on(1) is False

    @pytest.mark.parametrize("factory", TPG_FACTORIES)
    def test_sensor_on_off_noop_in_test_mode(self, factory):
        device = factory(test_mode=True)
        device.connect()
        device.sensor_on(1)
        device.sensor_off(1)

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
        device.hk_monitor()

        rows = _read_samples(sink)
        press_channels = {row[1] for row in rows if row[1].endswith("_Press")}
        assert "Sensor_CH3_Press" not in press_channels
        for ch in (1, 2, 4, 5, 6):
            assert f"Sensor_CH{ch}_Press" in press_channels


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
    def test_hipace_get_heating_enabled_guard_in_test_mode(self, factory):
        """get_heating_enabled() reads via the protocol, so it must be
        guarded in test mode just like the other TC400/TC80 getters."""
        pump = factory(test_mode=True)
        pump.connect()
        with pytest.raises(RuntimeError):
            pump.get_heating_enabled()
