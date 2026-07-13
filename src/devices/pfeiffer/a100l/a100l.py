"""
A100L device controller.

This module provides the A100L class for Pfeiffer A 100 L / A 200 L
multi-stage Roots pumps via their RS-232/RS-485 ASCII protocol
(``raw/Manuals/Pfeiffer_A100L_Manual.pdf`` ch. 13.3-13.6). The A 100 L
and A 200 L run identical firmware — one class drives both (``A200L``
is an alias).

Unlike the other Pfeiffer devices this family does NOT speak the
telegram frame protocol, so the class sits directly on
``SerialDeviceBase``. Frames are ``#<adr><ORDER><CR>`` (adr = 3-digit
pump address, default 000); replies are ``#<adr>OK<CR>``,
``#<adr>ERRx<CR>`` or, for STA, a 32-byte bit-field payload.

STA reply as observed on the real pump 2026-07-13 (notebook 030):
RS-485 layout WITHOUT separator characters —
``A B 000 000 E 0000 0000 000 0000 00 abcdef`` — where the status
bytes A/B/E/a-f are raw bit fields with bit 7 always set
(``\\x80`` = all clear). The motor-temperature warning bit sits at
bit 4 or 5 of byte ``e`` (manual table ambiguous, mask covers both);
flag behaviour verified against a real temperature warning.
"""
from typing import Any, Dict, Optional
import logging
import threading

from ...serial_device import SerialDeviceBase


