"""
HiPace300Bus opt-in tolerant telegram exchange (2026-10-23).

The HiPace_QMS TC400 replies checksum-valid frames whose terminating CR
arrives as 0xC3 (notebook 035). With tolerant_comm=True such frames are
accepted and lost exchanges are retried; the default keeps the stock
protocol path, which rejects them.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devices.pfeiffer.hipacebus import HiPace300Bus


def frame(addr: int, param: int, data: str) -> bytes:
    """Device reply frame WITHOUT the terminating CR."""
    body = f"{addr:03d}10{param:03d}{len(data):02d}{data}"
    return (body + f"{sum(map(ord, body)) % 256:03d}").encode()


CLEAN = frame(1, 349, "TC 400") + b"\r"
CORRUPT_CR = frame(1, 349, "TC 400") + b"\xc3"  # captured on the QMS line


class FakeSerial:
    """Scripted serial port: each write() queues the next scripted reply."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.writes = []
        self._rx = b""

    def write(self, data):
        self.writes.append(data)
        self._rx = self.replies.pop(0) if self.replies else b""
        return len(data)

    def read(self, n=1):
        out, self._rx = self._rx[:n], self._rx[n:]
        return out

    def reset_input_buffer(self):
        self._rx = b""


def make_pump(replies, **kwargs):
    pump = HiPace300Bus("HiPace_QMS", port="COM99", device_address=101,
                        tc400_address=1, comm_retry_delay=0.0, **kwargs)
    pump.serial_connection = FakeSerial(replies)
    pump.is_connected = True
    return pump


def test_default_is_off():
    assert HiPace300Bus("HiPace_QMS", port="COM99").tolerant_comm is False


def test_stock_path_rejects_corrupted_cr():
    pump = make_pump([CORRUPT_CR])
    with pytest.raises(Exception):
        pump._query_channel_parameter("tc400", 349)
    assert len(pump.serial_connection.writes) == 1  # no retry


def test_tolerant_accepts_corrupted_cr():
    pump = make_pump([CORRUPT_CR], tolerant_comm=True)
    assert pump._query_channel_parameter("tc400", 349) == "TC 400"
    assert len(pump.serial_connection.writes) == 1


def test_tolerant_retries_lost_reply():
    pump = make_pump([b"", CLEAN], tolerant_comm=True)
    assert pump._query_channel_parameter("tc400", 349) == "TC 400"
    assert len(pump.serial_connection.writes) == 2


def test_tolerant_gives_up_after_attempts():
    pump = make_pump([b""] * 5, tolerant_comm=True, comm_attempts=3)
    with pytest.raises(ValueError, match="after 3 attempts"):
        pump._query_channel_parameter("tc400", 349)
    assert len(pump.serial_connection.writes) == 3


def test_tolerant_write_checks_ack():
    ack = frame(1, 10, "111111") + b"\xc3"
    pump = make_pump([ack], tolerant_comm=True)
    pump._set_channel_parameter("tc400", 10, "111111")
    assert pump.serial_connection.writes[0].startswith(b"0011001006111111")
