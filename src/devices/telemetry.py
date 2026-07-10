"""
Telemetry sinks for device housekeeping data.

Device classes accept an optional ``sink`` (see ``TelemetrySink``) and emit
one sample per housekeeping channel. ``SQLiteSink`` is the stdlib-only
reference implementation writing to the shared ``telemetry.db`` (SQLite,
WAL mode) defined in ADR-0002:

    samples(ts REAL, device TEXT, channel TEXT, value REAL,
            sim INTEGER DEFAULT 0)          index (device, channel, ts)
    events(ts REAL, source TEXT, level TEXT, message TEXT)
    commands(ts REAL, device TEXT, action TEXT, value REAL,
             ok INTEGER, source TEXT, sim INTEGER)   index (device, ts)

The ``commands`` table is the audit trail of every operation issued
through a ctrl API (pump start/stop, settings, sensor toggles, ...).
The alert engine uses it to tell an operator-commanded stop from a
device that shut itself down.

Writers are the control processes owning the hardware; readers (dashboard,
watchdog) open the file read-only (URI ``mode=ro``). Simulated samples
(device in ``test_mode``) always carry ``sim=1`` so no consumer can mistake
them for real lab data.
"""
from pathlib import Path
from typing import Optional, Protocol, Union, runtime_checkable
import sqlite3
import threading
import time


_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts      REAL    NOT NULL,
    device  TEXT    NOT NULL,
    channel TEXT    NOT NULL,
    value   REAL    NOT NULL,
    sim     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_samples_device_channel_ts
    ON samples (device, channel, ts);
CREATE TABLE IF NOT EXISTS events (
    ts      REAL NOT NULL,
    source  TEXT NOT NULL,
    level   TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);
CREATE TABLE IF NOT EXISTS commands (
    ts      REAL    NOT NULL,
    device  TEXT    NOT NULL,
    action  TEXT    NOT NULL,
    value   REAL,
    ok      INTEGER NOT NULL DEFAULT 1,
    source  TEXT    NOT NULL DEFAULT '',
    sim     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_commands_device_ts ON commands (device, ts);
"""


@runtime_checkable
class TelemetrySink(Protocol):
    """
    Protocol for telemetry sinks injected into device classes.

    Any object with these methods can be passed as ``sink=`` to a device;
    the device calls ``write()`` once per channel per housekeeping cycle.
    """

    def write(
        self,
        device_id: str,
        channel: str,
        value: float,
        ts: Optional[float] = None,
        sim: int = 0,
    ) -> None:
        """Store one sample. ``ts`` defaults to now; ``sim=1`` marks simulated data."""
        ...

    def write_event(
        self,
        source: str,
        level: str,
        message: str,
        ts: Optional[float] = None,
    ) -> None:
        """Store one event (connect, disconnect, error, ...)."""
        ...

    def close(self) -> None:
        """Release resources. Devices do not call this; the owner process does."""
        ...


class SQLiteSink:
    """
    Thread-safe SQLite implementation of ``TelemetrySink`` (stdlib only).

    Opens (and creates if needed) the telemetry database in WAL mode with a
    busy timeout, so several processes can write to the same file safely.

    Example:
        sink = SQLiteSink("C:/lab/telemetry.db")
        chiller = Chiller("Chiller_A", port="COM4", sink=sink)
    """

    def __init__(self, db_path: Union[str, Path], busy_timeout: float = 5.0):
        """
        Args:
            db_path: Path to the SQLite database file (created if missing).
            busy_timeout: Seconds to wait on a locked database before failing.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(f"PRAGMA busy_timeout={int(busy_timeout * 1000)}")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def write(
        self,
        device_id: str,
        channel: str,
        value: float,
        ts: Optional[float] = None,
        sim: int = 0,
    ) -> None:
        """Insert one sample row (commits immediately; WAL keeps this cheap)."""
        if ts is None:
            ts = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO samples (ts, device, channel, value, sim) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, device_id, channel, float(value), int(sim)),
            )
            self._conn.commit()

    def write_event(
        self,
        source: str,
        level: str,
        message: str,
        ts: Optional[float] = None,
    ) -> None:
        """Insert one event row."""
        if ts is None:
            ts = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (ts, source, level, message) "
                "VALUES (?, ?, ?, ?)",
                (ts, source, level, message),
            )
            self._conn.commit()

    def write_command(
        self,
        device_id: str,
        action: str,
        value: Optional[float] = None,
        ok: int = 1,
        source: str = "",
        ts: Optional[float] = None,
        sim: int = 0,
    ) -> None:
        """Insert one command-audit row (an operation issued via a ctrl API).

        Deliberately NOT part of the ``TelemetrySink`` protocol — devices
        never call this; only the process serving the ctrl API does, and
        wrapper sinks (throttles) must keep satisfying the protocol as-is.
        """
        if ts is None:
            ts = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO commands (ts, device, action, value, ok, source, sim) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, device_id, action,
                 None if value is None else float(value),
                 int(ok), source, int(sim)),
            )
            self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteSink":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
