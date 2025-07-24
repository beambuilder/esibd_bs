"""
Unit tests for Arduino device class.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import pytest
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from devices.arduino.arduino import Arduino


class TestArduino:
    """Test cases for Arduino device class using pytest."""
    
    def test_arduino_initialization(self):
        """Test Arduino initialization with different parameters."""
        # Test default initialization
        arduino = Arduino("test_arduino", port="COM3")
        
        assert arduino.device_id == "test_arduino"
        assert arduino.port == "COM3"
        assert arduino.baudrate == 9600  # default
        assert arduino.timeout == 1.0  # default
        assert arduino.data_parser == "pump_locker"  # default
        assert arduino.is_connected == False
        assert arduino.serial_connection is None
        
        # Test custom initialization
        arduino_custom = Arduino(
            "custom_arduino", 
            port="COM5", 
            baudrate=115200, 
            timeout=2.0,
            data_parser="trafo_locker"
        )
        
        assert arduino_custom.device_id == "custom_arduino"
        assert arduino_custom.port == "COM5"
        assert arduino_custom.baudrate == 115200
        assert arduino_custom.timeout == 2.0
        assert arduino_custom.data_parser == "trafo_locker"

    def test_get_status(self):
        """Test get_status method returns correct information."""
        arduino = Arduino("status_test", "COM3", baudrate=115200, timeout=2.5)
        
        status = arduino.get_status()
        
        assert isinstance(status, dict)
        assert status["device_id"] == "status_test"
        assert status["port"] == "COM3"
        assert status["baudrate"] == 115200
        assert status["connected"] == False
        assert status["timeout"] == 2.5
        
        # Test status after mock connection
        arduino.is_connected = True
        status_connected = arduino.get_status()
        assert status_connected["connected"] == True

    @patch('devices.arduino.arduino.serial.Serial')
    def test_connect_success(self, mock_serial):
        """Test successful connection to Arduino."""
        arduino = Arduino("connect_test", "COM3")
        
        # Mock successful serial connection
        mock_serial_instance = Mock()
        mock_serial.return_value = mock_serial_instance
        
        result = arduino.connect()
        
        assert result == True
        assert arduino.is_connected == True
        assert arduino.serial_connection == mock_serial_instance
        mock_serial.assert_called_once_with("COM3", 9600, timeout=1.0)

    @patch('devices.arduino.arduino.serial.Serial')
    def test_connect_failure(self, mock_serial):
        """Test connection failure handling."""
        arduino = Arduino("connect_fail_test", "COM3")
        
        # Mock serial connection failure
        mock_serial.side_effect = Exception("Port not found")
        
        result = arduino.connect()
        
        assert result == False
        assert arduino.is_connected == False
        assert arduino.serial_connection is None

    def test_disconnect_success(self):
        """Test successful disconnection."""
        arduino = Arduino("disconnect_test", "COM3")
        
        # Setup mock connection
        mock_serial = Mock()
        arduino.serial_connection = mock_serial
        arduino.is_connected = True
        
        result = arduino.disconnect()
        
        assert result == True
        assert arduino.is_connected == False
        mock_serial.close.assert_called_once()

    def test_disconnect_no_connection(self):
        """Test disconnection when no connection exists."""
        arduino = Arduino("disconnect_none_test", "COM3")
        
        result = arduino.disconnect()
        
        assert result == True
        assert arduino.is_connected == False

    def test_parse_pump_locker_data_valid(self):
        """Test parsing valid pump locker data."""
        arduino = Arduino("parse_test", "COM3", data_parser="pump_locker")
        
        test_data = "Temperature: 23.44 °C | Fan_PWR: 60 % | Waterflow: 15.2 L/min"
        result = arduino.parse_data(test_data)
        
        assert result is not None
        assert result["temperature"] == 23.44
        assert result["fan_power"] == 60
        assert result["waterflow"] == 15.2
        assert result["raw_data"] == test_data

    def test_parse_pump_locker_data_with_spaces(self):
        """Test parsing pump locker data with extra spaces."""
        arduino = Arduino("parse_spaces_test", "COM3", data_parser="pump_locker")
        
        test_data = "Temperature:   25.1   °C  |  Fan_PWR:  75  %  | Waterflow:  12.8  L/min"
        result = arduino.parse_data(test_data)
        
        assert result is not None
        assert result["temperature"] == 25.1
        assert result["fan_power"] == 75
        assert result["waterflow"] == 12.8

    def test_parse_trafo_locker_data_valid(self):
        """Test parsing valid trafo locker data."""
        arduino = Arduino("trafo_test", "COM3", data_parser="trafo_locker")
        
        test_data = "Temperature: 28.5 °C | Fan_PWR: 80 %"
        result = arduino.parse_data(test_data)
        
        assert result is not None
        assert result["temperature"] == 28.5
        assert result["fan_power"] == 80
        assert result["raw_data"] == test_data

    def test_parse_data_invalid_format(self):
        """Test parsing invalid data formats."""
        arduino = Arduino("invalid_test", "COM3", data_parser="pump_locker")
        
        # Test empty string
        assert arduino.parse_data("") is None
        
        # Test random text
        assert arduino.parse_data("Random garbage text") is None
        
        # Test partial data
        assert arduino.parse_data("Temperature: 23.44") is None
        
        # Test malformed numbers
        assert arduino.parse_data("Temperature: abc °C | Fan_PWR: 60 % | Waterflow: 15.2 L/min") is None

    def test_parse_data_unknown_parser(self):
        """Test parsing with unknown parser type."""
        arduino = Arduino("unknown_parser_test", "COM3", data_parser="nonexistent")
        
        test_data = "Some random data"
        result = arduino.parse_data(test_data)
        
        assert result == {"raw_data": test_data}

    def test_parse_custom_data(self):
        """Test custom data parsing."""
        arduino = Arduino("custom_test", "COM3", data_parser="custom")
        
        test_data = "Custom format data"
        result = arduino.parse_data(test_data)
        
        assert result == {"raw_data": test_data}

    def test_readout_not_connected(self):
        """Test readout when Arduino is not connected."""
        arduino = Arduino("readout_test", "COM3")
        
        result = arduino.readout()
        
        assert result is None

    def test_readout_with_data(self):
        """Test readout when data is available."""
        arduino = Arduino("readout_data_test", "COM3")
        
        # Setup mock connection
        mock_serial = Mock()
        mock_serial.in_waiting = 10  # Simulate data available
        mock_serial.readline.return_value = b"Temperature: 23.5 \xc2\xb0C | Fan_PWR: 65 %\r\n"
        
        arduino.serial_connection = mock_serial
        arduino.is_connected = True
        
        result = arduino.readout()
        
        assert result == "Temperature: 23.5 °C | Fan_PWR: 65 %"
        mock_serial.readline.assert_called_once()

    def test_readout_no_data(self):
        """Test readout when no data is available."""
        arduino = Arduino("readout_no_data_test", "COM3")
        
        # Setup mock connection with no data
        mock_serial = Mock()
        mock_serial.in_waiting = 0  # No data available
        
        arduino.serial_connection = mock_serial
        arduino.is_connected = True
        
        result = arduino.readout()
        
        assert result is None

    def test_read_arduino_data_success(self):
        """Test successful read and parse of Arduino data."""
        arduino = Arduino("read_data_test", "COM3", data_parser="pump_locker")
        
        # Setup mock connection
        mock_serial = Mock()
        mock_serial.in_waiting = 10
        mock_serial.readline.return_value = b"Temperature: 22.3 \xc2\xb0C | Fan_PWR: 55 % | Waterflow: 14.1 L/min\r\n"
        
        arduino.serial_connection = mock_serial
        arduino.is_connected = True
        
        result = arduino.read_arduino_data()
        
        assert result is not None
        assert result["temperature"] == 22.3
        assert result["fan_power"] == 55
        assert result["waterflow"] == 14.1

    def test_read_arduino_data_no_data(self):
        """Test read_arduino_data when no data is available."""
        arduino = Arduino("read_no_data_test", "COM3")
        
        # Setup mock connection with no data
        mock_serial = Mock()
        mock_serial.in_waiting = 0
        
        arduino.serial_connection = mock_serial
        arduino.is_connected = True
        
        result = arduino.read_arduino_data()
        
        assert result is None


if __name__ == '__main__':
    # Support both pytest and unittest
    unittest.main()
