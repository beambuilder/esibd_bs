"""
Unit tests for the DT-670 depo-stage temperature Arduino (Ethernet/HTTP).

All HTTP traffic is mocked (urllib) — no hardware, no network.
"""

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from devices.arduino.dt670_arduino import DT670Arduino, STALE_AGE_MS


def _http_reply(payload: dict) -> MagicMock:
    """A context-manager mock mimicking urllib.request.urlopen()."""
    reply = MagicMock()
    reply.read.return_value = json.dumps(payload).encode("utf-8")
    cm = MagicMock()
    cm.__enter__.return_value = reply
    cm.__exit__.return_value = False
    return cm


OK_PAYLOAD = {"v": 0.55963, "t_k": 298.00, "t_c": 24.85,
              "flag": "ok", "age_ms": 31}


class RecordingSink:
    """Minimal TelemetrySink capturing writes for assertions."""

    def __init__(self):
        self.samples = []
        self.events = []

    def write(self, device, channel, value, sim=0):
        self.samples.append((device, channel, value, sim))

    def write_event(self, device, level, message):
        self.events.append((device, level, message))


class TestDT670Arduino:

    def test_initialization(self):
        dt = DT670Arduino("DT670_Depo")
        assert dt.host == "192.168.2.2"
        assert dt.url == "http://192.168.2.2/"
        assert dt.port == "192.168.2.2"      # aligned log column
        assert dt.http_timeout == 1.0
        assert dt.hk_interval == 2.0
        assert dt.is_connected is False

        custom = DT670Arduino("custom", host="10.0.0.5",
                              http_timeout=0.5, hk_interval=5.0)
        assert custom.url == "http://10.0.0.5/"
        assert custom.http_timeout == 0.5
        assert custom.hk_interval == 5.0

    @patch("devices.arduino.dt670_arduino.urllib.request.urlopen")
    def test_connect_success(self, mock_urlopen):
        mock_urlopen.return_value = _http_reply(OK_PAYLOAD)
        dt = DT670Arduino("connect_test")

        assert dt.connect() is True
        assert dt.is_connected is True
        args, kwargs = mock_urlopen.call_args
        assert args[0] == "http://192.168.2.2/"
        assert kwargs["timeout"] == 1.0

    @patch("devices.arduino.dt670_arduino.urllib.request.urlopen")
    def test_connect_failure_never_simulates(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("unreachable")
        sink = RecordingSink()
        dt = DT670Arduino("connect_fail", sink=sink)

        assert dt.connect() is False
        assert dt.is_connected is False
        # Loud error, no samples — never auto-sim.
        assert sink.samples == []
        assert any(lvl == "ERROR" for _, lvl, _ in sink.events)

    @patch("devices.arduino.dt670_arduino.urllib.request.urlopen")
    def test_hk_ok_logs_both_channels(self, mock_urlopen):
        mock_urlopen.return_value = _http_reply(OK_PAYLOAD)
        sink = RecordingSink()
        dt = DT670Arduino("hk_ok", sink=sink)
        dt.is_connected = True

        dt.hk_monitor()

        channels = {c: v for _, c, v, _ in sink.samples}
        assert channels["Temp_K"] == 298.00
        assert abs(channels["Volt"] - 0.55963) < 1e-9

    @patch("devices.arduino.dt670_arduino.urllib.request.urlopen")
    def test_hk_fault_flags(self, mock_urlopen):
        """open / reversed / out_of_range: Volt logged, no Temp_K, error event."""
        for flag, volts in (("open", 1.6), ("reversed", -0.2),
                            ("out_of_range", 0.1)):
            mock_urlopen.return_value = _http_reply(
                {"v": volts, "t_k": None, "t_c": None,
                 "flag": flag, "age_ms": 31})
            sink = RecordingSink()
            dt = DT670Arduino(f"fault_{flag}", sink=sink)
            dt.is_connected = True

            dt.hk_monitor()

            channels = [c for _, c, _, _ in sink.samples]
            assert channels == ["Volt"], flag
            assert any(flag in msg for _, lvl, msg in sink.events
                       if lvl == "ERROR"), flag

    @patch("devices.arduino.dt670_arduino.urllib.request.urlopen")
    def test_hk_stale_age_skipped(self, mock_urlopen):
        mock_urlopen.return_value = _http_reply(
            {**OK_PAYLOAD, "age_ms": STALE_AGE_MS + 500})
        sink = RecordingSink()
        dt = DT670Arduino("stale_test", sink=sink)
        dt.is_connected = True

        dt.hk_monitor()

        assert sink.samples == []
        assert any("stale" in msg for _, lvl, msg in sink.events
                   if lvl == "WARNING")

    @patch("devices.arduino.dt670_arduino.urllib.request.urlopen")
    def test_hk_timeout_no_samples(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("timed out")
        sink = RecordingSink()
        dt = DT670Arduino("timeout_test", sink=sink)
        dt.is_connected = True

        dt.hk_monitor()

        assert sink.samples == []
        assert any("HTTP read failed" in msg for _, lvl, msg in sink.events
                   if lvl == "ERROR")

    @patch("devices.arduino.dt670_arduino.urllib.request.urlopen")
    def test_hk_malformed_json(self, mock_urlopen):
        reply = MagicMock()
        reply.read.return_value = b"not json at all"
        cm = MagicMock()
        cm.__enter__.return_value = reply
        cm.__exit__.return_value = False
        mock_urlopen.return_value = cm
        sink = RecordingSink()
        dt = DT670Arduino("badjson_test", sink=sink)
        dt.is_connected = True

        dt.hk_monitor()

        assert sink.samples == []
        assert any(lvl == "ERROR" for _, lvl, _ in sink.events)

    def test_sim_mode(self):
        """Test mode: no network, plausible values, sim=1 in the sink."""
        sink = RecordingSink()
        dt = DT670Arduino("sim_test", sink=sink, test_mode=True)

        assert dt.connect() is True

        with patch("devices.arduino.dt670_arduino.urllib.request.urlopen") as m:
            dt.hk_monitor()
            m.assert_not_called()

        channels = {c: (v, s) for _, c, v, s in sink.samples}
        t_k, sim_flag = channels["Temp_K"]
        assert 295.0 <= t_k <= 300.0
        assert sim_flag == 1
        v, _ = channels["Volt"]
        assert 0.5 <= v <= 0.6

    def test_read_dt670_sim_shape(self):
        dt = DT670Arduino("sim_shape", test_mode=True)
        data = dt.read_dt670()
        assert set(data) == {"v", "t_k", "t_c", "flag", "age_ms"}
        assert data["flag"] == "ok"
        assert abs(data["t_k"] - 273.15 - data["t_c"]) < 0.05
