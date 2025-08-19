"""
Syringe pump device controller.

This module provides the SyringePump class for communicating with syringe
pump devices via various communication protocols for precise fluid control.
"""
from typing import Any, Dict, Optional
import logging
from datetime import datetime
from pathlib import Path
import threading

import serial
import time
import sys
import glob


class SyringePump:
    """
    Syringe pump device communication class.

    This class handles communication with syringe pump devices, providing
    methods for precise fluid control, flow rate management, and volume dispensing.

    Example:
        pump = SyringePump("main_pump", port="COM5")
        pump.connect()
        pump.set_flow_rate(10.0)
        pump.start_pumping()
        pump.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.0,
        x: int = 0,
        mode: int = 0,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 30.0,  # Housekeeping interval in seconds
        **kwargs,
    ):
        """
        Initialize Syringe Pump device.

        Args:
            device_id: Unique identifier for the syringe pump
            port: Serial port (e.g., "COM5" on Windows, "/dev/ttyUSB0" on Linux)
            baudrate: Communication baud rate (default: 9600)
            timeout: Serial communication timeout in seconds (default: 1.0)
            x: Pump channel/axis identifier (default: 0, no prefix)
            mode: Pump operation mode (default: 0, no mode suffix)
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 30.0)
            **kwargs: Additional keyword arguments for future extensibility
        """
        self.device_id = device_id
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.x = x
        self.mode = mode
        self.is_connected = False
        self.serial_connection: Optional[serial.Serial] = None

        # Housekeeping and threading setup
        self.hk_interval = hk_interval
        self.hk_running = False
        self.hk_stop_event = threading.Event()
        
        # Determine if using external or internal thread management
        self.external_thread = hk_thread is not None
        self.external_lock = thread_lock is not None
        
        # Setup thread lock (for serial communication)
        if thread_lock is not None:
            self.thread_lock = thread_lock
        else:
            self.thread_lock = threading.Lock()
            
        # Setup housekeeping lock (separate from communication lock)
        self.hk_lock = threading.Lock()
            
        # Setup housekeeping thread
        if hk_thread is not None:
            self.hk_thread = hk_thread
            # For external threads, we don't manage the thread lifecycle
        else:
            self.hk_thread = threading.Thread(
                target=self._hk_worker,
                name=f"HK_{device_id}",
                daemon=True
            )

        # Setup logger
        if logger is not None:
            self.logger = logger
            self._external_logger_provided = True
        else:
            self._external_logger_provided = False
            # Create logger with file handler and timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"SyringePump_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            # Only add handler if logger doesn't already have one
            if not self.logger.handlers:
                # Create logs directory if it doesn't exist
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent / "debugging" / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                # Create file handler with timestamp
                log_filename = f"SyringePump_{device_id}_{timestamp}.log"
                log_filepath = logs_dir / log_filename

                file_handler = logging.FileHandler(log_filepath)
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                file_handler.setFormatter(formatter)

                self.logger.addHandler(file_handler)
                self.logger.setLevel(logging.INFO)

                # Log the initialization
                self.logger.info(
                    f"SyringePump logger initialized for device '{device_id}' on port '{port}'"
                )
                if self.external_thread:
                    self.logger.info(f"Using external thread: {self.hk_thread.name if hasattr(self.hk_thread, 'name') else 'unnamed'}")
                else:
                    self.logger.info(f"Using internal thread: {self.hk_thread.name}")
                    
                if self.external_lock:
                    self.logger.info("Using external thread lock")
                else:
                    self.logger.info("Using internal thread lock")

    def connect(self) -> bool:
        """
        Establish connection to the syringe pump.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            with self.thread_lock:
                self.serial_connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout
                )
                
                if self.serial_connection.is_open:
                    self.is_connected = True
                    self.logger.info(f"Successfully connected to SyringePump on {self.port}")
                    self._flush_buffers()
                    return True
                else:
                    self.logger.error(f"Failed to open connection to {self.port}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.is_connected = False
            return False

    def disconnect(self) -> bool:
        """
        Close connection to the syringe pump.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        try:
            with self.thread_lock:
                if self.serial_connection and self.serial_connection.is_open:
                    self.serial_connection.close()
                    self.is_connected = False
                    self.logger.info("Successfully disconnected from SyringePump")
                    return True
                else:
                    self.logger.warning("No active connection to close")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Disconnection failed: {e}")
            return False

    def _flush_buffers(self):
        """Flush input and output buffers."""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()

    def _send_command(self, command: str) -> list:
        """
        Send command to syringe pump and get response.
        
        Args:
            command: Command string to send
            
        Returns:
            list: Response from pump as list of strings
        """
        if not self.is_connected or not self.serial_connection:
            self.logger.error("No active connection")
            return []
            
        try:
            with self.thread_lock:
                # Send command with carriage return
                arg = bytes(str(command), 'utf8') + b'\r'
                self.serial_connection.write(arg)
                time.sleep(0.5)  # Wait for response
                
                response = self._get_response()
                self.logger.debug(f"Command: {command}, Response: {response}")
                return response
                
        except Exception as e:
            self.logger.error(f"Command failed: {command}, Error: {e}")
            return []

    def _get_response(self) -> list:
        """
        Read response from syringe pump.
        
        Returns:
            list: Response lines as list of strings
        """
        try:
            response_list = []
            response = self.serial_connection.readlines()
            for line in response:
                line = line.strip(b'\n').decode('utf8')
                line = line.strip('\r')
                if line:  # Only add non-empty lines
                    response_list.append(line)
            return response_list
            
        except Exception as e:
            self.logger.error(f"Failed to get response: {e}")
            return []

    def _add_mode(self, command: str) -> str:
        """
        Add mode suffix to command if mode is set.
        
        Args:
            command: Base command string
            
        Returns:
            str: Command with mode suffix if applicable
        """
        if self.mode == 0:
            return command
        else:
            return command + ' ' + str(self.mode - 1)

    def _add_x(self, command: str) -> str:
        """
        Add pump channel/axis prefix to command if x is set.
        
        Args:
            command: Base command string
            
        Returns:
            str: Command with x prefix if applicable
        """
        if self.x == 0:
            return command
        else:
            return str(self.x) + ' ' + command

    def start_pump(self) -> list:
        """
        Start the syringe pump.
        
        Returns:
            list: Response from pump
        """
        command = 'start'
        command = self._add_x(command)
        command = self._add_mode(command)
        response = self._send_command(command)
        self.logger.info("Pump started")
        return response

    def stop_pump(self) -> list:
        """
        Stop the syringe pump.
        
        Returns:
            list: Response from pump
        """
        command = 'stop'
        command = self._add_x(command)
        response = self._send_command(command)
        self.logger.info("Pump stopped")
        return response

    def pause_pump(self) -> list:
        """
        Pause the syringe pump.
        
        Returns:
            list: Response from pump
        """
        command = 'pause'
        command = self._add_x(command)
        response = self._send_command(command)
        self.logger.info("Pump paused")
        return response

    def restart_pump(self) -> list:
        """
        Restart the syringe pump.
        
        Returns:
            list: Response from pump
        """
        command = 'restart'
        response = self._send_command(command)
        self.logger.info("Pump restarted")
        return response

    def set_units(self, units: str) -> list:
        """
        Set flow rate units.
        
        Args:
            units: Units string ('mL/min', 'mL/hr', 'μL/min', 'μL/hr')
            
        Returns:
            list: Response from pump
        """
        units_dict = {
            'mL/min': '0',
            'mL/hr': '1', 
            'μL/min': '2',
            'μL/hr': '3'
        }
        
        if units not in units_dict:
            self.logger.error(f"Invalid units: {units}")
            return []
            
        command = f'set units {units_dict[units]}'
        response = self._send_command(command)
        self.logger.info(f"Units set to {units}")
        return response

    def set_diameter(self, diameter: float) -> list:
        """
        Set syringe diameter.
        
        Args:
            diameter: Syringe diameter in mm
            
        Returns:
            list: Response from pump
        """
        command = f'set diameter {diameter}'
        response = self._send_command(command)
        self.logger.info(f"Diameter set to {diameter} mm")
        return response

    def set_rate(self, rate) -> list:
        """
        Set flow rate.
        
        Args:
            rate: Flow rate (float) or list of rates for multi-step
            
        Returns:
            list: Response from pump
        """
        if isinstance(rate, list):
            # Multi-step command
            command = 'set rate ' + ','.join([str(x) for x in rate])
            self.logger.info(f"Flow rates set to {rate}")
        else:
            command = f'set rate {rate}'
            self.logger.info(f"Flow rate set to {rate}")
            
        response = self._send_command(command)
        return response

    def set_volume(self, volume) -> list:
        """
        Set syringe volume.
        
        Args:
            volume: Volume (float) or list of volumes for multi-step
            
        Returns:
            list: Response from pump
        """
        if isinstance(volume, list):
            # Multi-step command
            command = 'set volume ' + ','.join([str(x) for x in volume])
            self.logger.info(f"Volumes set to {volume}")
        else:
            command = f'set volume {volume}'
            self.logger.info(f"Volume set to {volume}")
            
        response = self._send_command(command)
        return response

    def set_delay(self, delay) -> list:
        """
        Set delay between steps.
        
        Args:
            delay: Delay (float) or list of delays for multi-step
            
        Returns:
            list: Response from pump
        """
        if isinstance(delay, list):
            # Multi-step command
            command = 'set delay ' + ','.join([str(x) for x in delay])
            self.logger.info(f"Delays set to {delay}")
        else:
            command = f'set delay {delay}'
            self.logger.info(f"Delay set to {delay}")
            
        response = self._send_command(command)
        return response

    def set_time(self, timer: float) -> list:
        """
        Set pump timer.
        
        Args:
            timer: Timer value
            
        Returns:
            list: Response from pump
        """
        command = f'set time {timer}'
        response = self._send_command(command)
        self.logger.info(f"Timer set to {timer}")
        return response

    def get_parameter_limits(self) -> list:
        """
        Get parameter limits from pump.
        
        Returns:
            list: Response with parameter limits
        """
        command = 'read limit parameter'
        response = self._send_command(command)
        return response

    def get_parameters(self) -> list:
        """
        Get current parameters from pump.
        
        Returns:
            list: Response with current parameters
        """
        command = 'view parameter'
        response = self._send_command(command)
        return response

    def get_displaced_volume(self) -> list:
        """
        Get displaced volume from pump.
        
        Returns:
            list: Response with displaced volume
        """
        command = 'dispensed volume'
        response = self._send_command(command)
        return response

    def get_elapsed_time(self) -> list:
        """
        Get elapsed time from pump.
        
        Returns:
            list: Response with elapsed time
        """
        command = 'elapsed time'
        response = self._send_command(command)
        return response

    def get_pump_status(self) -> list:
        """
        Get pump status.
        
        Returns:
            list: Response with pump status
        """
        command = 'pump status'
        response = self._send_command(command)
        return response

    @staticmethod
    def get_available_ports() -> list:
        """
        Get list of available serial ports.
        
        Returns:
            list: Available port names
        """
        if sys.platform.startswith('win'):
            ports = [f'COM{i+1}' for i in range(256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/tty.*')
        else:
            raise EnvironmentError('Unsupported platform')
            
        result = []
        for port in ports:
            try:
                s = serial.Serial(port)
                s.close()
                result.append(port)
            except (OSError, serial.SerialException):
                pass
        return result

    def _hk_worker(self):
        """
        Housekeeping worker thread function.
        Placeholder for future implementation of periodic monitoring.
        """
        pass
