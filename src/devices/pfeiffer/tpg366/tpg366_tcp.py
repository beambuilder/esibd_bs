"""
TPG366 TCP device controller.

This module provides the TPG366TCP class for communicating with Pfeiffer
TPG366 pressure measurement and control units via TCP/IP (Ethernet).
It subclasses the serial ``TPG366`` and only swaps the transport: the
TPG366 Ethernet interface exposes a raw TCP socket that accepts the same
Pfeiffer telegram protocol frames.
"""
from typing import Any, Dict, Optional
import socket

from .tpg366 import TPG366


class _TcpSocketWrapper:
    """
    Wraps a TCP socket to expose the same interface as pyserial
    (write, read, reset_input_buffer, is_open) so that
    pfeifferVacuumProtocol functions work without modification.
    """

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self.is_open = True

    def write(self, data: bytes) -> int:
        return self._sock.send(data)

    def read(self, size: int = 1) -> bytes:
        try:
            return self._sock.recv(size)
        except socket.timeout:
            return b""

    def reset_input_buffer(self):
        """Drain any pending bytes from the receive buffer."""
        self._sock.setblocking(False)
        try:
            while True:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
        except (BlockingIOError, OSError):
            pass
        finally:
            self._sock.setblocking(True)
            self._sock.settimeout(self._timeout)

    @property
    def _timeout(self):
        return self._sock.gettimeout()

    def close(self):
        self.is_open = False
        self._sock.close()


class TPG366TCP(TPG366):
    """
    Pfeiffer TPG366 Pressure Measurement and Control Unit Class (TCP/IP).

    Identical functionality to the serial TPG366 class, but communicates
    over Ethernet instead of RS-485/USB serial.

    Example:
        gauge = TPG366TCP("tpg366_01", host="192.168.1.100", port=8000, device_address=10)
        gauge.connect()
        pressure = gauge.get_pressure(1)
        gauge.disconnect()
    """

    def __init__(
            self,
            device_id: str,
            host: str,
            port: int = 8000,
            device_address: int = 10,
            timeout: float = 2.0,
            hk_interval: float = 30.0,
            **kwargs,
    ):
        """
        Initialize TPG366 TCP device (see ``SerialDeviceBase`` for the shared
        parameters ``logger``, ``sink``, ``test_mode``, ``hk_thread``,
        ``thread_lock``).

        Args:
            device_id: Unique identifier for the device.
            host: IP address or hostname of the TPG366 (e.g., '192.168.1.100').
            port: TCP port number (default: 8000, check TPG366 Ethernet config).
            device_address: Pfeiffer device address (default: 10).
            timeout: Socket timeout in seconds (default: 2.0).
            hk_interval: Housekeeping monitoring interval in seconds.
            **kwargs: Shared SerialDeviceBase parameters.
        """
        self.host = host
        self.tcp_port = port
        # The base's `port` is the display/identity field in every log line.
        super().__init__(
            device_id=device_id,
            port=f"{host}:{port}",
            device_address=device_address,
            timeout=timeout,
            hk_interval=hk_interval,
            **kwargs,
        )

    # =========================================================================
    #     Transport override (TCP instead of pyserial)
    # =========================================================================

    def _open_transport(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.tcp_port))
        self.serial_connection = _TcpSocketWrapper(sock)

    def _close_transport(self) -> None:
        if self.serial_connection:
            self.serial_connection.close()
        self.serial_connection = None

    def _transport_desc(self) -> str:
        return f"TCP {self.host}:{self.tcp_port}"

    def extra_status(self) -> Dict[str, Any]:
        status = super().extra_status()
        status.update({"host": self.host, "tcp_port": self.tcp_port})
        return status
