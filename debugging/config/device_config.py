# Device Configuration for Testing and Debugging

# Arduino Configuration
arduino_config = {
    "device_id": "arduino_01",
    "port": "COM3",  # Update to match your system
    "baudrate": 9600,
    "timeout": 2.0
}

# Chiller Configuration
chiller_config = {
    "device_id": "chiller_01",
    "communication_type": "serial",
    "port": "COM4",  # Update to match your system
    "baudrate": 9600,
    "timeout": 5.0
}

# Logging Configuration
logging_config = {
    "level": "DEBUG",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "log_to_file": True,
    "log_to_console": True
}
