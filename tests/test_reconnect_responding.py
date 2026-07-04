"""
Responding indicator + reconnect (SerialDeviceBase, 2026-07-04).

``connected`` only ever meant "COM port opened once" — a powered-off or
mute device keeps showing connected=1 while every read fails (gotcha from
the 2026-07-03 commissioning). These tests cover the fix:

- ``responding_state()`` / ``get_status()["responding"]``: None while
  nothing polls the device (not connected or hk off), True while samples
  arrive, False when housekeeping polls into silence.
- ``reconnect()``: close + reopen in place, resuming housekeeping only if
  it was running before.
- ``connect()`` idempotence: a second connect must not reopen the port.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devices import Chiller, SQLiteSink
from devices.pfeiffer.hiscroll12 import HiScroll12


@pytest.fixture
def sink(tmp_path):
    with SQLiteSink(tmp_path / "telemetry.db") as s:
        yield s


@pytest.fixture
def device(sink):
    dev = Chiller("Chiller_T", port="COM90", sink=sink, test_mode=True,
                  hk_interval=0.05)
    yield dev
    dev.stop_housekeeping()


def _wait_for(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class TestRespondingState:
    def test_unknown_before_connect_and_without_hk(self, device):
        assert device.responding_state() is None
        assert device.connect()
        # Connected but nothing polls it: silence proves nothing.
        assert device.responding_state() is None
        status = device.get_status()
        assert status["responding"] is None
        assert status["last_sample_age_s"] is None

    def test_true_while_samples_arrive(self, device):
        device.connect()
        device.start_housekeeping()
        assert _wait_for(lambda: device.last_sample_ts is not None)
        assert device.responding_state() is True
        status = device.get_status()
        assert status["responding"] is True
        assert status["last_sample_age_s"] is not None

    def test_false_when_polling_into_silence(self, device):
        device.connect()
        device.start_housekeeping()
        assert _wait_for(lambda: device.last_sample_ts is not None)
        # Simulate a device that went mute: the last sample ages beyond
        # the max(2.5 * hk_interval, 15 s) window.
        device.last_sample_ts = time.time() - 1000.0
        assert device.responding_state() is False
        # A fresh hk start on a mute device: no sample yet -> False, not None.
        device.last_sample_ts = None
        assert device.responding_state() is False

    def test_unknown_again_after_hk_stop(self, device):
        device.connect()
        device.start_housekeeping()
        assert _wait_for(lambda: device.last_sample_ts is not None)
        device.stop_housekeeping()
        assert device.responding_state() is None


class TestReconnect:
    def test_reconnect_resumes_housekeeping(self, device):
        device.connect()
        device.start_housekeeping()
        assert _wait_for(lambda: device.last_sample_ts is not None)
        assert device.reconnect() is True
        assert device.is_connected
        assert device.hk_running  # was running before -> resumed
        assert _wait_for(lambda: device.last_sample_ts is not None)

    def test_reconnect_leaves_housekeeping_off(self, device):
        device.connect()
        assert device.reconnect() is True
        assert device.is_connected
        assert not device.hk_running  # was off before -> stays off

    def test_reconnect_resets_last_sample(self, device):
        device.connect()
        device.start_housekeeping()
        assert _wait_for(lambda: device.last_sample_ts is not None)
        device.stop_housekeeping()
        device.reconnect()
        # hk was off at reconnect time: the stamp must not survive the
        # transport swap (a stale stamp would fake "responding" later).
        assert device.responding_state() is None
        assert device.get_status()["last_sample_age_s"] is None

    def test_connect_is_idempotent(self, sink):
        dev = HiScroll12("HiScroll_T", port="COM94", sink=sink, test_mode=True)
        assert dev.connect()
        assert dev.connect()  # second call: no second open, still True
        assert dev.is_connected
