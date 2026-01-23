"""
PSU (Power Supply Unit) device controller.

This module provides the PSU class for communicating with CGC power supply
units via the PSU base hardware interface with added logging functionality.
"""
from typing import Optional
import logging
from datetime import datetime
from pathlib import Path
import threading

from .psu_base import PSUBase


class PSU(PSUBase):
    """
    PSU device communication class with logging functionality.

    This class inherits from PSUBase and provides logging capabilities,
    device identification, housekeeping thread management, and enhanced
    function call monitoring similar to other devices in the system.

    Example:
        psu = PSU("main_psu", com=5, port=0)
        psu.connect()
        psu.set_psu0_output_voltage(100.5)
        voltage = psu.get_psu0_output_voltage()
        psu.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        com: int,
        port: int = 0,
        baudrate: int = 230400,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 5.0,
        **kwargs,
    ):
        """
        Initialize PSU device with logging and threading support.
        """
        # Store parameters for PSU functionality
        self.device_id = device_id
        self.com = com
        self.port_num = port
        self.baudrate = baudrate
        self.hk_interval = hk_interval
        
        # Connection status
        self.connected = False
        
        # Housekeeping setup
        self.hk_running = False
        self.hk_stop_event = threading.Event()
        
        # Determine if using external or internal thread management
        self.external_thread = hk_thread is not None
        self.external_lock = thread_lock is not None
        
        # Setup thread lock (for communication)
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
                target=self._hk_worker, name=f"HK_{device_id}", daemon=True
            )

        # Setup logger
        if logger is not None:
            self.logger = logger
            self._external_logger_provided = True
        else:
            self._external_logger_provided = False
            # Create logger with file handler and timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"PSU_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            # Only add handler if logger doesn't already have one
            if not self.logger.handlers:
                # Create logs directory if it doesn't exist
                # Navigate from src/devices/cgc/psu/ back to project root, then to debugging/logs
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent.parent / "debugging" / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                # Create file handler with timestamp
                log_filename = f"PSU_{device_id}_{timestamp}.log"
                log_filepath = logs_dir / log_filename

                file_handler = logging.FileHandler(log_filepath)
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                file_handler.setFormatter(formatter)

                self.logger.addHandler(file_handler)
                self.logger.setLevel(logging.DEBUG)

                # Log the initialization
                self.logger.info(
                    f"PSU logger initialized for device '{device_id}' on COM{com}, port {port}"
                )
                self.logger.info(f"Baudrate: {baudrate}")

        # Initialize the base class
        super().__init__(com=com, port=port, log=None, idn=device_id)

    def connect(self) -> bool:
        """Connect to the PSU device."""
        try:
            self.logger.info(f"Connecting to PSU device {self.device_id} on COM{self.com}, port {self.port_num}")
            
            # Open port using base class method
            status = self.open_port(self.com, self.port_num)
            
            if status == self.NO_ERR:
                # Set communication speed
                speed_status = self.set_comspeed(self.baudrate)
                if speed_status == self.NO_ERR:
                    self.connected = True
                    self.logger.info(f"Successfully connected to PSU device {self.device_id}")
                    return True
                else:
                    self.logger.error(f"Failed to set communication speed: status {speed_status}")
                    return False
            else:
                self.logger.error(f"Failed to open port: status {status}")
                return False
                
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            return False

    def disconnect(self) -> bool:
        """Disconnect from the PSU device."""
        try:
            # Stop housekeeping before disconnecting
            self.stop_housekeeping()
            
            self.logger.info(f"Disconnecting PSU device {self.device_id}")
            
            # Close port using base class method
            status = self.close_port()
            
            if status == self.NO_ERR:
                self.connected = False
                self.logger.info(f"Successfully disconnected PSU device {self.device_id}")
                return True
            else:
                self.logger.error(f"Failed to close port: status {status}")
                return False
                
        except Exception as e:
            self.logger.error(f"Disconnection error: {e}")
            return False

    def _hk_worker(self):
        """
        Internal housekeeping worker thread function.
        Runs continuously until stop_event is set.
        """
        self.logger.info(f"Housekeeping worker started for {self.device_id}")
        
        while not self.hk_stop_event.is_set() and self.hk_running:
            try:
                if self.connected:
                    self.hk_monitor()
                else:
                    self.logger.warning("Device disconnected, pausing housekeeping")

                # Wait for interval or stop event
                self.hk_stop_event.wait(timeout=self.hk_interval)

            except Exception as e:
                self.logger.error(f"Housekeeping error: {e}")
                # Continue running even after errors
                self.hk_stop_event.wait(timeout=self.hk_interval)

        self.logger.info(f"Housekeeping worker stopped for {self.device_id}")

    # Individual housekeeping functions with structured logging
    
    def _hk_product_info(self):
        """Get and log product information."""
        status, product_no = self.get_product_no()
        if status == self.NO_ERR:
            self.logger.info(f"Product number: {product_no}")
        return status == self.NO_ERR

    def _hk_main_state(self):
        """Get and log main device state."""
        status, state_hex, state_name = self.get_main_state()
        if status == self.NO_ERR:
            self.logger.info(f"Main state: {state_name}")
        return status == self.NO_ERR

    def _hk_device_state(self):
        """Get and log device state."""
        status, state_hex, state_names = self.get_device_state()
        if status == self.NO_ERR:
            self.logger.info(f"Device state: {', '.join(state_names)}")
        return status == self.NO_ERR

    def _hk_general_housekeeping(self):
        """Get and log general housekeeping data."""
        status, volt_rect, volt_5v0, volt_3v3, temp_cpu = self.get_housekeeping()
        if status == self.NO_ERR:
            self.logger.info("get_housekeeping() results:")
            self.logger.info(f"  Rectifier Voltage: {volt_rect:.2f}V")
            self.logger.info(f"  5V Supply: {volt_5v0:.2f}V")
            self.logger.info(f"  3.3V Supply: {volt_3v3:.2f}V")
            self.logger.info(f"  CPU Temperature: {temp_cpu:.1f}°C")
        return status == self.NO_ERR

    def _hk_sensor_data(self):
        """Get and log sensor data."""
        status, temp0, temp1, temp2 = self.get_sensor_data()
        if status == self.NO_ERR:
            self.logger.info("get_sensor_data() results:")
            self.logger.info(f"  Sensor 0 Temperature: {temp0:.1f}°C")
            self.logger.info(f"  Sensor 1 Temperature: {temp1:.1f}°C")
            self.logger.info(f"  Sensor 2 Temperature: {temp2:.1f}°C")
        return status == self.NO_ERR

    def _hk_psu0_adc_housekeeping(self):
        """Get and log PSU0 ADC housekeeping data."""
        status, volt_avdd, volt_dvdd, volt_aldo, volt_dldo, volt_ref, temp_adc = self.get_psu0_adc_housekeeping()
        if status == self.NO_ERR:
            self.logger.info("get_psu0_adc_housekeeping() results:")
            self.logger.info(f"  AVDD Voltage: {volt_avdd:.2f}V")
            self.logger.info(f"  DVDD Voltage: {volt_dvdd:.2f}V")
            self.logger.info(f"  ALDO Voltage: {volt_aldo:.2f}V")
            self.logger.info(f"  DLDO Voltage: {volt_dldo:.2f}V")
            self.logger.info(f"  Reference Voltage: {volt_ref:.2f}V")
            self.logger.info(f"  ADC Temperature: {temp_adc:.1f}°C")
        return status == self.NO_ERR

    def _hk_psu1_adc_housekeeping(self):
        """Get and log PSU1 ADC housekeeping data."""
        status, volt_avdd, volt_dvdd, volt_aldo, volt_dldo, volt_ref, temp_adc = self.get_psu1_adc_housekeeping()
        if status == self.NO_ERR:
            self.logger.info("get_psu1_adc_housekeeping() results:")
            self.logger.info(f"  AVDD Voltage: {volt_avdd:.2f}V")
            self.logger.info(f"  DVDD Voltage: {volt_dvdd:.2f}V")
            self.logger.info(f"  ALDO Voltage: {volt_aldo:.2f}V")
            self.logger.info(f"  DLDO Voltage: {volt_dldo:.2f}V")
            self.logger.info(f"  Reference Voltage: {volt_ref:.2f}V")
            self.logger.info(f"  ADC Temperature: {temp_adc:.1f}°C")
        return status == self.NO_ERR

    def _hk_psu0_housekeeping(self):
        """Get and log PSU0 housekeeping data."""
        status, volt_24vp, volt_12vp, volt_12vn, volt_ref = self.get_psu0_housekeeping()
        if status == self.NO_ERR:
            self.logger.info("get_psu0_housekeeping() results:")
            self.logger.info(f"  24V+ Supply: {volt_24vp:.2f}V")
            self.logger.info(f"  12V+ Supply: {volt_12vp:.2f}V")
            self.logger.info(f"  12V- Supply: {volt_12vn:.2f}V")
            self.logger.info(f"  Reference Voltage: {volt_ref:.2f}V")
        return status == self.NO_ERR

    def _hk_psu1_housekeeping(self):
        """Get and log PSU1 housekeeping data."""
        status, volt_24vp, volt_12vp, volt_12vn, volt_ref = self.get_psu1_housekeeping()
        if status == self.NO_ERR:
            self.logger.info("get_psu1_housekeeping() results:")
            self.logger.info(f"  24V+ Supply: {volt_24vp:.2f}V")
            self.logger.info(f"  12V+ Supply: {volt_12vp:.2f}V")
            self.logger.info(f"  12V- Supply: {volt_12vn:.2f}V")
            self.logger.info(f"  Reference Voltage: {volt_ref:.2f}V")
        return status == self.NO_ERR

    def _hk_psu0_data(self):
        """Get and log PSU0 measured data."""
        status, voltage, current, volt_dropout = self.get_psu0_data()
        if status == self.NO_ERR:
            self.logger.info("get_psu0_data() results:")
            self.logger.info(f"  Output Voltage: {voltage:.3f}V")
            self.logger.info(f"  Output Current: {current:.3f}A")
            self.logger.info(f"  Dropout Voltage: {volt_dropout:.2f}V")
        return status == self.NO_ERR

    def _hk_psu1_data(self):
        """Get and log PSU1 measured data."""
        status, voltage, current, volt_dropout = self.get_psu1_data()
        if status == self.NO_ERR:
            self.logger.info("get_psu1_data() results:")
            self.logger.info(f"  Output Voltage: {voltage:.3f}V")
            self.logger.info(f"  Output Current: {current:.3f}A")
            self.logger.info(f"  Dropout Voltage: {volt_dropout:.2f}V")
        return status == self.NO_ERR

    def hk_monitor(self):
        """
        Perform housekeeping monitoring of PSU device data.
        This method executes all individual housekeeping functions.
        """
        try:
            # Execute all housekeeping functions
            with self.thread_lock:
                self._hk_product_info()
                self._hk_main_state()
                self._hk_device_state()
                self._hk_general_housekeeping()
                self._hk_sensor_data()
                self._hk_psu0_adc_housekeeping()
                self._hk_psu1_adc_housekeeping()
                self._hk_psu0_housekeeping()
                self._hk_psu1_housekeeping()
                self._hk_psu0_data()
                self._hk_psu1_data()
        except Exception as e:
            self.logger.error(f"Housekeeping monitoring failed: {e}")

    # =============================================================================
    #     Housekeeping and Threading Methods
    # =============================================================================

    def start_housekeeping(self, interval=-1, log_to_file=True) -> bool:
        """
        Start housekeeping monitoring. Works automatically in both internal and external thread modes.

        - Internal mode (no thread passed to __init__): Creates and manages its own thread
        - External mode (thread passed to __init__): Enables monitoring for external thread control

        Args:
            interval (int): Monitoring interval in seconds (default: uses hk_interval from __init__)
            log_to_file (bool): Whether to enable file logging (default: True)

        Returns:
            bool: True if started successfully, False otherwise
        """
        if not self.connected:
            self.logger.warning("Cannot start housekeeping: device not connected")
            return False

        with self.hk_lock:
            if self.hk_running:
                self.logger.warning("Housekeeping already running")
                return True

            try:
                self.hk_running = True
                if interval > 0:
                    self.hk_interval = interval
                else:
                    interval = self.hk_interval

                self.hk_stop_event.clear()

                if self.external_thread:
                    # External mode: Just enable monitoring, external code controls the thread
                    self.logger.info(
                        f"Housekeeping enabled (external mode) - interval: {interval}s"
                    )
                    self.logger.info(
                        "Use do_housekeeping_cycle() in your external thread"
                    )
                else:
                    # Internal mode: Start our own thread
                    if not self.hk_thread.is_alive():
                        self.hk_thread = threading.Thread(
                            target=self._hk_worker,
                            name=f"HK_{self.device_id}",
                            daemon=True,
                        )
                        self.hk_thread.start()

                    self.logger.info(
                        f"Housekeeping started (internal mode) - interval: {interval}s"
                    )

                return True

            except Exception as e:
                self.logger.error(f"Failed to start housekeeping: {e}")
                self.hk_running = False
                return False

    def stop_housekeeping(self) -> bool:
        """
        Stop housekeeping monitoring. Works in both internal and external modes.

        Returns:
            bool: True if stopped successfully, False otherwise
        """
        if not self.hk_running:
            return True

        with self.hk_lock:
            try:
                self.hk_running = False
                self.hk_stop_event.set()

                if self.external_thread:
                    # External mode: Just signal to stop
                    self.logger.info("Housekeeping stopped (external mode)")
                else:
                    # Internal mode: Wait for our thread to finish
                    if self.hk_thread and self.hk_thread.is_alive():
                        self.hk_thread.join(timeout=5.0)
                        if self.hk_thread.is_alive():
                            self.logger.warning(
                                "Housekeeping thread did not stop within timeout"
                            )

                    self.logger.info("Housekeeping stopped (internal mode)")

                return True

            except Exception as e:
                self.logger.error(f"Failed to stop housekeeping: {e}")
                return False

    def do_housekeeping_cycle(self) -> bool:
        """
        Perform one housekeeping cycle. Use this in external threads.

        This is the main method for external thread control - call it periodically
        in your external thread loop.

        Returns:
            bool: True if cycle completed successfully, False otherwise
        """
        if not self.hk_running:
            return False

        try:
            if self.connected:
                self.hk_monitor()
                return True
            else:
                self.logger.warning("Device not connected during housekeeping cycle")
                return False

        except Exception as e:
            self.logger.error(f"Housekeeping cycle error: {e}")
            return False

    def get_status(self) -> dict:
        """
        Get current PSU device status.

        Returns:
            Dict: Dictionary containing device status information
        """
        return {
            "device_id": self.device_id,
            "com": self.com,
            "port": self.port_num,
            "baudrate": self.baudrate,
            "connected": self.connected,
            "hk_running": self.hk_running,
            "hk_interval": self.hk_interval,
            "external_thread": self.external_thread,
            "external_lock": self.external_lock,
        }

    # Override key methods with logging
    
    def set_psu_output_voltage(self, psu_num, voltage):
        """Set PSU output voltage with logging."""
        psu_name = "PSU0" if psu_num == self.PSU_POS else "PSU1"
        self.logger.info(f"Setting {psu_name} output voltage to {voltage:.3f}V")
        try:
            status = super().set_psu_output_voltage(psu_num, voltage)
            if status == self.NO_ERR:
                self.logger.info(f"{psu_name} output voltage set successfully")
            else:
                self.logger.error(f"Failed to set {psu_name} output voltage: status {status}")
            return status
        except ValueError as e:
            self.logger.error(f"Invalid voltage format for {psu_name}: {e}")
            raise

    def set_psu0_output_voltage(self, voltage):
        """Set PSU0 output voltage with logging."""
        return self.set_psu_output_voltage(self.PSU_POS, voltage)
    
    def set_psu1_output_voltage(self, voltage):
        """Set PSU1 output voltage with logging."""
        return self.set_psu_output_voltage(self.PSU_NEG, voltage)

    def get_psu_output_voltage(self, psu_num):
        """Get PSU output voltage with logging."""
        status, voltage = super().get_psu_output_voltage(psu_num)
        if status == self.NO_ERR:
            psu_name = "PSU0" if psu_num == self.PSU_POS else "PSU1"
            self.logger.info(f"{psu_name} output voltage: {voltage:.3f}V")
        else:
            self.logger.warning(f"Failed to get PSU{psu_num} output voltage: status {status}")
        return status, voltage

    def get_psu0_output_voltage(self):
        """Get PSU0 output voltage with logging."""
        return self.get_psu_output_voltage(self.PSU_POS)
    
    def get_psu1_output_voltage(self):
        """Get PSU1 output voltage with logging."""
        return self.get_psu_output_voltage(self.PSU_NEG)

    def __getattr__(self, name):
        """
        Automatically wrap base class methods with logging.
        
        This method is called when an attribute is not found in the current class.
        It will look for the method in the base class and wrap it with logging.
        """
        # Get the method from the base class
        if hasattr(PSUBase, name):
            base_method = getattr(PSUBase, name)
            
            # Check if it's a callable method (not a constant or property)
            if callable(base_method):
                def logged_method(*args, **kwargs):
                    """Wrapper method that adds logging to base class methods."""
                    # Log the method call
                    self.logger.info(f"Calling {name} with args={args[1:]} kwargs={kwargs}")
                    
                    try:
                        # Call the original method with self as first argument
                        result = base_method(self, *args, **kwargs)
                        
                        # Log successful execution
                        if isinstance(result, tuple) and len(result) >= 1:
                            # Most PSU methods return (status, ...) tuples
                            status = result[0]
                            if status == self.NO_ERR:
                                self.logger.info(f"{name} completed successfully")
                            else:
                                self.logger.warning(f"{name} returned status {status}")
                        else:
                            self.logger.info(f"{name} completed")
                        
                        return result
                        
                    except Exception as e:
                        self.logger.error(f"Error in {name}: {e}")
                        raise
                
                return logged_method
            else:
                # For non-callable attributes, return them directly
                return base_method
        
        # If attribute not found in base class, raise AttributeError
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
