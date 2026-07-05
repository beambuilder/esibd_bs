"""
Shared fixtures for the CGC test suite.

The CGC bases call ``ctypes.WinDLL(path)`` in ``__init__``; ``FakeDLL``
stands in for the returned handle: every export records its call and
returns status 0 unless a handler is installed for that export name.
byref out-parameters are reached through ``arg._obj`` in handlers.
"""
import ctypes
import logging
import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class FakeDLL:
    """Fake vendor-DLL handle: records calls, returns 0 or handler result."""

    def __init__(self, path=None):
        self.path = path
        self.calls = []
        self.handlers = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def export(*args, _name=name):
            self.calls.append((_name, args))
            handler = self.handlers.get(_name)
            return handler(*args) if handler is not None else 0

        return export

    def call_names(self):
        return [name for name, _ in self.calls]


class DLLFactory:
    """Replaces ctypes.WinDLL; hands out FakeDLL instances and records paths."""

    def __init__(self):
        self.paths = []
        self.dlls = []

    def __call__(self, path):
        dll = FakeDLL(path)
        self.paths.append(path)
        self.dlls.append(dll)
        return dll

    @property
    def last(self):
        return self.dlls[-1]


@pytest.fixture
def dll_factory(monkeypatch):
    factory = DLLFactory()
    monkeypatch.setattr(ctypes, "WinDLL", factory)
    return factory


@pytest.fixture(autouse=True)
def reset_private_dll_counter():
    """Instances beyond the first load a private DLL copy (one channel per
    module); reset the process-wide counter so every test starts at the
    canonical path regardless of test order."""
    from devices.cgc.ampr.ampr_base import AMPRBase

    AMPRBase._dll_load_count = 0
    yield


class _ListHandler(logging.Handler):
    def __init__(self, records):
        super().__init__()
        self.records = records

    def emit(self, record):
        self.records.append(record.getMessage())


def capture_logger():
    """Standalone logger (not in the manager tree) capturing messages."""
    logger = logging.Logger("cgc_test")
    logger.setLevel(logging.INFO)
    records = []
    logger.addHandler(_ListHandler(records))
    return logger, records
