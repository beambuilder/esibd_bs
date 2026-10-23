"""
Tolerant Pfeiffer telegram exchange for RS-485 lines that corrupt the
terminating CR.

On a line without failsafe bias, the FINAL byte of a telegram (the CR) can
be corrupted when a transmitter releases the bus: the reply arrives
checksum-valid but ends in a non-ASCII byte (seen: 0xC3), or the pump never
sees a valid request and stays silent. Observed on the MPI TC110 (2026-07-09,
``HiPace80DCU``) and on the QMS TC400 behind its OmniControl (2026-10-23,
``HiPace300Bus(tolerant_comm=True)``).

``exchange_with_retry`` replaces the stock ``query_data``/``write_command``:

1. A response whose checksum verifies is accepted even if the trailing CR
   never arrived (data integrity is still fully enforced by the checksum).
2. Lost/garbled exchanges are retried with the input buffer flushed between
   attempts. Definitive device errors (NO_DEF/_RANGE/_LOGIC) are never
   retried.

The shared ``pfeifferVacuumProtocol`` module stays untouched; classes opt in.
"""

from typing import Optional
import time


#: Shortest valid frame WITHOUT the trailing CR:
#: addr(3) + action(2) + param(3) + len(2) + data(>=2) + checksum(3)
_MIN_FRAME_LEN = 13


def read_response_tolerant(s):
    """
    Read one telegram frame, tolerating a corrupted/missing terminating CR.

    Reads byte-wise until CR, timeout, or a non-ASCII byte. On a non-ASCII
    byte or timeout the buffer is accepted anyway IF its checksum verifies —
    that is exactly the corrupted-CR case. Mid-frame non-ASCII bytes (buffer
    not yet a valid frame) are dropped and reading continues.

    Returns (addr, rw, param_num, data) like the stock reader.
    """
    r = ""
    for _ in range(64):
        c = s.read(1)

        if c == b"":  # timeout — maybe the CR (or more) never arrived
            break

        try:
            ch = c.decode("ascii")
        except UnicodeDecodeError:
            # Non-ASCII byte. If the buffer already checksums as a complete
            # frame, this byte IS the corrupted CR — frame done.
            if frame_checksum_ok(r):
                break
            continue  # mid-frame glitch: drop byte, keep reading

        if ch == "\r":
            break
        r += ch  # CR excluded; parsing below works on the bare frame

    if len(r) < _MIN_FRAME_LEN:
        raise ValueError(f"response too short to be valid (len={len(r)})")

    if not frame_checksum_ok(r):
        raise ValueError("invalid checksum in response")

    addr = int(r[:3])
    rw = int(r[3:4])
    param_num = int(r[5:8])
    data = r[10:-3]

    if data == "NO_DEF":
        raise ValueError("undefined parameter number")
    if data == "_RANGE":
        raise ValueError("data is out of range")
    if data == "_LOGIC":
        raise ValueError("logic access violation")

    return addr, rw, param_num, data


def frame_checksum_ok(r: str) -> bool:
    """True if ``r`` (frame without CR) ends in its own valid checksum."""
    if len(r) < _MIN_FRAME_LEN or not r[-3:].isdigit():
        return False
    return int(r[-3:]) == sum(ord(x) for x in r[:-3]) % 256


def _send_data_request(s, addr: int, param_num: int) -> None:
    c = "{:03d}00{:03d}02=?".format(addr, param_num)
    c += "{:03d}\r".format(sum(ord(x) for x in c) % 256)
    s.write(c.encode())


def _send_control_command(s, addr: int, param_num: int, data_str: str) -> None:
    c = "{:03d}10{:03d}{:02d}{:s}".format(addr, param_num, len(data_str), data_str)
    c += "{:03d}\r".format(sum(ord(x) for x in c) % 256)
    s.write(c.encode())


#: Device answered definitively — retrying cannot change the outcome.
_NO_RETRY_ERRORS = (
    "undefined parameter number",
    "data is out of range",
    "logic access violation",
)


def exchange_with_retry(s, addr: int, param_num: int, attempts: int,
                         retry_delay: float, data_str: Optional[str] = None) -> str:
    """
    One robust telegram exchange: send request (query if ``data_str`` is
    None, else control command), read tolerant response, verify it matches
    the request. Flush + retry on comm failures; device errors raise
    immediately. Returns the response data field.
    """
    last_error: Exception = ValueError("no attempt made")
    for attempt in range(attempts):
        try:
            s.reset_input_buffer()  # also discards stale late replies
            if data_str is None:
                _send_data_request(s, addr, param_num)
            else:
                _send_control_command(s, addr, param_num, data_str)
            raddr, rw, rparam_num, rdata = read_response_tolerant(s)

            if raddr != addr or rw != 1 or rparam_num != param_num:
                raise ValueError(
                    f"response mismatch (addr {raddr}, rw {rw}, param {rparam_num})"
                )
            if data_str is not None and rdata != data_str:
                raise ValueError("invalid acknowledgment from device")
            return rdata
        except ValueError as e:
            if str(e) in _NO_RETRY_ERRORS:
                raise
            last_error = e
            if attempt < attempts - 1:
                time.sleep(retry_delay)
    raise ValueError(
        f"exchange failed after {attempts} attempts "
        f"(addr {addr}, param {param_num}): {last_error}"
    )
