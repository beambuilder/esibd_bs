# Test Directory & Reporting Configuration

This directory contains all unit tests for the lab device management system with automated report generation.

## Directory Structure

```
tests/
├── arduino/
│   └── test_arduino.py               # Arduino device unit tests
├── chiller/
│   ├── test_chiller.py               # Chiller device unit tests (NEW)
│   └── README.md                     # Chiller test documentation
├── reports/
│   ├── test_report.html              # Main HTML test report (auto-generated)
│   ├── test_results.xml              # JUnit XML for CI/CD (auto-generated)
│   ├── coverage_report/              # Code coverage analysis (auto-generated)
│   │   ├── index.html                # Coverage dashboard
│   │   └── src_devices_*.html        # Per-module coverage
│   ├── arduino_test_report.html      # Legacy Arduino HTML report
│   └── arduino_test_results.txt      # Legacy Arduino text results
└── README.md                         # This file
```

## Running Tests

### 🎯 Quick Start - All Tests with Automatic Reports
```bash
conda run --live-stream --name ESIBD pytest tests/ -v
```
**Automatically generates**: HTML report, XML report, and coverage analysis in `tests/reports/`

### Device-Specific Tests

#### Arduino Tests
```bash
conda run --live-stream --name ESIBD pytest tests/arduino/ -v
```

#### Chiller Tests  
```bash
conda run --live-stream --name ESIBD pytest tests/chiller/ -v
```

## Automatic Report Generation

The updated `pyproject.toml` configuration automatically generates comprehensive reports:

### 📁 Generated Files:
- **HTML Report**: `tests/reports/test_report.html` (interactive, detailed)
- **XML Report**: `tests/reports/test_results.xml` (CI/CD compatible)  
- **Coverage Report**: `tests/reports/coverage_report/index.html` (code coverage analysis)

### 📊 Report Contents:
- **HTML Test Report**: Test execution summary, detailed results with timing, error messages and stack traces, environment information
- **Coverage Report**: Line-by-line code coverage analysis, missing coverage highlighting, coverage percentage per module
- **XML Report**: Machine-readable test results compatible with CI/CD systems

## Manual Report Generation

For customized reporting:

### HTML Report Only:
```bash
conda run --name ESIBD pytest tests/chiller/ --html=tests/reports/chiller_report.html --self-contained-html
```

### Coverage Report Only:
```bash
conda run --name ESIBD pytest tests/chiller/ --cov=src --cov-report=html:tests/reports/chiller_coverage
```

### All Tests with Custom Reports:
```bash
conda run --name ESIBD pytest tests/ --html=tests/reports/full_test_report.html --cov=src --cov-report=html:tests/reports/full_coverage
```

## Adding New Device Tests

When adding tests for new devices, follow this structure:

1. **Create directory**: `tests/{device_name}/`
2. **Create test file**: `tests/{device_name}/test_{device_name}.py`
3. **Follow pattern**: Use existing Arduino/Chiller tests as templates
4. **Run tests**: `conda run --live-stream --name ESIBD pytest tests/{device_name}/ -v`

Reports will be automatically generated and included in the main test report.

## Current Test Coverage

### Arduino Device (17 tests)
- ✅ Initialization with different parameters
- ✅ Connection/disconnection handling  
- ✅ Data parsing for pump_locker and trafo_locker formats
- ✅ Error handling for invalid data
- ✅ Status reporting and serial communication mocking

### Chiller Device (34 tests) 🆕
- ✅ Initialization (default and custom parameters)
- ✅ Connection management (connect, disconnect, error handling)
- ✅ Temperature control (read/write operations)
- ✅ Pump management (levels 1-6 with validation)
- ✅ Device control (start, stop, keylock operations)  
- ✅ Status monitoring (running state, cooling mode, diagnostics)
- ✅ Housekeeping functions (custom_logger, hk_monitor)
- ✅ Integration tests (full operation cycles)

## Installation Requirements

To use HTML reporting features:
```bash
conda install -n ESIBD pytest-html
# or  
pip install pytest-html
```

## Configuration

Automatic report generation is configured in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = [
    "--html=tests/reports/test_report.html",
    "--junitxml=tests/reports/test_results.xml", 
    "--cov=src",
    "--cov-report=html:tests/reports/coverage_report"
]
```

## Notes

- ✅ **Tests use mocking** to avoid requiring actual hardware connections
- ✅ **Each device has its own directory** for better organization  
- ✅ **Reports are automatically generated** and saved for documentation
- ✅ **Coverage analysis** shows how well your code is tested
- ✅ **CI/CD compatible** with XML report generation
- ✅ **Reports persist** between test runs for historical tracking
