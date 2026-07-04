"""
Housekeeping poke (SerialDeviceBase, 2026-07-04).

The dashboard's control latency was dominated by hk_interval (10-15 s in
the lab config): a start/stop command executed instantly, but its result
only reached telemetry with the next scheduled housekeeping cycle. The
service ctrl API now calls ``poke_housekeeping()`` after every successful
command; these tests cover the primitive:

- a poke wakes the internal worker for an immediate extra cycle, long
  before hk_interval elapses,
- a poke while housekeeping is off is a no-op (no stray wake on restart),
- ``stop_housekeeping()`` no longer waits out the interval: the worker
  exits promptly (the stop path pokes the wait too).
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devices import Chiller, SQLiteSink


LONG_INTERVAL = 30.0  # no natural cycle within any test's runtime


@pytest.fixture
def sink(tmp_path):
    with SQLiteSink(tmp_path / "telemetry.db") as s:
        yield s


@pytest.fixture
def device(sink):
    dev = Chiller("Chiller_T", port="COM90", sink=sink, test_mode=True,
                  hk_interval=LONG_INTERVAL)
    yield dev
    dev.stop_housekeeping()


def _wait_for(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_poke_triggers_immediate_cycle(device):
    device.connect()
    device.start_housekeeping()
    assert _wait_for(lambda: device.last_sample_ts is not None)

    time.sleep(0.1)  # let the worker settle into its inter-cycle wait
    ts_before = device.last_sample_ts
    device.poke_housekeeping()
    # The next cycle would naturally be LONG_INTERVAL away — the poke must
    # produce one within the 2 s wait budget.
    assert _wait_for(lambda: device.last_sample_ts > ts_before)


def test_poke_without_hk_is_a_noop(device):
    device.connect()
    device.poke_housekeeping()
    assert not device.hk_poke_event.is_set()
    # A stale poke must not survive into the next hk start either.
    device.hk_poke_event.set()
    device.start_housekeeping()
    assert _wait_for(lambda: device.last_sample_ts is not None)


def test_stop_does_not_wait_out_the_interval(device):
    device.connect()
    device.start_housekeeping()
    assert _wait_for(lambda: device.last_sample_ts is not None)

    t0 = time.time()
    assert device.stop_housekeeping()
    assert time.time() - t0 < 2.0
    assert _wait_for(lambda: not device.hk_thread.is_alive())
