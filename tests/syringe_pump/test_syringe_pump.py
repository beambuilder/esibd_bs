"""
Unit tests for SyringePump device class.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
import pytest
import sys
import logging
import threading
import time
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from devices.syringe_pump.syringe_pump import SyringePump


class TestSyringePump:
    """Test cases for SyringePump device class using pytest."""

    def test_syringe_pump_initialization_default(self):
        """Test SyringePump initialization with default parameters."""
        pump = SyringePump("test_pump", port="COM5")

        assert pump.device_id == "test_pump"
        assert pump.port == "COM5"
        assert pump.baudrate == 9600  # default
        assert pump.timeout == 1.0  # default
        assert pump.x == 0  # default
        assert pump.mode == 0  # default
        assert pump.is_connected is False
        assert pump.serial_connection is None

        # Threading attributes
        assert pump.hk_interval == 30.0  # default
        assert pump.hk_running is False
        assert pump.hk_stop_event is not None
        assert pump.external_thread is False
        assert pump.external_lock is False
        assert pump.hk_thread is not None
        assert pump.thread_lock is not None
        assert pump.hk_lock is not None

        # Logger should be created automatically
        assert pump.logger is not None
        assert "SyringePump_test_pump_" in pump.logger.name

    def test_syringe_pump_initialization_custom(self):
        """Test SyringePump initialization with custom parameters."""
        custom_logger = logging.getLogger("test_logger")

        pump = SyringePump(
            "custom_pump",
            port="COM7",
            baudrate=115200,
            timeout=2.0,
            x=1,
            mode=2,
            logger=custom_logger,
            hk_interval=45.0,
        )

        assert pump.device_id == "custom_pump"
        assert pump.port == "COM7"
        assert pump.baudrate == 115200
        assert pump.timeout == 2.0
        assert pump.x == 1
        assert pump.mode == 2
        assert pump.logger == custom_logger
        assert pump.hk_interval == 45.0

    def test_initialization_with_external_thread(self):
        """Test initialization with external thread and lock."""
        external_thread = threading.Thread(name="ExternalThread")
        external_lock = threading.Lock()

        pump = SyringePump(
            "external_test",
            port="COM5",
            hk_thread=external_thread,
            thread_lock=external_lock,
        )

        assert pump.external_thread is True
        assert pump.external_lock is True
        assert pump.hk_thread == external_thread
        assert pump.thread_lock == external_lock

    @patch("serial.Serial")
    def test_connect_success(self, mock_serial):
        """Test successful connection to syringe pump."""
        pump = SyringePump("connect_test", "COM5")

        # Setup mock
        mock_serial_instance = Mock()
        mock_serial_instance.is_open = True
        mock_serial.return_value = mock_serial_instance

        result = pump.connect()

        assert result is True
        assert pump.is_connected is True
        assert pump.serial_connection == mock_serial_instance
        mock_serial.assert_called_once_with(port="COM5", baudrate=9600, timeout=1.0)

    @patch("serial.Serial")
    def test_connect_failure(self, mock_serial):
        """Test failed connection to syringe pump."""
        pump = SyringePump("connect_fail_test", "COM5")

        # Setup mock to raise exception
        mock_serial.side_effect = Exception("Port not available")

        result = pump.connect()

        assert result is False
        assert pump.is_connected is False
        assert pump.serial_connection is None

    def test_disconnect_success(self):
        """Test successful disconnection from syringe pump."""
        pump = SyringePump("disconnect_test", "COM5")

        # Setup mock connection
        mock_serial = Mock()
        mock_serial.is_open = True
        pump.serial_connection = mock_serial
        pump.is_connected = True

        result = pump.disconnect()

        assert result is True
        assert pump.is_connected is False
        mock_serial.close.assert_called_once()

    def test_disconnect_no_connection(self):
        """Test disconnection when no connection exists."""
        pump = SyringePump("disconnect_none_test", "COM5")

        result = pump.disconnect()

        assert result is False
        assert pump.is_connected is False

    def test_add_mode_no_mode(self):
        """Test _add_mode when mode is 0 (no mode suffix)."""
        pump = SyringePump("mode_test", "COM5", mode=0)

        command = "start"
        result = pump._add_mode(command)

        assert result == "start"

    def test_add_mode_with_mode(self):
        """Test _add_mode when mode is set."""
        pump = SyringePump("mode_test", "COM5", mode=2)

        command = "start"
        result = pump._add_mode(command)

        assert result == "start 1"  # mode 2 -> suffix 1

    def test_add_x_no_prefix(self):
        """Test _add_x when x is 0 (no prefix)."""
        pump = SyringePump("x_test", "COM5", x=0)

        command = "start"
        result = pump._add_x(command)

        assert result == "start"

    def test_add_x_with_prefix(self):
        """Test _add_x when x is set."""
        pump = SyringePump("x_test", "COM5", x=2)

        command = "start"
        result = pump._add_x(command)

        assert result == "2 start"

    def test_send_command_not_connected(self):
        """Test _send_command when pump is not connected."""
        pump = SyringePump("send_test", "COM5")

        result = pump._send_command("start")

        assert result == []

    @patch("time.sleep")
    def test_send_command_success(self, mock_sleep):
        """Test _send_command successful execution."""
        pump = SyringePump("send_success_test", "COM5")

        # Setup mock connection
        mock_serial = Mock()
        mock_serial.write = Mock()
        mock_serial.readlines = Mock(return_value=[b"OK\r\n"])

        pump.serial_connection = mock_serial
        pump.is_connected = True

        result = pump._send_command("start")

        assert result == ["OK"]
        mock_serial.write.assert_called_once_with(b"start\r")
        mock_sleep.assert_called_once_with(0.05)

    def test_get_response_success(self):
        """Test _get_response with valid data."""
        pump = SyringePump("response_test", "COM5")

        # Setup mock connection
        mock_serial = Mock()
        mock_serial.readlines = Mock(
            return_value=[b"Line 1\r\n", b"Line 2\r\n", b"\r\n", b"Line 3\r\n"]
        )

        pump.serial_connection = mock_serial

        result = pump._get_response()

        assert result == ["Line 1", "Line 2", "Line 3"]

    def test_get_response_error(self):
        """Test _get_response with exception."""
        pump = SyringePump("response_error_test", "COM5")

        # Setup mock connection to raise exception
        mock_serial = Mock()
        mock_serial.readlines = Mock(side_effect=Exception("Read error"))

        pump.serial_connection = mock_serial

        result = pump._get_response()

        assert result == []

    def test_start_pump_no_x_no_mode(self):
        """Test start_pump command construction without x and mode."""
        pump = SyringePump("start_test", "COM5", x=0, mode=0)

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.start_pump()

            mock_send.assert_called_once_with("start")
            assert result == ["OK"]

    def test_start_pump_with_x_and_mode(self):
        """Test start_pump command construction with x and mode."""
        pump = SyringePump("start_test", "COM5", x=2, mode=3)

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.start_pump()

            mock_send.assert_called_once_with("2 start 2")
            assert result == ["OK"]

    def test_stop_pump(self):
        """Test stop_pump command."""
        pump = SyringePump("stop_test", "COM5", x=1)

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.stop_pump()

            mock_send.assert_called_once_with("1 stop")
            assert result == ["OK"]

    def test_pause_pump(self):
        """Test pause_pump command."""
        pump = SyringePump("pause_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.pause_pump()

            mock_send.assert_called_once_with("pause")
            assert result == ["OK"]

    def test_restart_pump(self):
        """Test restart_pump command."""
        pump = SyringePump("restart_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.restart_pump()

            mock_send.assert_called_once_with("restart")
            assert result == ["OK"]

    def test_set_units_valid(self):
        """Test set_units with valid units."""
        pump = SyringePump("units_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.set_units("mL/min")
            mock_send.assert_called_with("set units 0")
            assert result == ["OK"]

            result = pump.set_units("mL/hr")
            mock_send.assert_called_with("set units 1")

            result = pump.set_units("μL/min")
            mock_send.assert_called_with("set units 2")

            result = pump.set_units("μL/hr")
            mock_send.assert_called_with("set units 3")

    def test_set_units_invalid(self):
        """Test set_units with invalid units."""
        pump = SyringePump("units_invalid_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command") as mock_send:
            result = pump.set_units("invalid_unit")

            mock_send.assert_not_called()
            assert result == []

    def test_set_diameter(self):
        """Test set_diameter command."""
        pump = SyringePump("diameter_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.set_diameter(10.5)

            mock_send.assert_called_once_with("set diameter 10.5")
            assert result == ["OK"]

    def test_set_rate_single_value(self):
        """Test set_rate with single value."""
        pump = SyringePump("rate_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.set_rate(5.0)

            mock_send.assert_called_once_with("set rate 5.0")
            assert result == ["OK"]

    def test_set_rate_multiple_values(self):
        """Test set_rate with multiple values (multi-step)."""
        pump = SyringePump("rate_multi_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.set_rate([1.0, 2.0, 3.0])

            mock_send.assert_called_once_with("set rate 1.0,2.0,3.0")
            assert result == ["OK"]

    def test_set_volume_single_value(self):
        """Test set_volume with single value."""
        pump = SyringePump("volume_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.set_volume(10.0)

            mock_send.assert_called_once_with("set volume 10.0")
            assert result == ["OK"]

    def test_set_volume_multiple_values(self):
        """Test set_volume with multiple values (multi-step)."""
        pump = SyringePump("volume_multi_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.set_volume([5.0, 10.0, 15.0])

            mock_send.assert_called_once_with("set volume 5.0,10.0,15.0")
            assert result == ["OK"]

    def test_set_delay_single_value(self):
        """Test set_delay with single value."""
        pump = SyringePump("delay_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.set_delay(2.0)

            mock_send.assert_called_once_with("set delay 2.0")
            assert result == ["OK"]

    def test_set_delay_multiple_values(self):
        """Test set_delay with multiple values (multi-step)."""
        pump = SyringePump("delay_multi_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.set_delay([1.0, 2.0, 3.0])

            mock_send.assert_called_once_with("set delay 1.0,2.0,3.0")
            assert result == ["OK"]

    def test_set_time(self):
        """Test set_time command."""
        pump = SyringePump("time_test", "COM5")

        # Mock _send_command
        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            result = pump.set_time(30.0)

            mock_send.assert_called_once_with("set time 30.0")
            assert result == ["OK"]

    def test_get_parameter_limits(self):
        """Test get_parameter_limits command."""
        pump = SyringePump("limits_test", "COM5")

        # Mock _send_command
        with patch.object(
            pump, "_send_command", return_value=["Limits: ..."]
        ) as mock_send:
            result = pump.get_parameter_limits()

            mock_send.assert_called_once_with("read limit parameter")
            assert result == ["Limits: ..."]

    def test_get_parameters(self):
        """Test get_parameters command."""
        pump = SyringePump("params_test", "COM5")

        # Mock _send_command
        with patch.object(
            pump, "_send_command", return_value=["Params: ..."]
        ) as mock_send:
            result = pump.get_parameters()

            mock_send.assert_called_once_with("view parameter")
            assert result == ["Params: ..."]

    def test_get_displaced_volume(self):
        """Test get_displaced_volume command."""
        pump = SyringePump("displaced_test", "COM5")

        # Mock _send_command
        with patch.object(
            pump, "_send_command", return_value=["10.5 mL"]
        ) as mock_send:
            result = pump.get_displaced_volume()

            mock_send.assert_called_once_with("dispensed volume")
            assert result == ["10.5 mL"]

    def test_get_elapsed_time(self):
        """Test get_elapsed_time command."""
        pump = SyringePump("elapsed_test", "COM5")

        # Mock _send_command
        with patch.object(
            pump, "_send_command", return_value=["120 seconds"]
        ) as mock_send:
            result = pump.get_elapsed_time()

            mock_send.assert_called_once_with("elapsed time")
            assert result == ["120 seconds"]

    def test_get_pump_status(self):
        """Test get_pump_status command."""
        pump = SyringePump("status_test", "COM5")

        # Mock _send_command
        with patch.object(
            pump, "_send_command", return_value=["Status: Running"]
        ) as mock_send:
            result = pump.get_pump_status()

            mock_send.assert_called_once_with("pump status")
            assert result == ["Status: Running"]

    @patch("serial.Serial")
    @patch("glob.glob")
    @patch("sys.platform", "win32")
    def test_get_available_ports_windows(self, mock_glob, mock_serial):
        """Test get_available_ports on Windows."""
        # Mock serial.Serial to succeed for COM1, COM3 and fail for others
        def serial_side_effect(port):
            if port in ["COM1", "COM3"]:
                mock_obj = Mock()
                return mock_obj
            else:
                raise OSError("Port not available")

        mock_serial.side_effect = serial_side_effect

        ports = SyringePump.get_available_ports()

        assert "COM1" in ports
        assert "COM3" in ports
        assert len(ports) == 2

    @patch("serial.Serial")
    @patch("glob.glob")
    @patch("sys.platform", "linux")
    def test_get_available_ports_linux(self, mock_glob, mock_serial):
        """Test get_available_ports on Linux."""
        mock_glob.return_value = ["/dev/ttyUSB0", "/dev/ttyUSB1"]

        # Mock serial.Serial to succeed for both
        mock_serial.return_value = Mock()

        ports = SyringePump.get_available_ports()

        assert "/dev/ttyUSB0" in ports
        assert "/dev/ttyUSB1" in ports

    def test_flush_buffers(self):
        """Test _flush_buffers method."""
        pump = SyringePump("flush_test", "COM5")

        # Setup mock connection
        mock_serial = Mock()
        mock_serial.is_open = True
        pump.serial_connection = mock_serial

        pump._flush_buffers()

        mock_serial.flushInput.assert_called_once()
        mock_serial.flushOutput.assert_called_once()

    def test_flush_buffers_no_connection(self):
        """Test _flush_buffers when no connection exists."""
        pump = SyringePump("flush_none_test", "COM5")

        # Should not raise exception
        pump._flush_buffers()


class TestSyringePumpIntegration:
    """Integration tests for SyringePump combining multiple methods."""

    def test_typical_workflow(self):
        """Test a typical pump workflow sequence."""
        pump = SyringePump("workflow_test", "COM5")

        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            # Set up pump
            pump.set_units("mL/min")
            pump.set_diameter(10.0)
            pump.set_rate(5.0)
            pump.set_volume(10.0)

            # Start pump
            pump.start_pump()

            # Check status
            pump.get_pump_status()

            # Stop pump
            pump.stop_pump()

            # Verify command sequence
            assert mock_send.call_count == 7

    @patch("serial.Serial")
    def test_connection_lifecycle(self, mock_serial):
        """Test complete connection lifecycle."""
        pump = SyringePump("lifecycle_test", "COM5")

        # Setup mock
        mock_serial_instance = Mock()
        mock_serial_instance.is_open = True
        mock_serial.return_value = mock_serial_instance

        # Connect
        assert pump.connect() is True
        assert pump.is_connected is True

        # Disconnect
        assert pump.disconnect() is True
        assert pump.is_connected is False

    def test_multi_step_operations(self):
        """Test multi-step pump operations."""
        pump = SyringePump("multistep_test", "COM5")

        with patch.object(pump, "_send_command", return_value=["OK"]) as mock_send:
            # Configure multi-step operation
            pump.set_rate([1.0, 2.0, 3.0])
            pump.set_volume([5.0, 10.0, 15.0])
            pump.set_delay([0.5, 1.0, 1.5])

            # Verify commands
            calls = mock_send.call_args_list
            assert calls[0][0][0] == "set rate 1.0,2.0,3.0"
            assert calls[1][0][0] == "set volume 5.0,10.0,15.0"
            assert calls[2][0][0] == "set delay 0.5,1.0,1.5"


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
