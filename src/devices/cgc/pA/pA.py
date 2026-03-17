"""
pA (Picoammeter DMMR-8) device controller.

This module provides the PA class for communicating with CGC DMMR-8 picoammeter
devices via the PA base hardware interface with added logging functionality.
"""
from typing import Optional
import logging
import threading
from datetime import datetime
from pathlib import Path

from .pA_base import PABase


class PA(PABase):
    """
    PA (DMMR-8) device communication class with logging functionality.

    This class inherits from PABase and provides logging capabilities,
    device identification, housekeeping thread management, and enhanced
    function call monitoring similar to other devices in the system.

    The DMMR-8 is a picoammeter device that can manage up to 8 DPA-1F
    current measurement modules.

    Example:
        pa = PA("main_pa", com=5)
        pa.connect()
        pa.set_enable(True)
        status, addr, current, meas_range, time = pa.get_current()
        pa.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        com: int,
        baudrate: int = 230400,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 5.0,
        **kwargs,
    ):
        """
        Initialize PA device with logging and threading support.
        """
        # Store parameters for PA functionality
        self.device_id = device_id
        self.com = com
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
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"PA_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            if not self.logger.handlers:
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent.parent / "debugging" / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                log_filename = f"PA_{device_id}_{timestamp}.log"
                log_filepath = logs_dir / log_filename

                file_handler = logging.FileHandler(log_filepath)
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                file_handler.setFormatter(formatter)

                self.logger.addHandler(file_handler)
                self.logger.setLevel(logging.DEBUG)

                self.logger.info(
                    f"PA logger initialized for device '{device_id}' on COM{com}"
                )
                self.logger.info(f"Baudrate: {baudrate}")

        # Initialize the base class
        super().__init__(com=com, log=None, idn=device_id)

    def connect(self) -> bool:
        """Connect to the PA device."""
        try:
            self.logger.info(f"Connecting to PA device {self.device_id} on COM{self.com}")

            status = self.open_port(self.com)

            if status == self.NO_ERR:
                self.connected = True
                self.logger.info(f"Successfully connected to PA device {self.device_id}")

                baud_status, actual_baud = self.set_baud_rate(self.baudrate)
                if baud_status == self.NO_ERR:
                    self.logger.info(f"Baud rate set to {actual_baud}")
                else:
                    self.logger.warning(f"Failed to set baud rate: {baud_status}")

                return True
            else:
                self.logger.error(f"Failed to connect to PA device {self.device_id}: {status}")
                return False

        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            return False

    def disconnect(self) -> bool:
        """Disconnect from the PA device."""
        try:
            self.stop_housekeeping()

            self.logger.info(f"Disconnecting PA device {self.device_id}")

            status = self.close_port()

            if status == self.NO_ERR:
                self.connected = False
                self.logger.info(f"Successfully disconnected PA device {self.device_id}")
                return True
            else:
                self.logger.error(f"Failed to disconnect PA device {self.device_id}: {status}")
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
                    self.hk_stop_event.wait(timeout=self.hk_interval)
                else:
                    self.hk_stop_event.wait(timeout=1.0)

            except Exception as e:
                self.logger.error(f"Housekeeping worker error: {e}")
                self.hk_stop_event.wait(timeout=1.0)

        self.logger.info(f"Housekeeping worker stopped for {self.device_id}")

    # Individual housekeeping functions with structured logging

    def _hk_product_info(self):
        """Get and log product information."""
        status, product_no = self.get_product_no()
        if status == self.NO_ERR:
            self.logger.debug(f"Product number: {product_no}")
        return status == self.NO_ERR

    def _hk_main_state(self):
        """Get and log main device state."""
        status, state_hex, state_name = self.get_state()
        if status == self.NO_ERR:
            self.logger.debug(f"Main state: {state_name} ({state_hex})")
        return status == self.NO_ERR

    def _hk_device_state(self):
        """Get and log device state."""
        status, state_hex, state_names = self.get_device_state()
        if status == self.NO_ERR:
            self.logger.debug(f"Device state: {', '.join(state_names)} ({state_hex})")
        return status == self.NO_ERR

    def _hk_general_housekeeping(self):
        """Get and log general housekeeping data."""
        status, volt_12v, volt_5v0, volt_3v3, temp_cpu = self.get_housekeeping()

        if status == self.NO_ERR:
            self.logger.debug("get_housekeeping() results:")
            self.logger.debug(f"  12V Supply: {volt_12v:.2f}V")
            self.logger.debug(f"  5V Supply: {volt_5v0:.2f}V")
            self.logger.debug(f"  3.3V Supply: {volt_3v3:.2f}V")
            self.logger.debug(f"  CPU Temperature: {temp_cpu:.1f}degC")
        return status == self.NO_ERR

    def _hk_voltage_state(self):
        """Get and log voltage state."""
        status, state_hex, state_names = self.get_voltage_state()
        if status == self.NO_ERR:
            self.logger.debug(f"Voltage state: {', '.join(state_names)} ({state_hex})")
        return status == self.NO_ERR

    def _hk_temperature_state(self):
        """Get and log temperature state."""
        status, state_hex, state_names = self.get_temperature_state()
        if status == self.NO_ERR:
            self.logger.debug(f"Temperature state: {', '.join(state_names)} ({state_hex})")
        return status == self.NO_ERR

    def _hk_base_state(self):
        """Get and log base device state."""
        status, state_hex, state_names = self.get_base_state()
        if status == self.NO_ERR:
            self.logger.debug(f"Base state: {', '.join(state_names)} ({state_hex})")
        return status == self.NO_ERR

    def _hk_base_temp(self):
        """Get and log base temperature."""
        status, base_temp = self.get_base_temp()
        if status == self.NO_ERR:
            self.logger.debug(f"Base temperature: {base_temp:.1f}degC")
        return status == self.NO_ERR

    def _hk_fan_data(self):
        """Get and log fan data."""
        status, set_pwm, state_hex, state_names = self.get_base_fan_pwm()
        if status == self.NO_ERR:
            self.logger.debug(f"Fan PWM: {set_pwm}, State: {', '.join(state_names)} ({state_hex})")
        rpm_status, rpm = self.get_base_fan_rpm()
        if rpm_status == self.NO_ERR:
            self.logger.debug(f"Fan RPM: {rpm:.0f}")
        return status == self.NO_ERR

    def _hk_led_data(self):
        """Get and log LED data."""
        status, red, green, blue = self.get_base_led_data()
        if status == self.NO_ERR:
            self.logger.debug(f"LED state: R={red}, G={green}, B={blue}")
        return status == self.NO_ERR

    def _hk_cpu_data(self):
        """Get and log CPU data."""
        status, load, frequency = self.get_cpu_data()
        if status == self.NO_ERR:
            self.logger.debug(f"CPU: Load={load*100:.1f}%, Frequency={frequency/1e6:.1f}MHz")
        return status == self.NO_ERR

    def _hk_module_presence(self):
        """Get and log module presence."""
        status, valid, max_module, presence_list = self.get_module_presence()
        if status == self.NO_ERR:
            present_modules = [i for i, present in enumerate(presence_list) if present]
            self.logger.debug(f"Modules present: {present_modules} (Max: {max_module}, Valid: {valid})")
        return status == self.NO_ERR

    def hk_monitor(self):
        """
        Perform housekeeping monitoring of PA device data.
        This method executes all individual housekeeping functions.
        """
        try:
            with self.thread_lock:
                self._hk_product_info()
                self._hk_main_state()
                self._hk_device_state()
                self._hk_general_housekeeping()
                self._hk_voltage_state()
                self._hk_temperature_state()
                self._hk_base_state()
                self._hk_base_temp()
                self._hk_fan_data()
                self._hk_led_data()
                self._hk_cpu_data()
                self._hk_module_presence()

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
                if interval > 0:
                    self.hk_interval = interval

                self.hk_stop_event.clear()
                self.hk_running = True

                if self.external_thread:
                    self.logger.info("Housekeeping enabled for external thread control")
                else:
                    if not self.hk_thread.is_alive():
                        self.hk_thread = threading.Thread(
                            target=self._hk_worker, name=f"HK_{self.device_id}", daemon=True
                        )
                    self.hk_thread.start()
                    self.logger.info(f"Housekeeping thread started with {self.hk_interval}s interval")

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

                if not self.external_thread and self.hk_thread.is_alive():
                    self.hk_thread.join(timeout=2.0)
                    if self.hk_thread.is_alive():
                        self.logger.warning("Housekeeping thread did not stop cleanly")
                    else:
                        self.logger.info("Housekeeping thread stopped")
                else:
                    self.logger.info("Housekeeping monitoring disabled")

                return True

            except Exception as e:
                self.logger.error(f"Failed to stop housekeeping: {e}")
                return False

    def do_housekeeping_cycle(self) -> bool:
        """
        Perform one housekeeping cycle. Use this in external threads.

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
                self.logger.warning("Housekeeping cycle skipped: device not connected")
                return False

        except Exception as e:
            self.logger.error(f"Housekeeping cycle error: {e}")
            return False

    def get_status(self) -> dict:
        """
        Get current PA device status.

        Returns:
            Dict: Dictionary containing device status information
        """
        return {
            "device_id": self.device_id,
            "com": self.com,
            "baudrate": self.baudrate,
            "connected": self.connected,
            "hk_running": self.hk_running,
            "hk_interval": self.hk_interval,
            "external_thread": self.external_thread,
            "external_lock": self.external_lock,
        }

    # Override key methods with logging

    def set_enable(self, enable):
        """Enable/disable modules with logging."""
        self.logger.info(f"Setting module enable to {enable}")
        try:
            status = super().set_enable(enable)
            if status == self.NO_ERR:
                self.logger.info(f"Module enable set to {enable}")
            else:
                self.logger.error(f"Failed to set module enable: status {status}")
            return status
        except Exception as e:
            self.logger.error(f"Error setting module enable: {e}")
            raise

    def get_state(self):
        """Get main state with logging."""
        status, state_hex, state_name = super().get_state()
        if status == self.NO_ERR:
            self.logger.debug(f"Main state: {state_name} ({state_hex})")
        else:
            self.logger.error(f"Failed to get main state: status {status}")
        return status, state_hex, state_name

    def restart(self):
        """Restart device with logging."""
        self.logger.info("Restarting PA device")
        try:
            status = super().restart()
            if status == self.NO_ERR:
                self.logger.info("Device restart successful")
            else:
                self.logger.error(f"Device restart failed: status {status}")
            return status
        except Exception as e:
            self.logger.error(f"Error restarting device: {e}")
            raise

    # Module management convenience methods with logging

    def scan_modules(self):
        """Scan and log all connected modules."""
        self.logger.info("Scanning for connected modules")
        try:
            modules = super().scan_all_modules()
            if modules:
                self.logger.info(f"Found {len(modules)} modules:")
                for addr, info in modules.items():
                    self.logger.info(f"  Module {addr}: Product {info.get('product_no', 'Unknown')}, "
                                   f"FW {info.get('fw_version', 'Unknown')}, "
                                   f"State {info.get('state', 'Unknown')}")
            else:
                self.logger.warning("No modules found")
            return modules
        except Exception as e:
            self.logger.error(f"Error scanning modules: {e}")
            raise

    def get_module_info(self, address):
        """Get detailed module information with logging."""
        self.logger.debug(f"Getting information for module {address}")
        try:
            info = {}

            status, product_no = super().get_module_product_no(address)
            if status == self.NO_ERR:
                info['product_no'] = product_no

            status, fw_version = super().get_module_fw_version(address)
            if status == self.NO_ERR:
                info['fw_version'] = fw_version

            status, hw_type = super().get_module_hw_type(address)
            if status == self.NO_ERR:
                info['hw_type'] = hw_type

            status, hw_version = super().get_module_hw_version(address)
            if status == self.NO_ERR:
                info['hw_version'] = hw_version

            status, state = super().get_module_state(address)
            if status == self.NO_ERR:
                info['state'] = state

            hk_result = super().get_module_housekeeping(address)
            hk_status = hk_result[0]
            if hk_status == self.NO_ERR:
                info['housekeeping'] = {
                    'volt_3v3': hk_result[1],
                    'temp_cpu': hk_result[2],
                    'volt_5v0': hk_result[3],
                    'volt_12v': hk_result[4],
                    'volt_3v3i': hk_result[5],
                    'temp_cpui': hk_result[6],
                    'volt_2v5i': hk_result[7],
                    'volt_36vn': hk_result[8],
                    'volt_20vp': hk_result[9],
                    'volt_20vn': hk_result[10],
                    'volt_15vp': hk_result[11],
                    'volt_15vn': hk_result[12],
                    'volt_1v8p': hk_result[13],
                    'volt_1v8n': hk_result[14],
                    'volt_vrefp': hk_result[15],
                    'volt_vrefn': hk_result[16],
                }

            # Get current measurement data
            cur_status, meas_current, meas_range = super().get_module_current(address)
            if cur_status == self.NO_ERR:
                info['current'] = {
                    'value': meas_current,
                    'range': meas_range,
                }

            self.logger.debug(f"Retrieved information for module {address}")
            return info

        except Exception as e:
            self.logger.error(f"Error getting module {address} info: {e}")
            raise

    def restart_module(self, address):
        """Restart specific module with logging."""
        self.logger.info(f"Restarting module {address}")
        try:
            status = super().restart_module(address)
            if status == self.NO_ERR:
                self.logger.info(f"Module {address} restart successful")
            else:
                self.logger.error(f"Module {address} restart failed: status {status}")
            return status
        except Exception as e:
            self.logger.error(f"Error restarting module {address}: {e}")
            raise

    def __getattr__(self, name):
        """
        Automatically wrap base class methods with logging.

        This method is called when an attribute is not found in the current class.
        It will look for the method in the base class and wrap it with logging.
        """
        if hasattr(PABase, name):
            base_method = getattr(PABase, name)

            if callable(base_method):
                def logged_method(*args, **kwargs):
                    self.logger.debug(f"Calling {name} with args={args}, kwargs={kwargs}")
                    try:
                        result = base_method(self, *args, **kwargs)
                        self.logger.debug(f"{name} returned: {result}")
                        return result
                    except Exception as e:
                        self.logger.error(f"Error in {name}: {e}")
                        raise

                if hasattr(base_method, '__doc__'):
                    logged_method.__doc__ = base_method.__doc__

                setattr(self, name, logged_method)
                return logged_method
            else:
                return getattr(self, name)

        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
