# Based on Package: Link to Package: https://gitlab.ipfdd.de/Henn/pypfeiffervacuumhighscrollprotocol/-/tree/master?ref_type=heads
# General Telegram Frame for Pfeiffer RS-485 Communication

from enum import Enum
import time


class InvalidCharError(Exception):  # Custom exception when failing on invalid chars
    pass


# Control non-ascii char filtering
_filter_invalid_char = False


def enable_valid_char_filter():
    """
    Globally enable a filter to ignore invalid characters coming from the serial device.
    :return:
    """
    global _filter_invalid_char
    _filter_invalid_char = True


def disable_valid_char_filter():
    """
    Globally disable a filter to ignore invalid characters coming from the serial device.
    :return:
    """
    global _filter_invalid_char
    _filter_invalid_char = False


# Error states for vacuum gauges
class ErrorCode(Enum):
    NO_ERROR = 1
    DEFECTIVE_TRANSMITTER = 2
    DEFECTIVE_MEMORY = 3


def _send_data_request(s, addr, param_num):
    c = "{:03d}00{:03d}02=?".format(addr, param_num)
    c += "{:03d}\r".format(sum([ord(x) for x in c]) % 256)
    # print(f"c = {c}")
    s.write(c.encode())


def _send_control_command(s, addr, param_num, data_str):
    c = "{:03d}10{:03d}{:02d}{:s}".format(addr, param_num, len(data_str), data_str)
    c += "{:03d}\r".format(sum([ord(x) for x in c]) % 256)
    return s.write(c.encode())


def _read_gauge_response(s, valid_char_filter=None):
    if valid_char_filter is None:
        valid_char_filter = _filter_invalid_char

    # Read until newline or we stop getting a response
    r = ""
    for _ in range(64):
        
        c = s.read(1)
        
        if c == b"":
            break

        try:
            r += c.decode("ascii")
        except UnicodeDecodeError:
            if valid_char_filter:
                continue
            raise InvalidCharError(
                "Cannot decode character. This issue may sometimes be resolved by ignoring invalid "
                "characters. Enable the filter globally by running the function "
                "`pfeiffer_vacuum_protocol.enable_valid_char_filter()` after the import statement."
            )

        if c == b"\r":
            break
    
    # Debugging -> Printing r
    # print(f"r: {r}")
    
    # Check the length
    if len(r) < 14:
        raise ValueError(f"gauge response too short to be valid len(r) = {len(r)}")

    # Check it is terminated correctly
    if r[-1] != "\r":
        raise ValueError("gauge response incorrectly terminated")

    # Evaluate the checksum
    if int(r[-4:-1]) != (sum([ord(x) for x in r[:-4]]) % 256):
        raise ValueError("invalid checksum in gauge response")

    # Pull out the address
    addr = int(r[:3])
    rw = int(r[3:4])
    param_num = int(r[5:8])
    data = r[10:-4]

    # Check for errors
    if data == "NO_DEF":
        raise ValueError("undefined parameter number")
    if data == "_RANGE":
        raise ValueError("data is out of range")
    if data == "_LOGIC":
        raise ValueError("logic access violation")

    # Return it
    return addr, rw, param_num, data


# Combines sending command and reading request
def write_command(s, addr, param_num, data_str, valid_char_filter = None):
    _send_control_command(s, addr, param_num, data_str)
    raddr, rw, rparam_num, rdata = _read_gauge_response(s, valid_char_filter=valid_char_filter)

    # Check the response
    if raddr != addr or rw != 1 or rparam_num != param_num:
        raise ValueError("invalid response from gauge")

    if rdata != data_str:
        raise ValueError("invalid acknowledgment from gauge")

    return rdata

# Combines sending data request and reading return value from slave
def query_data(s, addr, param_num, valid_char_filter=None):
    s.reset_input_buffer()
    _send_data_request(s, addr, param_num)
    # time.sleep(1)
    raddr, rw, rparam_num, rdata = _read_gauge_response(s, valid_char_filter=valid_char_filter)


    # print(f" rparam_num= {rparam_num}")
    # print(f" param_num= {param_num}")
    # print(f" rdata= {rdata}")

    if raddr != addr or rw != 1 or rparam_num != param_num:
        raise ValueError("invalid response from gauge 99999")

    return rdata


