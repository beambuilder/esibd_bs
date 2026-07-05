"""
Base-layer tests: the pure ctypes wrappers (AMPRBase, PABase) against a
fake WinDLL — construction, DLL paths, error dicts, representative
argument marshalling (scalar in, byref out, arrays, string buffers,
multi-value unpacks, state-bit decoding) and error-constant spot checks
against the vendor headers.
"""
import ctypes
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from devices.cgc.ampr.ampr_base import AMPRBase
from devices.cgc.pA.pA_base import PABase


# =========================================================================
#     AMPRBase
# =========================================================================

def test_amprbase_construction_loads_dll_and_error_dict(dll_factory):
    base = AMPRBase(com=6)
    assert dll_factory.paths[-1].endswith("AMPR-12_1_01\\x64\\COM-AMPR-12.dll")
    assert base.err_dict["-2"] == "Error opening port"
    assert base.err_dict["0"] == "No error"
    assert base.com == 6


def test_second_amprbase_loads_private_dll_copy(dll_factory):
    # The vendor DLL holds ONE implicit communication channel per loaded
    # module (no port handles); a second instance sharing the module would
    # steal the first one's channel. Instances beyond the first must load
    # a private on-disk copy of the DLL (distinct path = distinct module).
    import os

    first = AMPRBase(com=6)
    second = AMPRBase(com=8)
    assert dll_factory.paths[0].endswith("AMPR-12_1_01\\x64\\COM-AMPR-12.dll")
    assert dll_factory.paths[1] != dll_factory.paths[0]
    assert "cgc_private_dlls" in dll_factory.paths[1]
    assert os.path.isfile(dll_factory.paths[1])  # a real copy on disk
    assert first.ampr_dll is not second.ampr_dll


def test_two_amprbases_open_ports_on_separate_channels(dll_factory):
    first = AMPRBase(com=6)
    second = AMPRBase(com=8)
    first.open_port(6)
    second.open_port(8)
    first_opens = [args[0].value for name, args in dll_factory.dlls[0].calls if name == "COM_AMPR_12_Open"]
    second_opens = [args[0].value for name, args in dll_factory.dlls[1].calls if name == "COM_AMPR_12_Open"]
    assert first_opens == [6]
    assert second_opens == [8]


def test_amprbase_open_port_marshals_c_ubyte(dll_factory):
    base = AMPRBase(com=6)
    assert base.open_port(6) == 0
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_AMPR_12_Open"
    assert isinstance(args[0], ctypes.c_ubyte)
    assert args[0].value == 6


def test_amprbase_set_baud_rate_byref_roundtrip(dll_factory):
    base = AMPRBase(com=6)

    def negotiate(ref):
        ref._obj.value = 115200
        return 0

    dll_factory.last.handlers["COM_AMPR_12_SetBaudRate"] = negotiate
    assert base.set_baud_rate(230400) == (0, 115200)


def test_amprbase_get_fw_date_string_buffer(dll_factory):
    base = AMPRBase(com=6)

    def fill(buf):
        buf.value = b"Jan 01 2026"
        return 0

    dll_factory.last.handlers["COM_AMPR_12_GetFwDate"] = fill
    assert base.get_fw_date() == (0, "Jan 01 2026")


def test_amprbase_get_housekeeping_15_tuple_unpack(dll_factory):
    base = AMPRBase(com=6)

    def fill(*refs):
        assert len(refs) == 14
        for i, ref in enumerate(refs):
            ref._obj.value = float(i + 1)
        return 0

    dll_factory.last.handlers["COM_AMPR_12_GetHousekeeping"] = fill
    result = base.get_housekeeping()
    assert result[0] == 0
    assert result[1:] == tuple(float(i + 1) for i in range(14))


def test_amprbase_measured_voltages_array_out(dll_factory):
    base = AMPRBase(com=6)

    def fill(address, arr):
        assert isinstance(address, ctypes.c_uint)
        assert address.value == 3
        for i in range(4):
            arr[i] = i * 1.5
        return 0

    dll_factory.last.handlers["COM_AMPR_12_GetMeasuredModuleOutputVoltages"] = fill
    assert base.get_measured_module_output_voltages(3) == (0, [0.0, 1.5, 3.0, 4.5])


def test_amprbase_get_state_maps_main_state(dll_factory):
    base = AMPRBase(com=6)

    def fill(ref):
        ref._obj.value = 0x8005
        return 0

    dll_factory.last.handlers["COM_AMPR_12_GetState"] = fill
    assert base.get_state() == (0, "0x8005", "ST_ERR_ILOCK")


