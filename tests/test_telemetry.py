"""
Unit tests for the telemetry sinks (ADR-0002: SQLite WAL file).
"""

import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devices.telemetry import SQLiteSink, TelemetrySink


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "telemetry.db"


class TestSQLiteSink:
    """Test cases for SQLiteSink."""

    def test_satisfies_protocol(self, db_path):
        with SQLiteSink(db_path) as sink:
            assert isinstance(sink, TelemetrySink)

    def test_schema_created(self, db_path):
        with SQLiteSink(db_path):
            pass

        conn = sqlite3.connect(db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"samples", "events", "commands"} <= tables

        sample_cols = [row[1] for row in conn.execute("PRAGMA table_info(samples)")]
        assert sample_cols == ["ts", "device", "channel", "value", "sim"]
        event_cols = [row[1] for row in conn.execute("PRAGMA table_info(events)")]
        assert event_cols == ["ts", "source", "level", "message"]
        command_cols = [row[1] for row in conn.execute("PRAGMA table_info(commands)")]
        assert command_cols == ["ts", "device", "action", "value", "ok", "source", "sim"]
        conn.close()

    def test_commands_table_added_to_existing_db(self, db_path):
        """Pre-audit-trail telemetry.db (no commands table) upgrades in place
        on the next sink open — no migration step."""
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE samples (ts REAL NOT NULL, device TEXT NOT NULL, "
            "channel TEXT NOT NULL, value REAL NOT NULL, "
            "sim INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "CREATE TABLE events (ts REAL NOT NULL, source TEXT NOT NULL, "
            "level TEXT NOT NULL, message TEXT NOT NULL)"
        )
        conn.commit()
        conn.close()

        with SQLiteSink(db_path) as sink:
            sink.write_command("HiScroll_1", "stop")

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
        conn.close()
        assert count == 1

    def test_wal_mode(self, db_path):
        with SQLiteSink(db_path):
            conn = sqlite3.connect(db_path)
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            conn.close()
            assert mode == "wal"

    def test_write_sample(self, db_path):
        with SQLiteSink(db_path) as sink:
            before = time.time()
            sink.write("Chiller_A", "Cur_Temp", 19.85)
            sink.write("Chiller_A", "Cur_Temp", 20.05, ts=1234.5, sim=1)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT ts, device, channel, value, sim FROM samples ORDER BY rowid"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        ts0, device0, channel0, value0, sim0 = rows[0]
        assert ts0 >= before
        assert (device0, channel0, value0, sim0) == ("Chiller_A", "Cur_Temp", 19.85, 0)
        assert rows[1] == (1234.5, "Chiller_A", "Cur_Temp", 20.05, 1)

    def test_write_event(self, db_path):
        with SQLiteSink(db_path) as sink:
            sink.write_event("Chiller_A", "ERROR", "connect FAILED: timeout")

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT source, level, message FROM events").fetchall()
        conn.close()
        assert rows == [("Chiller_A", "ERROR", "connect FAILED: timeout")]

    def test_write_command(self, db_path):
        with SQLiteSink(db_path) as sink:
            before = time.time()
            sink.write_command("HiScroll_1", "stop", source="pump_locker")
            sink.write_command(
                "Chiller_A", "setting:set_temp", value=18.0, ok=0,
                source="chillers", ts=1234.5, sim=1,
            )

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT ts, device, action, value, ok, source, sim FROM commands "
            "ORDER BY rowid"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        ts0, device0, action0, value0, ok0, source0, sim0 = rows[0]
        assert ts0 >= before
        assert (device0, action0, value0, ok0, source0, sim0) == (
            "HiScroll_1", "stop", None, 1, "pump_locker", 0
        )
        assert rows[1] == (
            1234.5, "Chiller_A", "setting:set_temp", 18.0, 0, "chillers", 1
        )

    def test_readonly_uri_reader(self, db_path):
        """Dashboard/watchdog read pattern: URI mode=ro sees committed rows."""
        with SQLiteSink(db_path) as sink:
            sink.write("dev", "chan", 1.0)

            ro = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            count = ro.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
            ro.close()
            assert count == 1

    def test_concurrent_writes(self, db_path):
        """Multiple threads writing through one sink must not lose rows."""
        n_threads, n_writes = 5, 20

        with SQLiteSink(db_path) as sink:
            def worker(idx):
                for i in range(n_writes):
                    sink.write(f"dev{idx}", "chan", float(i))

            threads = [
                threading.Thread(target=worker, args=(idx,))
                for idx in range(n_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
        conn.close()
        assert count == n_threads * n_writes

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "sub" / "dir" / "telemetry.db"
        with SQLiteSink(nested) as sink:
            sink.write("dev", "chan", 1.0)
        assert nested.exists()
