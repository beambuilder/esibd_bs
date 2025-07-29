"""
Unit tests for Chiller device class.
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

from devices.chiller.chiller import Chiller, ChillerCommands


class TestChiller:
    """Test cases for Chiller device class using pytest."""
    
    def test_chiller_initialization_default(self):
        """Test Chiller initialization with default parameters."""
        chiller = Chiller("test_chiller", port="COM3")
        
        assert chiller.device_id == "test_chiller"
        assert chiller.port == "COM3"
        assert chiller.baudrate == 9600  # default
        assert chiller.timeout == 1.0  # default
        assert chiller.is_connected == False
        assert chiller.serial_connection is None
        assert chiller.current_temperature is None
        assert chiller.target_temperature is None
        assert chiller.is_cooling == False
        
        # Threading attributes
        assert chiller.hk_interval == 30.0  # default
        assert chiller.hk_running == False
        assert chiller.hk_stop_event is not None
        assert chiller.external_thread == False
        assert chiller.external_lock == False
        assert chiller.hk_thread is not None
        assert chiller.thread_lock is not None
        assert chiller.hk_lock is not None
        
        # Logger should be created automatically
        assert chiller.logger is not None
        assert "Chiller_test_chiller_" in chiller.logger.name

    def test_chiller_initialization_custom(self):
        """Test Chiller initialization with custom parameters."""
        custom_logger = logging.getLogger("test_logger")
        
        chiller = Chiller(
            "custom_chiller", 
            port="COM5", 
            baudrate=115200, 
            timeout=2.0,
            logger=custom_logger,
            hk_interval=45.0
        )
        
        assert chiller.device_id == "custom_chiller"
        assert chiller.port == "COM5"
        assert chiller.baudrate == 115200
        assert chiller.timeout == 2.0
        assert chiller.logger == custom_logger
        assert chiller.hk_interval == 45.0
        
        assert chiller.device_id == "custom_chiller"
        assert chiller.port == "COM5"
        assert chiller.baudrate == 115200
        assert chiller.timeout == 2.0
        assert chiller.logger == custom_logger

    def test_get_status(self):
        """Test get_status method returns correct information."""
        chiller = Chiller("status_test", "COM3", baudrate=115200, timeout=2.5, hk_interval=20.0)
        
        status = chiller.get_status()
        
        assert isinstance(status, dict)
        assert status["device_id"] == "status_test"
        assert status["port"] == "COM3"
        assert status["baudrate"] == 115200
        assert status["connected"] == False
        assert status["timeout"] == 2.5
        assert status["current_temperature"] is None
        assert status["target_temperature"] is None
        assert status["is_cooling"] == False
        assert status["housekeeping_running"] == False
        assert status["housekeeping_interval"] == 20.0
        assert "thread_name" in status
        
        # Test status after mock connection and housekeeping
        chiller.is_connected = True
        chiller.current_temperature = 22.5
        chiller.target_temperature = 20.0
        chiller.is_cooling = True
        chiller.hk_running = True
        
        status_connected = chiller.get_status()
        assert status_connected["connected"] == True
        assert status_connected["current_temperature"] == 22.5
        assert status_connected["target_temperature"] == 20.0
        assert status_connected["is_cooling"] == True
        assert status_connected["housekeeping_running"] == True

    @patch('devices.chiller.chiller.serial.Serial')
    def test_connect_success(self, mock_serial):
        """Test successful connection to Chiller."""
        chiller = Chiller("connect_test", "COM3")
        
        # Mock successful serial connection
        mock_serial_instance = Mock()
        mock_serial.return_value = mock_serial_instance
        
        result = chiller.connect()
        
        assert result == True
        assert chiller.is_connected == True
        assert chiller.serial_connection == mock_serial_instance
        mock_serial.assert_called_once_with("COM3", 9600, timeout=1.0)

    @patch('devices.chiller.chiller.serial.Serial')
    def test_connect_failure(self, mock_serial):
        """Test connection failure handling."""
        chiller = Chiller("connect_fail_test", "COM3")
        
        # Mock serial connection failure
        mock_serial.side_effect = Exception("Port not found")
        
        result = chiller.connect()
        
        assert result == False
        assert chiller.is_connected == False
        assert chiller.serial_connection is None

    def test_disconnect_success(self):
        """Test successful disconnection."""
        chiller = Chiller("disconnect_test", "COM3")
        
        # Setup mock connection
        mock_serial = Mock()
        chiller.serial_connection = mock_serial
        chiller.is_connected = True
        
        result = chiller.disconnect()
        
        assert result == True
        assert chiller.is_connected == False
        mock_serial.close.assert_called_once()

    def test_disconnect_no_connection(self):
        """Test disconnection when no connection exists."""
        chiller = Chiller("disconnect_none_test", "COM3")
        
        result = chiller.disconnect()
        
        assert result == True
        assert chiller.is_connected == False

    def test_read_dev_success(self):
        """Test successful device read operation."""
        chiller = Chiller("read_test", "COM3")
        
        # Setup mock connection
        mock_serial = Mock()
        mock_serial.readline.return_value = b"23.5\r\n"
        chiller.serial_connection = mock_serial
        chiller.is_connected = True
        
        result = chiller.read_dev("TEST_COMMAND\r\n")
        
        assert result == "23.5"
        mock_serial.write.assert_called_once_with(b"TEST_COMMAND\r\n")
        mock_serial.readline.assert_called_once()

    def test_read_dev_not_connected(self):
        """Test read_dev when not connected."""
        chiller = Chiller("read_not_connected_test", "COM3")
        
        with pytest.raises(Exception):
            chiller.read_dev("TEST_COMMAND\r\n")

    def test_set_param_success(self):
        """Test successful parameter setting."""
        chiller = Chiller("set_param_test", "COM3")
        
        # Setup mock connection
        mock_serial = Mock()
        mock_serial.readline.return_value = b"OK\r\n"
        chiller.serial_connection = mock_serial
        chiller.is_connected = True
        
        chiller.set_param("OUT_SP_00 020")
        
        mock_serial.write.assert_called_once_with(b"OUT_SP_00 020\r\n")

    def test_set_param_failure(self):
        """Test parameter setting failure."""
        chiller = Chiller("set_param_fail_test", "COM3")
        
        # Setup mock connection that returns non-OK response
        mock_serial = Mock()
        mock_serial.readline.return_value = b"ERROR\r\n"
        chiller.serial_connection = mock_serial
        chiller.is_connected = True
        
        with pytest.raises(Exception, match="Failed to set parameter"):
            chiller.set_param("OUT_SP_00 020")

    def test_set_param_not_connected(self):
        """Test set_param when not connected."""
        chiller = Chiller("set_param_not_connected_test", "COM3")
        
        with pytest.raises(Exception):
            chiller.set_param("OUT_SP_00 020")

    def test_read_temp(self):
        """Test reading temperature."""
        chiller = Chiller("read_temp_test", "COM3")
        
        # Mock the read_dev method
        with patch.object(chiller, 'read_dev') as mock_read_dev:
            mock_read_dev.return_value = "23.45"
            
            result = chiller.read_temp()
            
            assert result == 23.45
            mock_read_dev.assert_called_once_with(ChillerCommands.READ_TEMP)

    def test_read_set_temp(self):
        """Test reading set temperature."""
        chiller = Chiller("read_set_temp_test", "COM3")
        
        with patch.object(chiller, 'read_dev') as mock_read_dev:
            mock_read_dev.return_value = "20.00"
            
            result = chiller.read_set_temp()
            
            assert result == 20.00
            mock_read_dev.assert_called_once_with(ChillerCommands.READ_SET_TEMP)

    def test_read_pump_level(self):
        """Test reading pump level."""
        chiller = Chiller("read_pump_test", "COM3")
        
        with patch.object(chiller, 'read_dev') as mock_read_dev:
            mock_read_dev.return_value = "003"
            
            result = chiller.read_pump_level()
            
            assert result == 3
            mock_read_dev.assert_called_once_with(ChillerCommands.READ_PUMP_LEVEL)

    def test_read_cooling(self):
        """Test reading cooling mode."""
        chiller = Chiller("read_cooling_test", "COM3")
        
        with patch.object(chiller, 'read_dev') as mock_read_dev:
            mock_read_dev.return_value = "1"  # Returns numeric string
            
            result = chiller.read_cooling()
            
            assert result == "ON"  # 1 maps to "ON"
            mock_read_dev.assert_called_once_with(ChillerCommands.READ_COOLING_MODE)

    def test_read_keylock(self):
        """Test reading keylock status."""
        chiller = Chiller("read_keylock_test", "COM3")
        
        with patch.object(chiller, 'read_dev') as mock_read_dev:
            mock_read_dev.return_value = "1"  # Returns numeric string
            
            result = chiller.read_keylock()
            
            assert result == "LOCKED"  # 1 maps to "LOCKED"
            mock_read_dev.assert_called_once_with(ChillerCommands.READ_KEYLOCK)

    def test_read_running(self):
        """Test reading running status."""
        chiller = Chiller("read_running_test", "COM3")
        
        with patch.object(chiller, 'read_dev') as mock_read_dev:
            mock_read_dev.return_value = "0"  # Returns numeric string
            
            result = chiller.read_running()
            
            assert result == "DEVICE RUNNING"  # 0 maps to "DEVICE RUNNING"
            mock_read_dev.assert_called_once_with(ChillerCommands.READ_RUNNING_STATE)

    def test_read_status(self):
        """Test reading device status."""
        chiller = Chiller("read_status_test", "COM3")
        
        with patch.object(chiller, 'read_dev') as mock_read_dev:
            mock_read_dev.return_value = "0"  # Returns numeric string
            
            result = chiller.read_status()
            
            assert result == "OK"  # 0 maps to "OK"
            mock_read_dev.assert_called_once_with(ChillerCommands.READ_STATUS)

    def test_read_stat_diagnose(self):
        """Test reading diagnostics."""
        chiller = Chiller("read_diagnostics_test", "COM3")
        
        with patch.object(chiller, 'read_dev') as mock_read_dev:
            mock_read_dev.return_value = "NO_ERROR"
            
            result = chiller.read_stat_diagnose()
            
            assert result == "NO_ERROR"
            mock_read_dev.assert_called_once_with(ChillerCommands.READ_DIAGNOSTICS)

    def test_set_temperature(self):
        """Test setting temperature."""
        chiller = Chiller("set_temp_test", "COM3")
        
        with patch.object(chiller, 'set_param') as mock_set_param:
            chiller.set_temperature(25.5)
            
            expected_command = f"{ChillerCommands.SET_TEMP} 025.50"
            mock_set_param.assert_called_once_with(expected_command)

    def test_set_pump_level_valid(self):
        """Test setting valid pump levels."""
        chiller = Chiller("set_pump_valid_test", "COM3")
        
        with patch.object(chiller, 'set_param') as mock_set_param:
            # Test all valid levels
            for level in range(1, 7):
                chiller.set_pump_level(level)
                expected_command = f"{ChillerCommands.SET_PUMP_LEVEL} {level:03d}"
                mock_set_param.assert_called_with(expected_command)

    def test_set_pump_level_invalid(self):
        """Test setting invalid pump levels."""
        chiller = Chiller("set_pump_invalid_test", "COM3")
        
        invalid_levels = [0, 7, -1, 10]  # Removed 'invalid' string
        
        for level in invalid_levels:
            with pytest.raises(ValueError, match="Pump level must be between 1 and 6"):
                chiller.set_pump_level(level)
        
        # Test string input separately
        with pytest.raises(TypeError):
            chiller.set_pump_level('invalid')

    def test_set_keylock(self):
        """Test setting keylock state."""
        chiller = Chiller("set_keylock_test", "COM3")
        
        with patch.object(chiller, 'set_param') as mock_set_param:
            # Test locking
            chiller.set_keylock(True)
            expected_command = f"{ChillerCommands.SET_KEYLOCK} 1"  # int(True) = 1
            mock_set_param.assert_called_with(expected_command)
            
            # Test unlocking
            chiller.set_keylock(False)
            expected_command = f"{ChillerCommands.SET_KEYLOCK} 0"  # int(False) = 0
            mock_set_param.assert_called_with(expected_command)

    def test_start_device(self):
        """Test starting device."""
        chiller = Chiller("start_test", "COM3")
        
        with patch.object(chiller, 'set_param') as mock_set_param:
            chiller.start_device()
            mock_set_param.assert_called_once_with(ChillerCommands.START_DEVICE)

    def test_stop_device(self):
        """Test stopping device."""
        chiller = Chiller("stop_test", "COM3")
        
        with patch.object(chiller, 'set_param') as mock_set_param:
            chiller.stop_device()
            mock_set_param.assert_called_once_with(ChillerCommands.STOP_DEVICE)

    def test_custom_logger(self):
        """Test custom logger function."""
        chiller = Chiller("logger_test", "COM3")
        
        # Mock the logger
        with patch.object(chiller.logger, 'info') as mock_info:
            chiller.custom_logger("test_device", "COM3", "temperature", 25.5, "degC")
            mock_info.assert_called_once_with("test_device   COM3   temperature   25.5//degC")


class TestChillerCommands:
    """Test ChillerCommands constants."""
    
    def test_read_commands(self):
        """Test all read command constants."""
        assert ChillerCommands.READ_TEMP == "IN_PV_00\r\n"
        assert ChillerCommands.READ_SET_TEMP == "IN_SP_00\r\n"
        assert ChillerCommands.READ_PUMP_LEVEL == "IN_SP_01\r\n"
        assert ChillerCommands.READ_COOLING_MODE == "IN_SP_02\r\n"
        assert ChillerCommands.READ_KEYLOCK == "IN_MODE_00\r\n"
        assert ChillerCommands.READ_RUNNING_STATE == "IN_MODE_02\r\n"
        assert ChillerCommands.READ_STATUS == "STATUS\r\n"
        assert ChillerCommands.READ_DIAGNOSTICS == "STAT\r\n"
    
    def test_write_commands(self):
        """Test all write command constants."""
        assert ChillerCommands.SET_TEMP == "OUT_SP_00"
        assert ChillerCommands.SET_PUMP_LEVEL == "OUT_SP_01"
        assert ChillerCommands.SET_KEYLOCK == "OUT_MODE_00"
        assert ChillerCommands.START_DEVICE == "START"
        assert ChillerCommands.STOP_DEVICE == "STOP"


class TestChillerIntegration:
    """Integration tests for Chiller class combining multiple operations."""
    
    @patch('devices.chiller.chiller.serial.Serial')
    def test_full_operation_cycle(self, mock_serial):
        """Test a complete operation cycle: connect, read, write, disconnect."""
        chiller = Chiller("integration_test", "COM3")
        
        # Mock serial connection
        mock_serial_instance = Mock()
        mock_serial.return_value = mock_serial_instance
        mock_serial_instance.readline.side_effect = [b"25.0\r\n", b"20.0\r\n"]
        
        # Connect
        assert chiller.connect() == True
        assert chiller.is_connected == True
        
        # Read temperature
        with patch.object(chiller, 'read_dev', return_value="25.0"):
            temp = chiller.read_temp()
            assert temp == 25.0
        
        # Set temperature
        with patch.object(chiller, 'set_param') as mock_set_param:
            chiller.set_temperature(22.0)
            mock_set_param.assert_called_once()
        
        # Disconnect
        assert chiller.disconnect() == True
        assert chiller.is_connected == False

    def test_error_handling_without_connection(self):
        """Test that operations fail gracefully when not connected."""
        chiller = Chiller("error_test", "COM3")
        
        # All operations should raise exceptions when not connected
        with pytest.raises(Exception):
            chiller.read_temp()
        
        with pytest.raises(Exception):
            chiller.set_temperature(25.0)
        
        with pytest.raises(Exception):
            chiller.start_device()

    def test_logger_creation_and_usage(self):
        """Test logger creation and usage throughout operations."""
        chiller = Chiller("logger_integration_test", "COM3")
        
        # Logger should be created
        assert chiller.logger is not None
        assert "Chiller_logger_integration_test_" in chiller.logger.name
        
        # Test custom_logger functionality
        with patch.object(chiller.logger, 'info') as mock_info:
            chiller.custom_logger("test", "COM3", "measure", 123, "unit")
            mock_info.assert_called_once_with("test   COM3   measure   123//unit")

    # =============================================================================
    #     Threading Tests
    # =============================================================================

    def test_internal_thread_mode_initialization(self):
        """Test initialization in internal thread mode (no external thread/lock passed)."""
        chiller = Chiller("internal_thread_test", "COM3", hk_interval=15.0)
        
        # Check internal mode detection
        assert chiller.external_thread == False
        assert chiller.external_lock == False
        
        # Check thread attributes
        assert chiller.hk_thread is not None
        assert chiller.thread_lock is not None
        assert chiller.hk_lock is not None
        assert chiller.hk_interval == 15.0
        assert chiller.hk_running == False
        assert chiller.hk_stop_event is not None
        
        # Thread should not be alive initially
        assert chiller.hk_thread.is_alive() == False

    def test_external_thread_mode_initialization(self):
        """Test initialization in external thread mode (external thread/lock passed)."""
        import threading
        
        external_thread = threading.Thread(name="TestExternalThread")
        external_lock = threading.Lock()
        
        chiller = Chiller(
            "external_thread_test", 
            "COM3", 
            hk_thread=external_thread,
            thread_lock=external_lock,
            hk_interval=10.0
        )
        
        # Check external mode detection
        assert chiller.external_thread == True
        assert chiller.external_lock == True
        
        # Check that external objects are used
        assert chiller.hk_thread is external_thread
        assert chiller.thread_lock is external_lock
        assert chiller.hk_lock is not None  # Should still have housekeeping lock
        assert chiller.hk_interval == 10.0

    def test_enable_file_logging_existing_handler(self):
        """Test enable_file_logging when handler already exists."""
        chiller = Chiller("file_logging_existing_test", "COM3")
        
        # Add a file handler
        file_handler = logging.FileHandler("test.log")
        chiller.logger.addHandler(file_handler)
        
        with patch.object(chiller.logger, 'info') as mock_info:
            result = chiller.enable_file_logging()
            
            assert result == True
            mock_info.assert_called_with("File logging already enabled")

    def test_start_housekeeping_internal_mode_success(self):
        """Test start_housekeeping in internal thread mode."""
        chiller = Chiller("hk_internal_test", "COM3")
        chiller.is_connected = True  # Mock connection
        
        with patch.object(chiller, 'enable_file_logging') as mock_enable_logging, \
             patch('threading.Thread') as mock_thread:
            
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance
            
            result = chiller.start_housekeeping(interval=5, log_to_file=True)
            
            assert result == True
            assert chiller.hk_running == True
            assert chiller.hk_interval == 5
            mock_enable_logging.assert_called_once()
            mock_thread_instance.start.assert_called_once()

    def test_start_housekeeping_external_mode_success(self):
        """Test start_housekeeping in external thread mode."""
        import threading
        
        external_thread = threading.Thread(name="TestThread")
        chiller = Chiller(
            "hk_external_test", 
            "COM3", 
            hk_thread=external_thread
        )
        chiller.is_connected = True  # Mock connection
        
        with patch.object(chiller, 'enable_file_logging') as mock_enable_logging:
            result = chiller.start_housekeeping(interval=3, log_to_file=True)
            
            assert result == True
            assert chiller.hk_running == True
            assert chiller.hk_interval == 3
            mock_enable_logging.assert_called_once()
            # External thread should not be started automatically

    def test_start_housekeeping_default_interval(self):
        """Test start_housekeeping with default interval (-1)."""
        chiller = Chiller("hk_default_interval_test", "COM3", hk_interval=25.0)
        chiller.is_connected = True
        
        with patch.object(chiller, 'enable_file_logging'):
            result = chiller.start_housekeeping(interval=-1)
            
            assert result == True
            assert chiller.hk_interval == 25.0  # Should keep original value

    def test_start_housekeeping_not_connected(self):
        """Test start_housekeeping fails when not connected."""
        chiller = Chiller("hk_not_connected_test", "COM3")
        
        result = chiller.start_housekeeping()
        
        assert result == False
        assert chiller.hk_running == False

    def test_start_housekeeping_already_running(self):
        """Test start_housekeeping when already running."""
        chiller = Chiller("hk_already_running_test", "COM3")
        chiller.is_connected = True
        chiller.hk_running = True
        
        result = chiller.start_housekeeping()
        
        assert result == True  # Should return True but not change state

    def test_stop_housekeeping_internal_mode(self):
        """Test stop_housekeeping in internal thread mode."""
        chiller = Chiller("stop_hk_internal_test", "COM3")
        chiller.hk_running = True
        
        # Mock a running thread
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        chiller.hk_thread = mock_thread
        
        result = chiller.stop_housekeeping()
        
        assert result == True
        assert chiller.hk_running == False
        assert chiller.hk_stop_event.is_set() == True
        mock_thread.join.assert_called_once_with(timeout=5.0)

    def test_stop_housekeeping_external_mode(self):
        """Test stop_housekeeping in external thread mode."""
        import threading
        
        external_thread = threading.Thread(name="TestThread")
        chiller = Chiller(
            "stop_hk_external_test", 
            "COM3", 
            hk_thread=external_thread
        )
        chiller.hk_running = True
        
        result = chiller.stop_housekeeping()
        
        assert result == True
        assert chiller.hk_running == False
        assert chiller.hk_stop_event.is_set() == True

    def test_stop_housekeeping_not_running(self):
        """Test stop_housekeeping when not running."""
        chiller = Chiller("stop_hk_not_running_test", "COM3")
        
        result = chiller.stop_housekeeping()
        
        assert result == True  # Should succeed even if not running

    def test_do_housekeeping_cycle_success(self):
        """Test do_housekeeping_cycle successful execution."""
        chiller = Chiller("hk_cycle_success_test", "COM3")
        chiller.hk_running = True
        chiller.is_connected = True
        
        with patch.object(chiller, 'hk_monitor') as mock_hk_monitor:
            result = chiller.do_housekeeping_cycle()
            
            assert result == True
            mock_hk_monitor.assert_called_once()

    def test_do_housekeeping_cycle_not_running(self):
        """Test do_housekeeping_cycle when not running."""
        chiller = Chiller("hk_cycle_not_running_test", "COM3")
        chiller.hk_running = False
        
        result = chiller.do_housekeeping_cycle()
        
        assert result == False

    def test_do_housekeeping_cycle_not_connected(self):
        """Test do_housekeeping_cycle when not connected."""
        chiller = Chiller("hk_cycle_not_connected_test", "COM3")
        chiller.hk_running = True
        chiller.is_connected = False
        
        result = chiller.do_housekeeping_cycle()
        
        assert result == False

    def test_do_housekeeping_cycle_exception(self):
        """Test do_housekeeping_cycle handles exceptions."""
        chiller = Chiller("hk_cycle_exception_test", "COM3")
        chiller.hk_running = True
        chiller.is_connected = True
        
        with patch.object(chiller, 'hk_monitor', side_effect=Exception("Test error")):
            result = chiller.do_housekeeping_cycle()
            
            assert result == False

    def test_should_continue_housekeeping_true(self):
        """Test should_continue_housekeeping returns True when should continue."""
        chiller = Chiller("should_continue_true_test", "COM3")
        chiller.hk_running = True
        chiller.hk_stop_event.clear()
        
        result = chiller.should_continue_housekeeping()
        
        assert result == True

    def test_should_continue_housekeeping_false_not_running(self):
        """Test should_continue_housekeeping returns False when not running."""
        chiller = Chiller("should_continue_false_test", "COM3")
        chiller.hk_running = False
        
        result = chiller.should_continue_housekeeping()
        
        assert result == False

    def test_should_continue_housekeeping_false_stop_event(self):
        """Test should_continue_housekeeping returns False when stop event is set."""
        chiller = Chiller("should_continue_stop_test", "COM3")
        chiller.hk_running = True
        chiller.hk_stop_event.set()
        
        result = chiller.should_continue_housekeeping()
        
        assert result == False

    def test_hk_worker_function(self):
        """Test _hk_worker internal thread function."""
        chiller = Chiller("hk_worker_test", "COM3")
        chiller.is_connected = True
        chiller.hk_running = True
        chiller.hk_interval = 0.1  # Short interval for testing
        
        with patch.object(chiller, 'hk_monitor') as mock_hk_monitor, \
             patch.object(chiller.hk_stop_event, 'wait') as mock_wait:
            
            # Set stop event after first iteration
            def stop_after_first_call(*args, **kwargs):
                chiller.hk_stop_event.set()
                return False
            
            mock_wait.side_effect = stop_after_first_call
            
            chiller._hk_worker()
            
            mock_hk_monitor.assert_called_once()
            mock_wait.assert_called_with(timeout=0.1)

    def test_get_status_with_threading_info(self):
        """Test get_status includes threading information."""
        import threading
        
        external_thread = threading.Thread(name="TestStatusThread")
        chiller = Chiller(
            "status_threading_test", 
            "COM3", 
            hk_thread=external_thread,
            hk_interval=20.0
        )
        chiller.hk_running = True
        
        status = chiller.get_status()
        
        assert status["housekeeping_running"] == True
        assert status["housekeeping_interval"] == 20.0
        assert status["thread_name"] == "TestStatusThread"

    def test_thread_safety_concurrent_access(self):
        """Test thread safety with concurrent access to methods."""
        import threading
        import time
        
        chiller = Chiller("thread_safety_test", "COM3")
        chiller.is_connected = True
        
        results = []
        
        def worker():
            try:
                # Test concurrent access to helper methods
                chiller.should_continue_housekeeping()
                chiller.do_housekeeping_cycle()
                results.append("success")
            except Exception as e:
                results.append(f"error: {e}")
        
        # Start multiple threads
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=2)
        
        # Should have some results (may be mix of success/failure due to no connection)
        assert len(results) == 5

    def test_disconnect_stops_housekeeping(self):
        """Test that disconnect() stops housekeeping automatically."""
        chiller = Chiller("disconnect_hk_test", "COM3")
        chiller.hk_running = True
        
        with patch.object(chiller, 'stop_housekeeping') as mock_stop_hk:
            chiller.disconnect()
            
            mock_stop_hk.assert_called_once()

    def test_cleanup_destructor(self):
        """Test __del__ method calls stop_housekeeping."""
        chiller = Chiller("cleanup_test", "COM3")
        
        with patch.object(chiller, 'stop_housekeeping') as mock_stop_hk:
            chiller.__del__()
            
            mock_stop_hk.assert_called_once()

    def test_threading_attributes_consistency(self):
        """Test that threading attributes are consistent across both modes."""
        # Internal mode
        chiller_internal = Chiller("attr_internal_test", "COM3")
        
        # External mode
        import threading
        external_thread = threading.Thread(name="TestThread")
        external_lock = threading.Lock()
        chiller_external = Chiller(
            "attr_external_test", 
            "COM3", 
            hk_thread=external_thread,
            thread_lock=external_lock
        )
        
        # Both should have the same set of threading attributes
        threading_attrs = [
            'hk_thread', 'thread_lock', 'hk_lock', 'hk_running', 
            'hk_stop_event', 'hk_interval', 'external_thread', 'external_lock'
        ]
        
        for attr in threading_attrs:
            assert hasattr(chiller_internal, attr), f"Internal mode missing {attr}"
            assert hasattr(chiller_external, attr), f"External mode missing {attr}"

    def test_interval_parameter_handling(self):
        """Test proper handling of interval parameter in various scenarios."""
        chiller = Chiller("interval_test", "COM3", hk_interval=30.0)
        chiller.is_connected = True
        
        with patch.object(chiller, 'enable_file_logging'):
            # Test positive interval
            chiller.start_housekeeping(interval=10)
            assert chiller.hk_interval == 10
            chiller.stop_housekeeping()
            
            # Test negative interval (should use default)
            chiller.start_housekeeping(interval=-1)
            assert chiller.hk_interval == 10  # Should keep previous value
            chiller.stop_housekeeping()
            
            # Test zero interval
            chiller.start_housekeeping(interval=0)
            assert chiller.hk_interval == 10  # Should keep previous value
