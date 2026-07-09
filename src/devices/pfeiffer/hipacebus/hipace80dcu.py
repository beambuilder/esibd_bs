"""
HiPace80DCU device controller.

HiPace80 variant for the MPI loadlock: TC110 drive electronics powered by a
DCU110 (display + power pack), no OmniControl. The DCU's RS-485 leg is
unplugged so the PC is the sole bus master (the DCU display goes dark but
its power-pack section keeps feeding the TC110 — verified 2026-07-09).

Why a separate class: with the DCU gone nothing biases the RS-485 line, and
the cheap USB converter provides no failsafe bias. Consequence (observed
2026-07-09): when a transmitter releases the floating bus, the FINAL byte of
a telegram — the terminating CR — is corrupted in either direction:

- TC110 -> PC: frame arrives complete and checksum-valid, but the CR shows
  up as a non-ASCII byte (e.g. 0xC3). The stock reader then fails with
  "gauge response incorrectly terminated".
- PC -> TC110: the request's CR is corrupted at the pump, the pump discards
  the request, no reply at all ("gauge response too short").

This class therefore uses a tolerant telegram exchanger instead of the stock
``query_data``/``write_command``:

1. A response whose checksum verifies is accepted even if the trailing CR
   never arrived (the CR is redundant once the checksum passes — data
   integrity is still fully enforced).
2. Lost/garbled exchanges are retried (input buffer flushed between
   attempts, so stale late replies are discarded). Definitive device errors
   (NO_DEF/_RANGE/_LOGIC) are never retried.

No other Pfeiffer code path is touched; the biased buses (OmniControl
setups) keep using the stock protocol functions. Proper fix remains a
converter with failsafe bias — then this class can be retired for plain
HiPace80Bus.

Note: the TC110 may answer NO_DEF ("undefined parameter number") for
TC80-specific parameters (power backup, rotor temperature, ...). That is a
clean device answer, not a comm failure.
"""

from typing import Optional
import time

from .hipace80bus import HiPace80Bus


# =============================================================================
#     Tolerant telegram exchange (module-level, self-contained)
# =============================================================================

#: Shortest valid frame WITHOUT the trailing CR:
#: addr(3) + action(2) + param(3) + len(2) + data(>=2) + checksum(3)
_MIN_FRAME_LEN = 13


def _read_response_tolerant(s):
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
            if _frame_checksum_ok(r):
                break
            continue  # mid-frame glitch: drop byte, keep reading

        if ch == "\r":
            break
        r += ch  # CR excluded; parsing below works on the bare frame

    if len(r) < _MIN_FRAME_LEN:
        raise ValueError(f"response too short to be valid (len={len(r)})")

    if not _frame_checksum_ok(r):
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


def _frame_checksum_ok(r: str) -> bool:
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


