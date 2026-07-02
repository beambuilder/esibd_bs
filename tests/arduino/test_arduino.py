"""
Unit tests for the Arduino device classes (base + pump/trafo lockers).
"""

import unittest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from devices.arduino.arduino import Arduino
from devices.arduino.pump_arduino import PumpArduino
from devices.arduino.trafo_arduino import TrafoArduino


class TestArduino:
    """Test cases for the Arduino classes using pytest."""

    def test_arduino_initialization(self):
        """Test Arduino initialization with different parameters."""
        # Test default initialization
        arduino = PumpArduino("test_arduino", port="COM3")

        assert arduino.device_id == "test_arduino"
        assert arduino.port == "COM3"
        assert arduino.baudrate == 9600  # default
        assert arduino.timeout == 1.0  # default
        assert arduino.hk_interval == 1.0  # default
        assert arduino.is_connected == False
        assert arduino.serial_connection is None
        assert arduino.test_mode == False
        assert arduino.sink is None

        # Test custom initialization
        arduino_custom = TrafoArduino(
            "custom_arduino",
            port="COM5",
            baudrate=115200,
            timeout=2.0,
        )

        assert arduino_custom.device_id == "custom_arduino"
        assert arduino_custom.port == "COM5"
        assert arduino_custom.baudrate == 115200
        assert arduino_custom.timeout == 2.0

    def test_get_status(self):
        """Test get_status method returns correct information."""
        arduino = PumpArduino("status_test", "COM3", baudrate=115200, timeout=2.5)

        status = arduino.get_status()

        assert isinstance(status, dict)
        assert status["device_id"] == "status_test"
        assert status["port"] == "COM3"
        assert status["baudrate"] == 115200
        assert status["connected"] == False
        assert status["timeout"] == 2.5
        assert status["test_mode"] == False

        # Test status after mock connection
        arduino.is_connected = True
        status_connected = arduino.get_status()
        assert status_connected["connected"] == True

    @patch('devices.serial_device.serial.Serial')
    def test_connect_success(self, mock_serial):
        """Test successful connection to Arduino."""
        arduino = PumpArduino("connect_test", "COM3")

        # Mock successful serial connection
        mock_serial_instance = Mock()
        mock_serial.return_value = mock_serial_instance

        result = arduino.connect()

        assert result == True
        assert arduino.is_connected == True
        assert arduino.serial_connection == mock_serial_instance
        mock_serial.assert_called_once_with("COM3", 9600, timeout=1.0)

    @patch('devices.serial_device.serial.Serial')
    def test_connect_failure(self, mock_serial):
        """Test connection failure handling."""
        arduino = PumpArduino("connect_fail_test", "COM3")

        # Mock serial connection failure
        mock_serial.side_effect = Exception("Port not found")

        result = arduino.connect()

        assert result == False
        assert arduino.is_connected == False
        assert arduino.serial_connection is None

    def test_disconnect_success(self):
        """Test successful disconnection."""
        arduino = PumpArduino("disconnect_test", "COM3")

        # Setup mock connection
        mock_serial = Mock()
        arduino.serial_connection = mock_serial
        arduino.is_connected = True

        result = arduino.disconnect()

        assert result == True
        assert arduino.is_connected == False
        mock_serial.close.assert_called_once()

    def test_disconnect_no_connection(self):
        """Test disconnection when no connection exists (idempotent)."""
        arduino = PumpArduino("disconnect_none_test", "COM3")

        result = arduino.disconnect()

        assert result == True
        assert arduino.is_connected == False

    def test_parse_pump_locker_data_valid(self):
        """Test parsing a valid pump-locker CSV line."""
        arduino = PumpArduino("parse_test", "COM3")

        result = arduino.parse_data("18.69,35,3.10,0.00")

        assert result is not None
        assert result["temperature"] == 18.69
        assert result["fan_power"] == 35
        assert result["flow_rate_1"] == 3.10
        assert result["flow_rate_2"] == 0.00
        assert result["raw_data"] == "18.69,35,3.10,0.00"

    def test_parse_pump_locker_data_with_spaces(self):
        """Test parsing pump-locker CSV with extra spaces."""
        arduino = PumpArduino("parse_spaces_test", "COM3")

        result = arduino.parse_data(" 25.1 , 75 , 12.8 , 1.5 ")

        assert result is not None
        assert result["temperature"] == 25.1
        assert result["fan_power"] == 75
        assert result["flow_rate_1"] == 12.8
        assert result["flow_rate_2"] == 1.5

    def test_parse_trafo_locker_data_valid(self):
        """Test parsing a valid trafo-locker CSV line."""
        arduino = TrafoArduino("trafo_test", "COM3")

        result = arduino.parse_data("28.5,80")

        assert result is not None
        assert result["temperature"] == 28.5
        assert result["fan_power"] == 80
        assert result["raw_data"] == "28.5,80"

    def test_parse_data_invalid_format(self):
        """Test parsing invalid data formats (incl. periodic CSV headers)."""
        pump = PumpArduino("invalid_test", "COM3")
        trafo = TrafoArduino("invalid_trafo_test", "COM3")

        # Empty string
        assert pump.parse_data("") is None

        # CSV header line printed by the firmware every 20 lines
        assert pump.parse_data("Temp,Fan,Flow1,Flow2") is None
        assert trafo.parse_data("Temp,Fan") is None

        # Wrong field count
        assert pump.parse_data("18.69,35") is None
        assert trafo.parse_data("18.69,35,1.0,2.0") is None

        # Malformed numbers
        assert pump.parse_data("abc,35,0.0,0.0") is None

    def test_readout_not_connected(self):
        """Test readout when Arduino is not connected."""
        arduino = PumpArduino("readout_test", "COM3")

        result = arduino.readout()

        assert result is None

    def test_readout_with_data(self):
        """Test readout when data is available."""
        arduino = PumpArduino("readout_data_test", "COM3")

        # Setup mock connection
        mock_serial = Mock()
        mock_serial.in_waiting = 10  # Simulate data available
        mock_serial.readline.return_value = b"18.69,35,0.00,0.00\r\n"

        arduino.serial_connection = mock_serial
        arduino.is_connected = True

        result = arduino.readout()

        assert result == "18.69,35,0.00,0.00"
        mock_serial.readline.assert_called_once()

    def test_readout_no_data(self):
        """Test readout when no data is available."""
        arduino = PumpArduino("readout_no_data_test", "COM3")

        # Setup mock connection with no data
        mock_serial = Mock()
        mock_serial.in_waiting = 0  # No data available

        arduino.serial_connection = mock_serial
        arduino.is_connected = True

        result = arduino.readout()

        assert result is None

    def test_read_arduino_data_success(self):
        """Test successful read and parse of Arduino data."""
        arduino = PumpArduino("read_data_test", "COM3")

        # Setup mock connection
        mock_serial = Mock()
        mock_serial.in_waiting = 10
        mock_serial.readline.return_value = b"22.3,55,14.1,0.5\r\n"

        arduino.serial_connection = mock_serial
        arduino.is_connected = True

        result = arduino.read_arduino_data()

        assert result is not None
        assert result["temperature"] == 22.3
        assert result["fan_power"] == 55
        assert result["flow_rate_1"] == 14.1
        assert result["flow_rate_2"] == 0.5

    def test_read_arduino_data_no_data(self):
        """Test read_arduino_data when no data is available."""
        arduino = PumpArduino("read_no_data_test", "COM3")

        # Setup mock connection with no data
        mock_serial = Mock()
        mock_serial.in_waiting = 0

        arduino.serial_connection = mock_serial
        arduino.is_connected = True

        result = arduino.read_arduino_data()

        assert result is None

    def test_read_arduino_data_test_mode(self):
        """Test that test mode yields simulated data without hardware."""
        pump = PumpArduino("sim_pump", "COM3", test_mode=True)
        trafo = TrafoArduino("sim_trafo", "COM4", test_mode=True)

        assert pump.connect() is True
        assert trafo.connect() is True

        pump_data = pump.read_arduino_data()
        assert set(pump_data) == {
            "temperature", "fan_power", "flow_rate_1", "flow_rate_2", "raw_data"
        }
        assert 18.0 <= pump_data["temperature"] <= 22.0

        trafo_data = trafo.read_arduino_data()
        assert set(trafo_data) == {"temperature", "fan_power", "raw_data"}
        assert 18.0 <= trafo_data["temperature"] <= 24.0


if __name__ == '__main__':
    # Support both pytest and unittest
    unittest.main()
