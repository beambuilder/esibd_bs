# AMPR-12 Device Driver

This directory contains the implementation for controlling CGC AMPR-12 amplifier devices. The AMPR-12 is a multi-channel amplifier that can manage up to 12 modules, where each module can hold up to 4 individual voltage supplies.

## Files Overview

### Core Implementation

- **`ampr_base.py`** - Base hardware communication class
  - Direct DLL interface to COM-AMPR-12.dll
  - Low-level hardware communication methods
  - Error codes and state constants
  - Module management functions

- **`ampr.py`** - Main AMPR device class
  - High-level device interface with logging
  - Threading and housekeeping support
  - Connection management
  - Enhanced error handling and monitoring

- **`__init__.py`** - Module initialization
  - Exports AMPR and AMPRBase classes

### Documentation and Examples

- **`README.md`** - This file
- **`example_usage.py`** - Comprehensive usage examples
- **`test_ampr.py`** - Basic functionality tests

### Hardware Dependencies

- **`AMPR-12_1_01/`** - Hardware interface files
  - `x64/COM-AMPR-12.dll` - 64-bit DLL for hardware communication
  - `COM-AMPR-12.h` - C header file with API definitions

## Features

### Device Management
- Device connection/disconnection
- Baud rate configuration
- Device restart and control
- Status monitoring

### State Monitoring
- Main device state
- Device state flags
- Voltage state monitoring
- Temperature state monitoring
- Interlock state monitoring

### Housekeeping
- Real-time monitoring of device parameters
- Automatic logging of device status
- Configurable monitoring intervals
- Thread-safe operation

### Module Management
- Support for up to 12 modules
- 4 voltage channels per module
- Individual and bulk voltage control
- Module scanning and identification
- Module housekeeping data

### Logging and Threading
- Comprehensive logging system
- Thread-safe communication
- Internal or external thread management
- Configurable log levels and outputs

## Usage Examples

### Basic Device Control

```python
from src.devices.cgc.ampr import AMPR

# Create AMPR instance
ampr = AMPR("main_ampr", com=5)

# Connect and configure
ampr.connect()

# Enable PSUs
status, enabled = ampr.enable_psu(True)

# Get device state
status, state_hex, state_name = ampr.get_state()
print(f"Device state: {state_name}")

# Start housekeeping
ampr.start_housekeeping(interval=5.0)

# Disconnect
ampr.disconnect()
```

### Module Voltage Control

```python
# Scan for connected modules
modules = ampr.scan_modules()

# Set voltages for module 0, channels 1-4
voltages = [10.0, 20.0, 30.0, 40.0]
results = ampr.set_module_voltages(0, voltages)

# Read current voltages
current_voltages = ampr.get_module_voltages(0)

# Set individual channel
ampr.set_module_voltage(0, 1, 15.5)
```

### Advanced Configuration

```python
import logging
import threading

# Custom logger
logger = logging.getLogger("my_ampr")

# Shared thread resources
thread_lock = threading.Lock()
hk_thread = threading.Thread()

# Create AMPR with advanced options
ampr = AMPR(
    device_id="advanced_ampr",
    com=5,
    baudrate=230400,
    logger=logger,
    thread_lock=thread_lock,
    hk_thread=hk_thread,
    hk_interval=2.0
)
```

## Hardware Interface

### DLL Functions
The implementation interfaces with the COM-AMPR-12.dll through ctypes. Key function categories:

- **Communication**: Open, close, purge, baud rate
- **General**: Version info, product info, housekeeping
- **Controller**: State management, PSU control, interlock
- **Modules**: Module scanning, voltage control, housekeeping

### Error Handling
All hardware operations return status codes:
- `NO_ERR (0)`: Success
- Negative values: Various error conditions
- Error messages available through logging system

### Threading Considerations
- All communication is thread-safe using locks
- Housekeeping can run in dedicated thread
- External thread management supported for integration

## Module Architecture

### AMPR-12 Module System
- **Base Controller**: Main AMPR-12 unit (address 0x80)
- **Modules**: Up to 12 expansion modules (addresses 0-11)
- **Channels**: 4 voltage outputs per module
- **Communication**: Serial communication via COM port

### Module Addressing
- Base module: Address 0x80 (128)
- Expansion modules: Addresses 0-11
- Broadcast address: 0xFF (255)

### Voltage Control
- Each channel supports independent voltage control
- Voltage setpoint and measured values
- Module-specific housekeeping data

## Error Codes

### Communication Errors
- `ERR_OPEN (-2)`: Error opening port
- `ERR_CLOSE (-3)`: Error closing port
- `ERR_COMMAND_SEND (-7)`: Error sending command
- `ERR_COMMAND_RECEIVE (-10)`: Error receiving command

### Device Errors
- `ERR_NOT_CONNECTED (-100)`: Device not connected
- `ERR_NOT_READY (-101)`: Device not ready
- Various device state errors (see MAIN_STATE dictionary)

## Logging

### Log Levels
- **INFO**: Connection, major operations
- **WARNING**: Non-critical issues
- **ERROR**: Critical errors, failures
- **DEBUG**: Detailed operation information

### Log Outputs
- File logging with timestamps
- Console logging (configurable)
- Custom logger integration

## Testing

Run the test suite to verify implementation:

```bash
python src/devices/cgc/ampr/test_ampr.py
```

Tests include:
- Initialization verification
- Constants and error codes
- Status methods
- Logging setup
- Threading configuration
- Module method availability
- Base class inheritance

## Dependencies

### Required Libraries
- `ctypes` - DLL interface
- `json` - Configuration file parsing
- `threading` - Thread management
- `logging` - Logging system
- `os`, `pathlib` - File system operations

### Hardware Requirements
- CGC AMPR-12 device
- Windows system (for DLL compatibility)
- Available COM port
- Proper device drivers

## Integration Notes

### PSU Compatibility
The AMPR implementation follows the same pattern as the PSU implementation:
- Similar class structure and method signatures
- Compatible logging and threading systems
- Consistent error handling approach

### System Integration
- Can be integrated with existing device management systems
- Thread-safe for multi-device operations
- Configurable for various system architectures

## Troubleshooting

### Common Issues
1. **DLL not found**: Verify COM-AMPR-12.dll is in correct directory
2. **Connection failures**: Check COM port availability and permissions
3. **Threading issues**: Ensure proper lock usage in multi-threaded environments

### Debug Information
Enable DEBUG logging to see detailed operation information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Version History

- **v1.0**: Initial implementation based on PSU pattern
  - Complete DLL interface
  - Module management support
  - Logging and threading integration
  - Comprehensive documentation and examples

## License

Part of the ESIBD_BS project. See project license for details.