def test_amprbase_device_state_flag_decode(dll_factory):
    base = AMPRBase(com=6)

    def fill(ref):
        ref._obj.value = (1 << 0x0) | (1 << 0x8)
        return 0

    dll_factory.last.handlers["COM_AMPR_12_GetDeviceState"] = fill
    status, state_hex, names = base.get_device_state()
    assert status == 0
    assert set(names) == {"DS_PSU_ENB", "DS_VOLT_FAIL"}


def test_amprbase_error_constants_match_header():
    assert AMPRBase.NO_ERR == 0
    assert AMPRBase.ERR_OPEN == -2
    assert AMPRBase.ERR_NOT_CONNECTED == -100
    assert AMPRBase.DEVICE_TYPE == 0xA3D8
    assert AMPRBase.MODULE_NUM == 12
    assert AMPRBase.MODULE_CHANNEL_NUM == 4
    assert AMPRBase.ADDR_BASE == 0x80


# =========================================================================
#     PABase
# =========================================================================

def test_pabase_construction_loads_dll_and_error_dict(dll_factory):
    base = PABase(com=7)
    assert dll_factory.paths[-1].endswith("DMMR-8_1-02\\x64\\COM-DMMR-8.dll")
    assert base.err_dict["-100"] == "Device not connected"
    assert base.com == 7


def test_pabase_open_port_marshals_c_ubyte(dll_factory):
    base = PABase(com=7)
    assert base.open_port(7) == 0
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_DMMR_8_Open"
    assert isinstance(args[0], ctypes.c_ubyte)
    assert args[0].value == 7


def test_pabase_set_enable_marshals_c_bool(dll_factory):
    base = PABase(com=7)
    assert base.set_enable(True) == 0
    name, args = dll_factory.last.calls[-1]
    assert name == "COM_DMMR_8_SetEnable"
    assert isinstance(args[0], ctypes.c_bool)
    assert args[0].value is True


def test_pabase_get_current_multi_out_unpack(dll_factory):
    base = PABase(com=7)

    def fill(addr_ref, cur_ref, range_ref, time_ref):
        addr_ref._obj.value = 3
        cur_ref._obj.value = 2.5e-12
        range_ref._obj.value = 2
        time_ref._obj.value = 123.5
        return 0

    dll_factory.last.handlers["COM_DMMR_8_GetCurent"] = fill
    assert base.get_current() == (0, 3, 2.5e-12, 2, 123.5)


def test_pabase_get_module_current_addr_and_out(dll_factory):
    base = PABase(com=7)

    def fill(address, cur_ref, range_ref):
        assert isinstance(address, ctypes.c_uint)
        assert address.value == 4
        cur_ref._obj.value = 1.0e-12
        range_ref._obj.value = 1
        return 0

    dll_factory.last.handlers["COM_DMMR_8_GetModuleCurent"] = fill
    assert base.get_module_current(4) == (0, 1.0e-12, 1)


def test_pabase_get_config_name_string_buffer(dll_factory):
    base = PABase(com=7)

    def fill(number, buf):
        assert isinstance(number, ctypes.c_ushort)
        assert number.value == 12
        buf.value = b"lab default"
        return 0

    dll_factory.last.handlers["COM_DMMR_8_GetConfigName"] = fill
    assert base.get_config_name(12) == (0, "lab default")


def test_pabase_module_housekeeping_17_tuple_unpack(dll_factory):
    base = PABase(com=7)

    def fill(address, *refs):
        assert address.value == 2
        assert len(refs) == 16
        for i, ref in enumerate(refs):
            ref._obj.value = float(i)
        return 0

    dll_factory.last.handlers["COM_DMMR_8_GetModuleHousekeeping"] = fill
    result = base.get_module_housekeeping(2)
    assert result[0] == 0
    assert result[1:] == tuple(float(i) for i in range(16))


def test_pabase_get_error_message_decodes_char_p(dll_factory):
    base = PABase(com=7)
    dll_factory.last.handlers["COM_DMMR_8_GetErrorMessage"] = lambda: b"all fine"
    assert base.get_error_message() == "all fine"


def test_pabase_constants_match_header():
    assert PABase.NO_ERR == 0
    assert PABase.NO_DATA == 1
    assert PABase.ERR_BUFF_FULL == -200
    assert PABase.MODULE_TYPE == 0xC41E
    assert PABase.DEVICE_TYPE == 0xAC38
    assert PABase.MODULE_NUM == 8
    assert PABase.FAN_PWM_MAX == (0x9F << 1) + 1
