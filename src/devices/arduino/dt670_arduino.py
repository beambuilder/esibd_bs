"""
DT-670 depo-stage temperature Arduino (Ethernet/HTTP).

Reads a Lake Shore DT-670 silicon diode on the deposition stage via an
Arduino Uno R3 + W5500 Ethernet Shield 2 + ADS1115 (firmware
``dt670srv.ino``, sibling file). The Arduino measures the diode forward
voltage, converts it to kelvin via the official DT-670 breakpoint table
and serves the latest reading as JSON on ``GET http://<host>/``::

    {"v":0.55963,"t_k":298.00,"t_c":24.85,"flag":"ok","age_ms":31}

``flag``: ``ok`` | ``open`` (broken wire / empty seat) | ``reversed``
(diode polarity swapped) | ``out_of_range`` (outside the 50-440 K curve).
``t_k``/``t_c`` are JSON null unless the flag is ``ok``.

One reading per TCP connection, no request queue on the Uno — poll at
a few Hz max, never concurrently. Transport is stdlib ``urllib`` (no
extra dependency); this class subclasses the transport-agnostic
``DeviceBase`` directly, not ``SerialDeviceBase``.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from ..device_base import DeviceBase

#: A reading whose firmware-side age exceeds this is treated as stale —
#: the Uno's measurement loop is stalled, not a fresh sample.
STALE_AGE_MS = 2000


class DT670Arduino(DeviceBase):
    """
    DT-670 temperature readout over HTTP.

    Channels (housekeeping):
        Temp_K  [K]  — diode temperature (only while flag is "ok")
        Volt    [V]  — diode forward voltage (always logged; it is the
                       diagnostic when the flag reports a fault)

    Example:
        dt670 = DT670Arduino("DT670_Depo", host="192.168.2.2")
        dt670.connect()
        dt670.start_housekeeping(interval=2.0)
    """

    FAMILY = "Arduino"

    def __init__(
        self,
        device_id: str,
        host: str = "192.168.2.2",
        http_timeout: float = 1.0,
        hk_interval: float = 2.0,
        **kwargs,
    ):
        """
        Initialize the DT-670 readout (see ``DeviceBase`` for the shared
        parameters ``logger``, ``sink``, ``test_mode``, ``hk_thread``,
        ``thread_lock``).

        Args:
            device_id: Unique identifier (e.g. "DT670_Depo").
            host: IP or hostname of the Arduino (static, no DHCP).
            http_timeout: Per-request timeout in seconds. Always finite —
                the Uno serves one connection at a time and a wedged
                client blocks the next reading's serve slot.
            hk_interval: Housekeeping poll interval in seconds. The
                firmware is designed and tested at 2 Hz; keep polling
                at a few Hz or slower.
        """
        self.host = host
        self.http_timeout = http_timeout
        self.url = f"http://{host}/"
        # DeviceBase.port is the aligned log column; baudrate is
        # meaningless for HTTP and stays at the ignored default.
        super().__init__(
            device_id=device_id,
            port=host,
            hk_interval=hk_interval,
            **kwargs,
        )

    # =========================================================================
    #     Transport hooks (HTTP is stateless; connect = one probe GET)
    # =========================================================================

    def _open_transport(self) -> None:
        """Probe the endpoint once; any failure raises and connect()
        reports a loud error (never falls back to simulation)."""
        self._fetch()

    def _close_transport(self) -> None:
        """Nothing to close — one TCP connection per request."""

    def _transport_desc(self) -> str:
        return self.url

    # =========================================================================
    #     Readout
    # =========================================================================

    def _fetch(self) -> Dict[str, Any]:
        """One GET + JSON parse. Raises on network/HTTP/parse failure."""
        with self.thread_lock:
            with urllib.request.urlopen(
                self.url, timeout=self.http_timeout
            ) as reply:
                return json.loads(reply.read().decode("utf-8"))

    def read_dt670(self) -> Optional[Dict[str, Any]]:
        """
        Read the latest DT-670 sample.

        In test mode this returns the simulated dict instead of touching
        the network.

        Returns:
            dict with keys *v*, *t_k*, *t_c*, *flag*, *age_ms* — or None
            on network/parse failure (logged).
        """
        if self.test_mode:
            return self._sim_data()
        try:
            return self._fetch()
        except (urllib.error.URLError, OSError, ValueError) as e:
            self.log_event("error", f"HTTP read failed: {e}")
            return None

    # =========================================================================
    #     Simulation
    # =========================================================================

    def _sim_data(self) -> Dict[str, Any]:
        """Plausible room-temperature reading for test mode."""
        t_k = self._sim_uniform(295.0, 300.0)
        # Roughly the DT-670 slope around room temp (-2.3 mV/K).
        v = round(0.559639 - (t_k - 300.0) * -0.0023, 5)
        return {
            "v": v,
            "t_k": t_k,
            "t_c": round(t_k - 273.15, 2),
            "flag": "ok",
            "age_ms": int(self._sim_uniform(10, 80, 0)),
        }

    # =========================================================================
    #     Housekeeping
    # =========================================================================

    def hk_monitor(self) -> None:
        """Read one DT-670 sample and report it."""
        try:
            data = self.read_dt670()
            if data is None:
                return

            age_ms = data.get("age_ms")
            if isinstance(age_ms, (int, float)) and age_ms > STALE_AGE_MS:
                # Measurement loop on the Uno stalled — not a fresh value.
                self.log_event(
                    "warning",
                    f"stale reading (age {age_ms:.0f} ms > {STALE_AGE_MS} ms), skipped",
                )
                return

            flag = data.get("flag")
            volts = data.get("v")
            if isinstance(volts, (int, float)):
                self.log_sample("Volt", volts, "V", fmt=".5f")

            if flag == "ok":
                t_k = data.get("t_k")
                if isinstance(t_k, (int, float)):
                    self.log_sample("Temp_K", t_k, "K", fmt=".2f")
                else:
                    self.log_event("error", "flag ok but t_k missing/non-numeric")
            else:
                # open / reversed / out_of_range: hard sensor fault —
                # loud event + Temp_K plot gap; Volt above is the
                # diagnostic (rail / negative / off-curve voltage).
                self.log_event("error", f"sensor fault: flag={flag!r}")
        except Exception as e:
            self.log_event("error", f"housekeeping read failed: {e}")
