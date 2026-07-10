"""
Pfeiffer error acknowledgment + error history (user 2026-07-10).

ErrorAckn [P:009]: a drive that tripped into an error state refuses a new
start until acknowledged — every pump family exposes acknowledge_error()
and it must be sim-safe (the dashboard button reaches it via the ctrl API
in LAB_SIM smoke stacks too).

ErrHist1-3 [P:360-362]: string parameters (type 4), so they bypass the
numeric telemetry sink — hk_monitor() caches them on the device and
get_status() serves them as "error_history" for the dashboard card.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devices.pfeiffer.hipacebus import HiPace80Bus, HiPace80DCU, HiPace300Bus
from devices.pfeiffer.hiscroll12 import HiScroll12

MAKERS = [
    lambda: HiScroll12("HiScroll_1", port="COM94", test_mode=True),
    lambda: HiPace300Bus("HiPace_Transfer", port="COM95", test_mode=True),
    lambda: HiPace80Bus("HiPace_LL_PhotonSTM", port="COM96", test_mode=True),
    lambda: HiPace80DCU("HiPace_LL_MPI", port="COM97", test_mode=True),
]

IDS = ["hiscroll12", "hipace300bus", "hipace80bus", "hipace80dcu"]


@pytest.fixture(params=MAKERS, ids=IDS)
def pump(request):
    dev = request.param()
    yield dev
    dev.disconnect()


class TestAcknowledgeError:
    def test_sim_acknowledge_does_not_raise(self, pump):
        pump.connect()
        pump.acknowledge_error()


class TestErrorHistory:
    def test_sim_getter_defaults_blank(self, pump):
        assert [pump.get_error_history(n) for n in (1, 2, 3)] == ["", "", ""]

    def test_slot_out_of_range_raises(self, pump):
        with pytest.raises(ValueError):
            pump.get_error_history(0)
        with pytest.raises(ValueError):
            pump.get_error_history(4)

    def test_hk_caches_and_status_serves(self, pump):
        pump.connect()
        pump._sim_state["err_hist"] = ["Err021", "Wrn007", ""]
        pump.hk_monitor()
        assert pump.get_status()["error_history"] == ["Err021", "Wrn007", ""]

    def test_status_before_first_hk_cycle_is_empty_list(self, pump):
        assert pump.get_status()["error_history"] == []
