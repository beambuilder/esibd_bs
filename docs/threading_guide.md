# Chiller Threading Implementation Guide

## Overview

The Chiller class now supports two distinct threading modes to accommodate different usage scenarios:

1. **Internal Thread Mode** (Debugging/Simple Usage)
2. **External Thread Mode** (Advanced/Production Usage)

Both modes allow you to use all read/set functions normally while housekeeping runs in the background.

## Mode 1: Internal Thread Mode (Debugging)

### Usage
```python
# Simple initialization - no threads passed
chiller = Chiller(device_id="DEBUG_CHILLER", port="COM3")

# Connect and start automatic housekeeping
chiller.connect()
chiller.start_housekeeping(interval=30)  # Automatic thread creation

# Use read/set functions normally - they work alongside housekeeping
temp = chiller.read_temp()
chiller.set_temperature(25.0)

# Stop everything
chiller.stop_housekeeping()
chiller.disconnect()
```

### Behavior
- Chiller automatically creates and manages its own housekeeping thread
- `start_housekeeping()` creates a daemon thread that runs `hk_monitor()` periodically
- Thread is automatically cleaned up when `stop_housekeeping()` is called
- All read/set functions work normally alongside the automatic housekeeping

### Use Cases
- Debugging and testing
- Simple scripts where you want automatic monitoring
- When you don't need fine control over threading

## Mode 2: External Thread Mode (Production)

### Usage
```python
# Initialize with your own thread and lock objects
my_thread = threading.Thread(name="MyChillerThread")
my_lock = threading.Lock()

chiller = Chiller(
    device_id="PROD_CHILLER", 
    port="COM3",
    hk_thread=my_thread,      # Your thread
    thread_lock=my_lock       # Your lock
)

# Connect and enable housekeeping (doesn't start thread automatically)
chiller.connect()
chiller.start_housekeeping(interval=10)  # Just enables monitoring

# Your external thread control
def my_housekeeping_loop():
    while chiller.should_continue_housekeeping():
        chiller.do_housekeeping_cycle()  # Easy single cycle
        time.sleep(chiller.hk_interval)

# Start your external thread
my_thread = threading.Thread(target=my_housekeeping_loop, daemon=True)
my_thread.start()

# Use read/set functions normally - they work with your threading
temp = chiller.read_temp()
chiller.set_temperature(25.0)

# Stop everything
chiller.stop_housekeeping()
my_thread.join()
chiller.disconnect()
```

### Behavior
- You control the thread lifecycle completely
- `start_housekeeping()` just enables monitoring, doesn't create threads
- You call `do_housekeeping_cycle()` when you want monitoring to happen
- `should_continue_housekeeping()` tells you when to stop your loop
- All read/set functions work normally with your threading setup

### Use Cases
- Production environments where you manage threading
- Integration with existing thread pools or async systems
- When you need precise control over when housekeeping happens
- Multi-device scenarios with shared thread management

## Key Methods

### Core Methods (Same for Both Modes)
- `start_housekeeping(interval=30, log_to_file=True)` - Enable housekeeping
- `stop_housekeeping()` - Disable housekeeping  
- All `read_*()` and `set_*()` methods work identically in both modes

### External Thread Helper Methods
- `do_housekeeping_cycle()` - Perform one monitoring cycle (for external threads)
- `should_continue_housekeeping()` - Check if monitoring should continue (for external threads)

### Housekeeping Core (Unchanged)
- `hk_monitor()` - The actual monitoring function (unchanged per your request)

## Thread Safety

### Locks
- `thread_lock` - Protects serial communication (read/write operations)
- `hk_lock` - Protects housekeeping state (internal coordination)

### Safe Concurrent Usage
Both modes support:
- Calling read/set functions while housekeeping is running
- Multiple threads accessing the chiller object (with proper locking)
- Starting/stopping housekeeping from any thread

## Implementation Details

### Automatic Mode Detection
```python
# Detects mode during initialization
self.external_thread = hk_thread is not None
self.external_lock = thread_lock is not None
```

### Thread Creation Strategy
- **Internal mode**: Creates daemon threads automatically
- **External mode**: Uses provided thread objects, no automatic creation

### Resource Management
- **Internal mode**: Automatically joins threads on stop
- **External mode**: You control thread lifecycle

## Migration Guide

### From Old Implementation
If you were using the previous implementation:

```python
# Old way (still works)
chiller = Chiller(device_id="test", port="COM3")
chiller.connect()
chiller.start_housekeeping()

# New way (same result, just clearer)
chiller = Chiller(device_id="test", port="COM3")  # Internal mode automatic
chiller.connect()
chiller.start_housekeeping(interval=30, log_to_file=True)
```

### Adding External Thread Control
```python
# Add thread control to existing code
my_lock = threading.Lock()
chiller = Chiller(
    device_id="test", 
    port="COM3",
    thread_lock=my_lock  # Now you control the locking
)

# Use external thread pattern
def my_monitoring():
    chiller.start_housekeeping()
    while chiller.should_continue_housekeeping():
        chiller.do_housekeeping_cycle()
        time.sleep(chiller.hk_interval)

threading.Thread(target=my_monitoring, daemon=True).start()
```

## Best Practices

### For Internal Mode (Debugging)
- Just use `start_housekeeping()` and `stop_housekeeping()`
- Let the chiller handle everything automatically
- Perfect for quick scripts and debugging

### For External Mode (Production)
- Always check `should_continue_housekeeping()` in your loop
- Use `do_housekeeping_cycle()` for easy monitoring
- Handle thread lifecycle properly with join/cleanup
- Consider your interval timing based on your application needs

### General
- Always call `stop_housekeeping()` before `disconnect()`
- Use `log_to_file=True` for debugging, `False` for production
- All read/set functions are thread-safe in both modes
- Exception handling in your external thread is your responsibility

## Logging

Logging behavior is consistent across both modes:
- File logging can be enabled/disabled with `log_to_file` parameter
- Housekeeping data is logged via `custom_logger()` method
- Thread mode is logged during initialization
- All operations are logged with appropriate levels

## Error Handling

Both modes handle errors gracefully:
- Connection failures are logged and return False
- Serial communication errors are logged
- Thread errors are contained and logged
- External threads should handle their own exceptions in monitoring loops
