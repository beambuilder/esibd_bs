# Test Directory Structure

This directory contains all unit tests for the lab device management system.

## Directory Structure

```
tests/
├── arduino/
│   └── test_arduino.py      # Arduino device unit tests
├── reports/
│   ├── arduino_test_report.html      # HTML test report for Arduino
│   └── arduino_test_results.txt      # Text test results for Arduino
└── README.md                # This file
```

## Running Tests

### Arduino Tests
To run the Arduino unit tests:

```bash
# Run Arduino tests with verbose output
conda run --live-stream --name ESIBD pytest tests/arduino/test_arduino.py -v

# Run Arduino tests and save results to file
conda run --live-stream --name ESIBD pytest tests/arduino/test_arduino.py -v > tests/reports/arduino_test_results.txt 2>&1
```

### All Tests
To run all tests in the future:

```bash
# Run all device tests
conda run --live-stream --name ESIBD pytest tests/ -v
```

## Adding New Device Tests

When adding tests for new devices (e.g., chiller, pump, etc.), follow this structure:

1. Create a new directory: `tests/{device_name}/`
2. Create test file: `tests/{device_name}/test_{device_name}.py`
3. Run tests: `conda run --live-stream --name ESIBD pytest tests/{device_name}/test_{device_name}.py -v`
4. Save results: `conda run --live-stream --name ESIBD pytest tests/{device_name}/test_{device_name}.py -v > tests/reports/{device_name}_test_results.txt 2>&1`

## Test Reports

Test reports are saved in the `reports/` directory:

- **HTML Reports**: `{device_name}_test_report.html` - Visual, formatted reports
- **Text Reports**: `{device_name}_test_results.txt` - Raw pytest output

## Current Test Coverage

### Arduino Device (17 tests)
- ✅ Initialization with different parameters
- ✅ Connection/disconnection handling
- ✅ Data parsing for pump_locker format
- ✅ Data parsing for trafo_locker format
- ✅ Error handling for invalid data
- ✅ Status reporting
- ✅ Serial communication mocking

All Arduino tests pass with 100% success rate.

## Notes

- Tests use mocking to avoid requiring actual hardware connections
- Each device has its own test directory for better organization
- Test results are saved for documentation and CI/CD purposes
- Tests can be run individually or as a complete suite
