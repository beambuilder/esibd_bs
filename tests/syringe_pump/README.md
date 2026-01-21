# Syringe Pump Tests

This directory contains comprehensive unit and integration tests for the SyringePump device class.

## Test Coverage

The test suite achieves **92% code coverage** of the syringe_pump module, covering:

- Initialization and configuration
- Connection/disconnection lifecycle
- Serial communication
- Command construction and execution
- Multi-step operations
- Error handling
- Thread safety

## Test Structure

### TestSyringePump
Unit tests for individual methods and features:
- Initialization with default and custom parameters
- External thread/lock management
- Serial connection and disconnection
- Command prefixes (x) and suffixes (mode)
- Communication methods (_send_command, _get_response)
- Pump control commands (start, stop, pause, restart)
- Configuration commands (set_units, set_diameter, set_rate, etc.)
- Query commands (get_parameters, get_pump_status, etc.)
- Utility functions (get_available_ports, _flush_buffers)

### TestSyringePumpIntegration
Integration tests combining multiple operations:
- Typical workflow sequence
- Connection lifecycle
- Multi-step operations with arrays

## Running the Tests

### Run all syringe pump tests:
```bash
pytest tests/syringe_pump/test_syringe_pump.py -v
```

### Run with coverage:
```bash
pytest tests/syringe_pump/test_syringe_pump.py --cov=src/devices/syringe_pump --cov-report=html --cov-report=term-missing
```

### Run specific test:
```bash
pytest tests/syringe_pump/test_syringe_pump.py::TestSyringePump::test_connect_success -v
```

### Run all tests in the repository (includes syringe pump):
```bash
pytest tests/ -v --cov=src --cov-report=html:tests/reports/coverage_report
```

## Test Results

**Total Tests:** 42
- Unit Tests: 39
- Integration Tests: 3

**Status:** All tests passing ✓

## Code Quality

The syringe_pump.py module has been linted and formatted using:
- **black**: Code formatter (line length: 88)
- **flake8**: Style checker (no violations)

## Reports

Test reports are generated in:
- HTML Test Report: `tests/reports/syringe_pump_test_report.html`
- Coverage Report: `tests/reports/syringe_pump_coverage/index.html`
- XML Results: `tests/reports/test_results.xml`

## Test Dependencies

Required packages (installed via `pip install -e ".[dev]"`):
- pytest >= 7.0.0
- pytest-cov >= 4.0.0
- pytest-html >= 3.1.0
- pyserial >= 3.5

## Notes

- Tests use mocking to avoid requiring actual hardware
- Thread-safe tests verify proper lock usage
- External thread/lock management is tested separately
- Multi-platform port detection is tested for Windows and Linux
