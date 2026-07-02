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
