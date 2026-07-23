"""32-bit bridge server hosting the Borland COM-ESI-CTRL.dll (DLL 1-00).

The manufacturer-supported DLL in ``ESI-CTRL_1-00/`` is a 32-bit Borland
build (cdecl calling convention, underscore-prefixed exports such as
``_COM_ESI_CTRL_Open``); the ``x64/`` build is broken (manufacturer
statement, 2026-07-23) and 64-bit Python cannot load a 32-bit DLL
directly (WinError 193). This module runs inside msl-loadlib's frozen
32-bit server process and executes DLL calls on behalf of the 64-bit
client proxy in ``esi_bridge``.

Runs in the frozen 32-bit interpreter: stdlib + msl.loadlib only — never
import from the devices package here.
"""
import ctypes
import os

from msl.loadlib import Server32


class ESIServer32(Server32):
    """Generic call marshaller for the 32-bit COM-ESI-CTRL DLL."""

    def __init__(self, host, port, dll_path=None, **kwargs):
        if not dll_path:
            dll_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "ESI-CTRL_1-00", "COM-ESI-CTRL.dll",
            )
        super().__init__(dll_path, "cdll", host, port)

    def call(self, name, restype_name, arg_descs):
        """Execute export ``_<name>`` with reconstructed ctypes arguments.

        ``arg_descs`` entries (built by ``esi_bridge._BridgeFunc``):

        - ``("ref", type_name, value)`` — byref scalar (out/inout)
        - ``("val", type_name, value)`` — by-value scalar
        - ``("arr", type_name, values)`` — array of scalars (out/inout)
        - ``("cbuf", raw_bytes, size)`` — char buffer (out/inout)

        Returns ``(retval, out_values)`` with ``out_values`` aligned to
        ``arg_descs`` (``None`` for by-value entries).
        """
        func = getattr(self.lib, "_" + name)
        func.restype = (
            getattr(ctypes, restype_name) if restype_name else ctypes.c_int
        )
        cargs = []
        holders = []
        for desc in arg_descs:
            kind = desc[0]
            if kind == "ref":
                obj = getattr(ctypes, desc[1])(desc[2])
                cargs.append(ctypes.byref(obj))
                holders.append(obj)
            elif kind == "val":
                cargs.append(getattr(ctypes, desc[1])(desc[2]))
                holders.append(None)
            elif kind == "arr":
                arr = (getattr(ctypes, desc[1]) * len(desc[2]))(*desc[2])
                cargs.append(arr)
                holders.append(arr)
            elif kind == "cbuf":
                buf = (ctypes.c_char * desc[2])()
                buf.raw = desc[1][:desc[2]]
                cargs.append(buf)
                holders.append(buf)
            else:
                raise ValueError(f"unknown arg kind {kind!r}")
        ret = func(*cargs)
        outs = []
        for holder in holders:
            if holder is None:
                outs.append(None)
            elif isinstance(holder, ctypes.Array):
                outs.append(
                    holder.raw if holder._type_ is ctypes.c_char else list(holder)
                )
            else:
                outs.append(holder.value)
        return ret, outs