class A100L(SerialDeviceBase):
    """
    Pfeiffer A 100 L / A 200 L multi-stage Roots pump device class.

    Provides pump start/stop (SYSON/SYSOFF) and the decoded STA status
    (run state, control mode, motor-temperature warning/alarm and the
    summary warning/alarm flags).

    Example:
        pump = A100L("A100", port="COM36")
        pump.connect()
        pump.start_pump()
        status = pump.get_pump_status()   # {"running": True, ...}
        pump.stop_pump()
        pump.disconnect()
    """

    FAMILY = "Pfeiffer"

    #: STA payload length between '#adr' and <CR>.
    _STA_PAYLOAD_LEN = 32
    #: Motor-temperature bit in the STA warning/alarm bytes (bit 4 or 5 —
    #: the manual's bit table is ambiguous; the mask covers both and the
    #: warning flag is verified against a real temperature warning).
    _TEMP_MASK = 0x30

    def __init__(
        self,
        device_id: str,
        port: str,
        device_address: int = 0,
        baudrate: int = 9600,
        timeout: float = 2.0,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 30.0,
        **kwargs,
    ):
        """
        Initialize A 100 L / A 200 L pump (see ``SerialDeviceBase`` for the
        shared parameters ``sink`` and ``test_mode``).

        Args:
            device_id: Unique identifier for the device (e.g. "A100", "A200").
            port: Serial port (e.g. 'COM36' on Windows).
            device_address: Pump address on the serial link (0-255,
                factory default 0 → frame address "000").
            baudrate: Communication speed (default: 9600, 8N1 fixed).
            timeout: Serial communication timeout in seconds (default: 2.0).
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 30.0)
            **kwargs: Shared SerialDeviceBase parameters.
        """
        self.device_address = int(device_address)
        super().__init__(
            device_id=device_id,
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            logger=logger,
            hk_thread=hk_thread,
            thread_lock=thread_lock,
            hk_interval=hk_interval,
            **kwargs,
        )
        # Simulated pump state so test mode behaves consistently across calls.
        self._sim_state = {"running": False, "temp_warning": False,
                           "temp_alarm": False}

    # =========================================================================
    #     Protocol
    # =========================================================================

    def _command(self, order: str) -> bytes:
        """
        Send one ``#<adr><ORDER><CR>`` frame and return the raw reply.

        Args:
            order: Order string incl. any parameters (e.g. "SYSON", "STA").

        Returns:
            bytes: Raw reply up to and including <CR>.

        Raises:
            RuntimeError: If called in test mode — simulation happens at the
                method level, never at the protocol level.
            Exception: If not connected, the reply times out, or the pump
                answers ERR0-ERR4.
        """
        if self.test_mode:
            raise RuntimeError(
                "_command() called in test_mode — simulate in the calling "
                "method instead"
            )
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        msg = f"#{self.device_address:03d}{order}\r".encode("ascii")
        try:
            with self.thread_lock:  # Thread-safe communication
                self.serial_connection.reset_input_buffer()
                self.serial_connection.write(msg)
                resp = self.serial_connection.read_until(b"\r")
        except Exception as e:
            self.log_event("error", f"{order} failed: {e}")
            raise
        if not resp:
            raise Exception(f"no reply to {order} (timeout)")
        if b"ERR" in resp:
            raise Exception(f"{order} rejected by pump: {resp!r}")
        return resp

    @classmethod
    def _parse_sta(cls, resp: bytes) -> Dict[str, Any]:
        """
        Decode an STA reply (RS-485 layout, no separator characters).

        Payload byte map (after '#adr'):
        ``A B 000 000 E 0000 0000 000 0000 00 abcdef`` — A = status bits 1
        (bit 6 = running), E = status bits 3 (bits 2-0 = control mode),
        a/c/e = warning bytes, b/d/f = alarm bytes; bit 7 is always set.
        """
        body = resp.split(b"#", 1)[-1][3:].rstrip(b"\r")
        if len(body) != cls._STA_PAYLOAD_LEN:
            raise ValueError(
                f"unexpected STA payload length {len(body)}: {resp!r}"
            )
        A, E = body[0], body[8]
        a, b, c, d, e, f = body[26:32]
        return {
            "running": bool(A & 0x40),
            "mode": "remote" if (E & 0x07) == 1 else "local",
            "temp_warning": bool(e & cls._TEMP_MASK),
            "temp_alarm": bool(f & cls._TEMP_MASK),
            "variator_alarm": bool(d & 0x01),
            "any_warning": bool((a | c | e) & 0x7F),
            "any_alarm": bool((b | d | f) & 0x7F),
        }

    # =========================================================================
    #     Control Commands
    # =========================================================================

    def start_pump(self) -> None:
        """Start the pump (SYSON)."""
        if self.test_mode:
            self._sim_state["running"] = True
            self.log_event("info", "pump started (simulated)")
            return
        resp = self._command("SYSON")
        if b"OK" not in resp:
            raise Exception(f"SYSON not acknowledged: {resp!r}")
        self.log_event("info", "pump started (SYSON acknowledged)")

    def stop_pump(self) -> None:
        """Stop the pump (SYSOFF)."""
        if self.test_mode:
            self._sim_state["running"] = False
            self.log_event("info", "pump stopped (simulated)")
            return
        resp = self._command("SYSOFF")
        if b"OK" not in resp:
            raise Exception(f"SYSOFF not acknowledged: {resp!r}")
        self.log_event("info", "pump stopped (SYSOFF acknowledged)")

    # =========================================================================
    #     Status Requests
    # =========================================================================

    def get_pump_status(self) -> Dict[str, Any]:
        """
        Query and decode the pump status (STA).

        Returns:
            dict: ``running`` (bool), ``mode`` ("local"/"remote"),
            ``temp_warning``/``temp_alarm`` (motor temperature),
            ``variator_alarm``, and the summary flags
            ``any_warning``/``any_alarm``.
        """
        if self.test_mode:
            s = self._sim_state
            return {
                "running": s["running"],
                "mode": "remote",
                "temp_warning": s["temp_warning"],
                "temp_alarm": s["temp_alarm"],
                "variator_alarm": False,
                "any_warning": s["temp_warning"],
                "any_alarm": s["temp_alarm"],
            }
        return self._parse_sta(self._command("STA"))

    def is_running(self) -> bool:
        """Check if the pump is running (STA)."""
        return self.get_pump_status()["running"]

    def is_temp_ok(self) -> bool:
        """Check that neither motor-temperature warning nor alarm is set."""
        status = self.get_pump_status()
        return not (status["temp_warning"] or status["temp_alarm"])

    def extra_status(self) -> Dict[str, Any]:
        """A100L-specific status entries."""
        return {"device_address": self.device_address}

    # =========================================================================
    #     Housekeeping Override
    # =========================================================================

    def hk_monitor(self):
        """One housekeeping cycle: run state + warning/alarm flags (STA)."""
        try:
            status = self.get_pump_status()
            self.log_sample("Pump_Running", status["running"])
            self.log_sample("Temp_Warning", status["temp_warning"])
            self.log_sample("Temp_Alarm", status["temp_alarm"])
            self.log_sample("Any_Warning", status["any_warning"])
            self.log_sample("Any_Alarm", status["any_alarm"])
        except Exception as e:
            self.log_event("error", f"housekeeping read failed: {e}")


#: The A 200 L runs the same firmware and protocol — alias so call sites
#: instantiating the second pump read naturally.
A200L = A100L
