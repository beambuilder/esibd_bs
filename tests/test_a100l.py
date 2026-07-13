"""
A100L/A200L (Pfeiffer multi-stage Roots pumps): STA decode against the
real-capture byte layout, the simulator round trip, and the
temperature auto-stop guard (SYSOFF on temp warning/alarm while
running, once per episode).
"""

import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devices.pfeiffer.a100l import A100L, A200L


def sta_reply(running=True, warn=False, alarm=False, remote=True):
    """Build an STA reply in the RS-485 no-separator layout observed on
    the real pump 2026-07-13 (notebook 030): 32-byte payload
    ``A B 000 000 E 0000 0000 000 0000 00 abcdef``, status bytes with
    bit 7 always set."""
    A = 0x80 | (0x40 if running else 0)
    E = 0x80 | (0x01 if remote else 0x02)
    e = 0x80 | (0x10 if warn else 0)       # motor-temp warning (mask 0x30)
    f = 0x80 | (0x20 if alarm else 0)      # motor-temp alarm
    body = (bytes([A, 0x80]) + b"000" + b"000" + bytes([E])
            + b"0000" + b"0000" + b"000" + b"0000" + b"00"
            + bytes([0x80, 0x80, 0x80, 0x80, e, f]))
    assert len(body) == 32
    return b"#000" + body + b"\r"


class TestStaParse:
    def test_all_clear_running(self):
        s = A100L._parse_sta(sta_reply(running=True))
        assert s == {"running": True, "mode": "remote",
                     "temp_warning": False, "temp_alarm": False,
                     "variator_alarm": False,
                     "any_warning": False, "any_alarm": False}

    def test_stopped_local(self):
        s = A100L._parse_sta(sta_reply(running=False, remote=False))
        assert s["running"] is False
        assert s["mode"] == "local"

    def test_temp_warning_sets_summary(self):
        # mirrors the deliberately provoked real warning (2026-07-13)
        s = A100L._parse_sta(sta_reply(warn=True))
        assert s["temp_warning"] is True
        assert s["any_warning"] is True
        assert s["temp_alarm"] is False and s["any_alarm"] is False

    def test_temp_alarm(self):
        s = A100L._parse_sta(sta_reply(alarm=True))
        assert s["temp_alarm"] is True and s["any_alarm"] is True

    def test_wrong_length_raises(self):
        with pytest.raises(ValueError, match="STA payload length"):
            A100L._parse_sta(b"#000" + b"\x80" * 31 + b"\r")


class TestSim:
    def test_alias_is_same_class(self):
        assert A200L is A100L

    def test_sim_round_trip(self):
        pump = A100L("A100", port="COM98", test_mode=True)
        assert pump.connect() is True
        assert pump.is_running() is False
        pump.start_pump()
        assert pump.is_running() is True
        assert pump.is_temp_ok() is True
        pump.stop_pump()
        assert pump.is_running() is False
        pump.disconnect()


class TestTempAutoStop:
    def _hot_running_pump(self, **kw):
        pump = A100L("A100", port="COM98", test_mode=True, **kw)
        pump.connect()
        pump.start_pump()
        pump._sim_state["temp_warning"] = True
        return pump

    def test_warning_stops_running_pump(self):
        pump = self._hot_running_pump()
        pump.hk_monitor()
        assert pump.is_running() is False

    def test_alarm_stops_too(self):
        pump = self._hot_running_pump()
        pump._sim_state["temp_warning"] = False
        pump._sim_state["temp_alarm"] = True
        pump.hk_monitor()
        assert pump.is_running() is False

    def test_one_shot_per_episode_then_rearm(self):
        pump = self._hot_running_pump()
        pump.hk_monitor()
        assert pump.is_running() is False
        # user restarts while the warning persists: no second auto-stop
        pump.start_pump()
        pump.hk_monitor()
        assert pump.is_running() is True
        # warning clears -> guard re-arms -> next episode stops again
        pump._sim_state["temp_warning"] = False
        pump.hk_monitor()
        pump._sim_state["temp_warning"] = True
        pump.hk_monitor()
        assert pump.is_running() is False

    def test_disabled_guard_never_stops(self):
        pump = self._hot_running_pump(temp_auto_stop=False)
        pump.hk_monitor()
        assert pump.is_running() is True

    def test_idle_pump_not_started_or_touched(self):
        pump = A100L("A100", port="COM98", test_mode=True)
        pump.connect()
        pump._sim_state["temp_warning"] = True
        pump.hk_monitor()
        assert pump.is_running() is False
        # guard stays armed for a later running-hot episode
        assert pump._temp_stop_armed is True
