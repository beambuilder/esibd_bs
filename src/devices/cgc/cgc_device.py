"""
Shared lab layer for all CGC vendor-DLL device families (P6, ADR-0005).

``CGCDevice`` is the vendor-DLL counterpart of ``SerialDeviceBase``: it
plugs the pure ctypes wrapper bases (``AMPRBase``, ``PABase``, ...) into
the transport-agnostic ``DeviceBase`` (canonical aligned log line,
telemetry sink, housekeeping worker + poke, responding_state/reconnect,
explicit test mode). The wrapper bases stay publishable stand-alone —
everything lab-specific lives here.

Pattern per family (cooperative multiple inheritance, DeviceBase does not
call ``super().__init__``)::

    class AMPR(CGCDevice, AMPRBase):
        FAMILY = "AMPR"
        DLL_BASE = AMPRBase

        def __init__(self, device_id, com, baudrate=230400, logger=None,
                     *, test_mode=False, **kwargs):
            CGCDevice.__init__(self, device_id, com, baudrate,
                               logger=logger, test_mode=test_mode, **kwargs)
            if not test_mode:
                AMPRBase.__init__(self, com=com, log=None, idn=device_id)

Contract notes:

- The constructor stays positionally compatible with the pre-P6 classes
  (``device_id, com, baudrate``); everything after ``logger`` is
  keyword-only. ``port`` is derived as ``f"COM{com}"`` so the canonical
  log columns align with the serial families.
- ``test_mode=True`` skips the DLL-base ``__init__`` entirely — no
  ``ctypes.WinDLL`` load, no hardware. Only the curated high-level
  methods of each family are simulated; **raw DLL exports are
  real-hardware-only** and raise ``AttributeError`` in test mode.
- ``_check(status, what)`` converts a nonzero DLL status code into a
  ``CGCStatusError`` carrying the vendor error text.
- ``trace_dll_calls()`` replaces the old (dead) ``__getattr__`` logging
  fallbacks: opt-in, instance-level shadowing of every public DLL-wrapper
  method that still resolves to the ``DLL_BASE`` implementation. Curated
  lab-layer overrides keep their own logging and are never shadowed.
"""
from typing import Any, Dict

from ..device_base import DeviceBase


class CGCStatusError(RuntimeError):
    """A CGC DLL call returned a nonzero status code."""

    def __init__(self, status: int, what: str, message: str):
        self.status = status
        self.what = what
        super().__init__(f"{what} failed: {message} (status {status})")


class CGCDevice(DeviceBase):
    """
    Base class for CGC DLL-driven lab devices with housekeeping, canonical
    logging, telemetry and explicit test mode.

    Family subclasses set ``FAMILY`` and ``DLL_BASE``, implement
    ``_open_transport()`` (the full documented bring-up sequence, so the
    inherited ``reconnect()`` re-runs it) and ``hk_monitor()`` (one
    housekeeping cycle reporting every channel via ``log_sample()``).
    """

    FAMILY = "CGC"
    #: The pure ctypes wrapper base of the family (set by subclasses);
    #: used by trace_dll_calls() to find the raw DLL exports.
    DLL_BASE = None

    def __init__(
        self,
        device_id: str,
        com: int,
        baudrate: int = 230400,
        logger=None,
        *,
        sink=None,
        test_mode: bool = False,
        hk_thread=None,
        thread_lock=None,
        hk_interval: float = 5.0,
        **kwargs,
    ):
        """
        Initialize a CGC device.

        Args:
            device_id: Unique identifier for the device (appears in every log line).
            com: COM port number as the vendor DLLs expect it (int, e.g. 6);
                the canonical ``port`` column shows "COM6".
            baudrate: Communication baud rate (CGC default 230400).
            logger: Optional external logger. If None, creates a timestamped
                file logger in debugging/logs/.
            sink: Optional telemetry sink; one sample per channel per
                housekeeping cycle is written to it.
            test_mode: If True, the vendor DLL is never loaded and the
                curated high-level methods produce simulated values on the
                same channels with the same log format ([SIM] marker,
                sim=1 in the sink). Never enabled automatically.
            hk_thread: Optional external housekeeping thread.
            thread_lock: Optional external lock for DLL communication.
            hk_interval: Housekeeping interval in seconds (CGC default 5).
            **kwargs: Ignored; accepted for forward compatibility.
        """
        self.com = com
        super().__init__(
            device_id,
            f"COM{com}",
            baudrate=baudrate,
            logger=logger,
            sink=sink,
            test_mode=test_mode,
            hk_thread=hk_thread,
            thread_lock=thread_lock,
            hk_interval=hk_interval,
            **kwargs,
        )
        self._traced_names = []

    # =========================================================================
    #     Status-code handling
    # =========================================================================

    def _check(self, status: int, what: str) -> int:
        """
        Raise ``CGCStatusError`` (with the vendor error text) if a DLL call
        returned a nonzero status; pass the status through otherwise.
        """
        if status != 0:
            message = getattr(self, "err_dict", {}).get(
                str(status), "unknown error code"
            )
            raise CGCStatusError(status, what, message)
        return status

    # =========================================================================
    #     Transport hooks (vendor DLL)
    # =========================================================================

    def _close_transport(self) -> None:
        """Best-effort DLL port close; a nonzero status is logged, not raised."""
        status = self.close_port()
        if status != 0:
            self.log_event("warning", f"close_port returned {status}")

    def _transport_desc(self) -> str:
        return f"vendor DLL, {self.baudrate} baud"

    # =========================================================================
    #     Status
    # =========================================================================

    def extra_status(self) -> Dict[str, Any]:
        """Add the CGC-specific keys the pre-P6 ``get_status()`` carried."""
        return {"com": self.com, "external_lock": self.external_lock}

    # =========================================================================
    #     Opt-in DLL call tracer (replaces the dead __getattr__ fallbacks)
    # =========================================================================

    def trace_dll_calls(self, enable: bool = True) -> None:
        """
        Shadow every public DLL-wrapper method inherited unchanged from
        ``DLL_BASE`` with a logging wrapper: full args in, raw result out,
        no status interpretation. Off by default; ``enable=False`` removes
        the shadows again. Uses plain logger lines (not the sink's events
        table) so a traced housekeeping loop cannot flood telemetry.
        """
        for name in self._traced_names:
            self.__dict__.pop(name, None)
        self._traced_names = []
        if not enable:
            return
        if self.DLL_BASE is None:
            raise TypeError(f"{type(self).__name__} has no DLL_BASE set")
        for name in dir(self.DLL_BASE):
            if name.startswith("_"):
                continue
            func = getattr(self.DLL_BASE, name, None)
            if not callable(func):
                continue
            # Only shadow methods that still resolve to the DLL-base
            # implementation — curated overrides keep their own logging.
            if getattr(type(self), name, None) is not func:
                continue
            self.__dict__[name] = self._make_traced(name, func)
            self._traced_names.append(name)
        self.logger.info(
            f"{self._prefix()}DLL call tracing ON "
            f"({len(self._traced_names)} methods)"
        )

    def _make_traced(self, name, func):
        def traced(*args, **kwargs):
            self.logger.info(
                f"{self._prefix()}TRACE {name} args={args} kwargs={kwargs}"
            )
            try:
                result = func(self, *args, **kwargs)
            except Exception as e:
                self.logger.error(f"{self._prefix()}TRACE {name} raised: {e}")
                raise
            self.logger.info(f"{self._prefix()}TRACE {name} -> {result}")
            return result

        traced.__doc__ = func.__doc__
        return traced