def _exchange_with_retry(s, addr: int, param_num: int, attempts: int,
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
            raddr, rw, rparam_num, rdata = _read_response_tolerant(s)

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


# =============================================================================
#     Device class
# =============================================================================

# TC110 parameter-set differences (vs the TC80 the base class targets).
# The TC110 manual's parameter list lacks these TC80 parameters (a query
# answers NO_DEF): 58 TmpMgtMode, 324 TmpPwrStg, 384 TempRotor, 396 AddID,
# 726/728/733/734 (power backup). C1/D1 (params 68/69) don't exist either —
# the TC110 connector panel has A1/B1/DO1 only. Since hk_monitor aborts at
# the first failing channel, the TC110 needs its own HK table. Extras the
# TC80 lacks: 342 TempBearng, 346 TempMotor. (Module-level because a
# class-body genexpr cannot see class attributes.)
_TC110_MISSING_CHANNELS = frozenset({
    "Temperature_Management", "Temp_Power_Stage", "Temp_Rotor",
    "Pump_Identification", "Max_Power_Output_Time", "Fan_On_Temperature",
    "Power_Output_Voltage", "Power_Output_Threshold",
    "Cfg_Acc_C1", "Cfg_Acc_D1",
})


class HiPace80DCU(HiPace80Bus):
    """
    HiPace80 behind a TC110 + DCU110 on an unbiased RS-485 line (MPI
    loadlock). Same API and housekeeping as HiPace80Bus; only the telegram
    exchange is replaced by the tolerant/retrying implementation above.

    Extra args:
        comm_attempts: telegram attempts per call (default 3)
        comm_retry_delay: pause between attempts in seconds (default 0.05)

    Example:
        pump = HiPace80DCU("hipace80_mpi", port="COM9", tc80_address=1)
        pump.connect()
        pump.get_pump_firmware_version()
    """

    HK_CHANNELS = tuple(
        c for c in HiPace80Bus.HK_CHANNELS
        if c[0] not in _TC110_MISSING_CHANNELS
    ) + (
        ("Temp_Bearing", "degC", "", "get_bearing_temperature"),
        ("Temp_Motor", "degC", "", "get_motor_temperature"),
        ("Cfg_DO1", "", "", "get_cfg_do1"),
    )

    _SIM_PARAMS = {
        **HiPace80Bus._SIM_PARAMS,
        ("tc80", 24): ("do1", "u_short_int"),
    }

    def __init__(self, *args, comm_attempts: int = 3,
                 comm_retry_delay: float = 0.05, **kwargs):
        super().__init__(*args, **kwargs)
        self.comm_attempts = comm_attempts
        self.comm_retry_delay = comm_retry_delay
        # Sim defaults mirror the MPI-loadlock wiring: A1 = venting valve,
        # B1 = heating, DO1 = free (rotation-speed switch point).
        self._sim_state.update({"acc_a1": 1, "acc_b1": 2, "do1": 0})

    # -------------------------------------------------------------------------
    #     TC110 accessory / output configuration
    # -------------------------------------------------------------------------

    def _validate_accessory_config_tc80(self, config: int) -> None:
        """Validate a TC110 accessory configuration value. The TC110 uses
        the full TC400-style range 0-14 (no 11), not the TC80's 0-13."""
        valid_configs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14]
        if config not in valid_configs:
            raise ValueError(f"TC110 configuration must be one of {valid_configs}")

    def set_cfg_do1(self, config: int) -> None:
        """
        Set configuration for digital output DO1 (Cfg DO1, TC110 [P:024]).

        The TC110 has no C1/D1 accessory ports; DO1 is its third
        configurable output. Functions per [P:019]: 0 = rotation speed
        switch point reached, 1 = no error, 2 = error, 3 = warning,
        4 = error and/or warning, 5 = set rotation speed reached,
        6 = pump on, 7 = pump accelerating, 8 = pump decelerating,
        9 = always "0", 10 = always "1", 11 = remote priority active,
        12 = heating, 13 = backing pump, 14 = sealing gas,
        15 = pumping station, 16 = pump rotates, 17 = pump does not
        rotate, 18 = TMS settled (TMS pumps only), 19/20 = pressure
        switch point 1/2 underrun, 21 = fore-vacuum valve delayed,
        22 = backing pump standby.
        """
        if not isinstance(config, int) or not 0 <= config <= 22:
            raise ValueError("DO1 configuration must be an integer 0..22")
        value = self.data_converter.int_2_u_short_int(config)
        self._set_channel_parameter('tc80', 24, value)

    def get_cfg_do1(self) -> int:
        """Get configuration for digital output DO1 (Cfg DO1, TC110 [P:024])."""
        response = self._query_channel_parameter('tc80', 24)
        return self.data_converter.u_short_int_2_int(response)

    # -------------------------------------------------------------------------
    #     TC110 status extras (missing on the TC80)
    # -------------------------------------------------------------------------

    def get_bearing_temperature(self) -> int:
        """Get bearing temperature in °C (TempBearng, TC110 [P:342])."""
        response = self._query_channel_parameter('tc80', 342)
        return self.data_converter.u_integer_2_int(response)

    def get_motor_temperature(self) -> int:
        """Get motor temperature in °C (TempMotor, TC110 [P:346])."""
        response = self._query_channel_parameter('tc80', 346)
        return self.data_converter.u_integer_2_int(response)

    def _sim_channels(self) -> dict:
        sim = super()._sim_channels()
        running = self._sim_state["pump_on"]
        sim.update({
            "Temp_Bearing": round(self._sim_uniform(30, 36, 0) if running
                                  else self._sim_uniform(23, 27, 0)),
            "Temp_Motor": round(self._sim_uniform(35, 42, 0) if running
                                else self._sim_uniform(23, 27, 0)),
            "Cfg_DO1": self._sim_state["do1"],
        })
        return sim

    def _resolve_channel_address(self, channel) -> int:
        if isinstance(channel, str):
            if channel not in self.channel_addresses:
                raise ValueError(
                    f"Unknown channel '{channel}'. "
                    f"Available: {list(self.channel_addresses.keys())}"
                )
            return self.channel_addresses[channel]
        if isinstance(channel, int):
            return channel
        raise ValueError("Channel must be a string identifier or integer address")

    def _query_channel_parameter(self, channel, param_num: int) -> str:
        if self.test_mode:
            return super()._query_channel_parameter(channel, param_num)

        device_address = self._resolve_channel_address(channel)
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        try:
            with self.thread_lock:
                return _exchange_with_retry(
                    self.serial_connection, device_address, param_num,
                    self.comm_attempts, self.comm_retry_delay,
                )
        except Exception as e:
            self.logger.error(
                f"Failed to query channel {channel} (addr: {device_address}) "
                f"parameter {param_num}: {e}"
            )
            raise

    def _set_channel_parameter(self, channel, param_num: int, value: str) -> None:
        if self.test_mode:
            super()._set_channel_parameter(channel, param_num, value)
            return

        device_address = self._resolve_channel_address(channel)
        if not self.is_connected or not self.serial_connection:
            raise Exception("Device not connected. Call connect() first.")

        try:
            with self.thread_lock:
                # Retried writes are safe: these parameters are absolute
                # values (booleans/setpoints), so a repeated send is
                # idempotent, and the acknowledgment check verifies the
                # accepted value each attempt.
                _exchange_with_retry(
                    self.serial_connection, device_address, param_num,
                    self.comm_attempts, self.comm_retry_delay, data_str=value,
                )
        except Exception as e:
            self.logger.error(
                f"Failed to set channel {channel} (addr: {device_address}) "
                f"parameter {param_num}: {e}"
            )
            raise
