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
        assert {"samples", "events"} <= tables

        sample_cols = [row[1] for row in conn.execute("PRAGMA table_info(samples)")]
        assert sample_cols == ["ts", "device", "channel", "value", "sim"]
        event_cols = [row[1] for row in conn.execute("PRAGMA table_info(events)")]
        assert event_cols == ["ts", "source", "level", "message"]
        conn.close()

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
