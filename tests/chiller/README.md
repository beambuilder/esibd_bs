# Chiller Unit Tests

This directory contains comprehensive unit tests for the Chiller device class.

## Test Structure

The tests are organized following the same pattern as the Arduino tests:

```
tests/
├── arduino/
│   └── test_arduino.py
├── chiller/
│   └── test_chiller.py    # <-- New chiller tests
└── README.md
```

## Test Coverage

The `test_chiller.py` file includes tests for:

### Core Functionality
- ✅ **Initialization** - Default and custom parameters
- ✅ **Connection Management** - Connect, disconnect, error handling
- ✅ **Status Reporting** - Device status and configuration
- ✅ **Communication** - Low-level read/write operations

### Device Operations
- ✅ **Temperature Control** - Reading current and set temperatures
- ✅ **Pump Management** - Reading and setting pump levels (1-6)
- ✅ **Device Control** - Start, stop, keylock operations
- ✅ **Status Monitoring** - Running state, cooling mode, diagnostics

### Housekeeping Functions
- ✅ **Custom Logger** - Formatted logging functionality
- ✅ **HK Monitor** - Comprehensive device monitoring
- ✅ **Error Handling** - Exception management and edge cases

### Integration Tests
- ✅ **Full Operation Cycle** - Connect → Read → Write → Disconnect
- ✅ **Error Scenarios** - Operations without connection
- ✅ **Logger Integration** - Logging throughout operations

## Running the Tests

### Using the command you provided:
```bash
conda run --live-stream --name ESIBD pytest tests/
```

### Or specifically for chiller tests:
```bash
conda run --live-stream --name ESIBD pytest tests/chiller/ -v
```

### To run individual test classes:
```bash
conda run --live-stream --name ESIBD pytest tests/chiller/test_chiller.py::TestChiller -v
conda run --live-stream --name ESIBD pytest tests/chiller/test_chiller.py::TestChillerCommands -v
conda run --live-stream --name ESIBD pytest tests/chiller/test_chiller.py::TestChillerIntegration -v
```

## Test Classes

1. **TestChiller** - Main test class for all chiller functionality
2. **TestChillerCommands** - Tests for command constants
3. **TestChillerIntegration** - Integration and end-to-end tests

## Notes

- Tests use mocking to avoid requiring actual hardware
- All chiller methods and properties are thoroughly tested
- Error conditions and edge cases are covered
- Tests validate the new housekeeping functions (hk_monitor, custom_logger)
- Integration tests verify complete operation workflows

The tests are designed to catch regressions and ensure robust operation of the chiller class in your lab automation system.
