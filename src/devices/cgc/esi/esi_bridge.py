"""64-bit client side of the ESI-CTRL 32-bit DLL bridge.

``ESIDllBridge`` is a drop-in stand-in for the ``ctypes.WinDLL`` handle
``ESIBase`` used against the (broken) x64 DLL: attribute access returns
callables that accept the same ctypes arguments (``byref`` scalars,
arrays, ``create_string_buffer`` buffers, by-value scalars) and support
the ``restype`` assignment idiom. Calls are marshalled to a frozen
32-bit server process (``esi_server32.ESIServer32``) which hosts the
32-bit Borland DLL and writes results back into the caller's ctypes
objects.

Server startup costs a couple of seconds once per process; each call adds
~ms of IPC latency — negligible at the 5 s housekeeping cadence.
"""
import atexit
import ctypes
import os

from msl.loadlib import Client64

_SERVER_MODULE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "esi_server32.py"
)


class _BridgeFunc:
    """Callable standing in for one DLL export.

    Cached per export name on the bridge so ``restype`` assignments
    persist across attribute accesses (the ctypes idiom
    ``dll.Func.restype = ...; dll.Func()`` relies on that).
    """

    def __init__(self, bridge, name):
        self._bridge = bridge
        self._name = name
        self.restype = None

    def __call__(self, *args):
        descs = []
        originals = []
        for arg in args:
            if hasattr(arg, "_obj"):  # CArgObject from ctypes.byref()
                obj = arg._obj
                descs.append(("ref", type(obj).__name__, obj.value))
                originals.append(obj)
            elif isinstance(arg, ctypes.Array):
                if arg._type_ is ctypes.c_char:
                    descs.append(("cbuf", arg.raw, len(arg)))
                else:
                    descs.append(("arr", arg._type_.__name__, list(arg)))
                originals.append(arg)
            elif isinstance(arg, ctypes._SimpleCData):
                descs.append(("val", type(arg).__name__, arg.value))
                originals.append(None)
            else:  # plain python int (defensive; ESIBase always wraps)
                descs.append(("val", "c_int", int(arg)))
                originals.append(None)
        restype_name = self.restype.__name__ if self.restype is not None else ""
        ret, outs = self._bridge.request32(
            "call", self._name, restype_name, descs
        )
        for orig, out in zip(originals, outs):
            if orig is None or out is None:
                continue
            if isinstance(orig, ctypes.Array):
                if orig._type_ is ctypes.c_char:
                    orig.raw = out
                else:
                    orig[:] = out
            else:
                orig.value = out
        return ret


class ESIDllBridge(Client64):
    """Proxy for the 32-bit COM-ESI-CTRL DLL.

    Attribute access mirrors a ctypes DLL handle:
    ``bridge.COM_ESI_CTRL_Open(ctypes.c_ubyte(14))``. The Borland
    underscore decoration (``_COM_ESI_CTRL_*``) is applied server-side.
    """

    def __init__(self, dll_path=None):
        self._funcs = {}
        kwargs = {"dll_path": dll_path} if dll_path else {}
        super().__init__(_SERVER_MODULE, **kwargs)
        atexit.register(self._shutdown_quietly)

    def _shutdown_quietly(self):
        try:
            self.shutdown_server32()
        except Exception:
            pass

    def __getattr__(self, name):
        if name.startswith("COM_ESI_CTRL_"):
            func = self._funcs.get(name)
            if func is None:
                func = _BridgeFunc(self, name)
                self._funcs[name] = func
            return func
        raise AttributeError(name)
