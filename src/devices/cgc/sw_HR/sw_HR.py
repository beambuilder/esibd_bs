"""
SW_HR (High-Resolution Switch) device controller.

This module provides the SWHR class for communicating with CGC HV-AMX-CTRL-4EDH
high-resolution switch devices via the SW_HR base hardware interface with added
logging functionality.
"""
from typing import Optional
import logging
import threading
from datetime import datetime
from pathlib import Path

from .sw_HR_base import SWHRBase


class SWHR(SWHRBase):
    """
    SW_HR device communication class with logging functionality.

    This class inherits from SWHRBase and provides logging capabilities,
    device identification, housekeeping thread management, and enhanced
    function call monitoring similar to other devices in the system.

    The HV-AMX-CTRL-4EDH is a high-resolution switch controller that manages
    4 high-voltage switches with configurable timers, PLLs, clocks, dividers,
    counters, mapping engines, digital I/O, fine delay control, and
    trigger/enable source configuration.

    Example:
        sw_hr = SWHR("main_sw_hr", com=5, stream=0)
        sw_hr.connect()
        sw_hr.set_device_enable(True)
        state = sw_hr.get_device_state()
        sw_hr.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        com: int,
        stream: int = 0,
        baudrate: int = 230400,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 5.0,
        **kwargs,
    ):
        """
        Initialize SW_HR device with logging and threading support.
        """
        # Store parameters for SW_HR functionality
        self.device_id = device_id
        self.com = com
        self.stream_num = stream
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
            # Create logger with file handler and timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"SWHR_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            # Only add handler if logger doesn't already have one
            if not self.logger.handlers:
                # Create logs directory if it doesn't exist
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent.parent
                    / "debugging"
                    / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                # Create file handler with timestamp
                log_filename = f"SWHR_{device_id}_{timestamp}.log"
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
                    f"SWHR logger initialized for device '{device_id}' on COM{com}, stream {stream}"
                )
                self.logger.info(f"Baudrate: {baudrate}")

        # Initialize the base class
        super().__init__(com=com, stream=stream, log=None, idn=device_id)

    def connect(self) -> bool:
        """Connect to the SW_HR device."""
        try:
            self.logger.info(
                f"Connecting to SW_HR device {self.device_id} on COM{self.com}, stream {self.stream_num}"
            )

            # Open port using base class method
            status = self.open_port(self.com, self.stream_num)

            if status == self.NO_ERR:
                # Set communication speed
                baud_status, actual_baud = self.set_comspeed(self.baudrate)
                if baud_status == self.NO_ERR:
                    self.connected = True
                    self.logger.info(
                        f"Successfully connected to SW_HR device {self.device_id} "
                        f"(baud rate: {actual_baud})"
                    )
                    return True
                else:
                    self.logger.error(
                        f"Failed to set baud rate: status {baud_status}"
                    )
                    return False
            else:
                self.logger.error(f"Failed to open port: status {status}")
                return False

        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            return False

    def disconnect(self) -> bool:
        """Disconnect from the SW_HR device."""
        try:
            # Stop housekeeping before disconnecting
            self.stop_housekeeping()

            self.logger.info(f"Disconnecting SW_HR device {self.device_id}")

            # Close port using base class method
            status = self.close_port()

            if status == self.NO_ERR:
                self.connected = False
                self.logger.info(
                    f"Successfully disconnected SW_HR device {self.device_id}"
                )
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
                    # Wait for interval or stop event
                    self.hk_stop_event.wait(timeout=self.hk_interval)
                else:
                    # If not connected, wait a short time before checking again
                    self.hk_stop_event.wait(timeout=1.0)

            except Exception as e:
                self.logger.error(f"Housekeeping worker error: {e}")
                self.hk_stop_event.wait(timeout=1.0)

        self.logger.info(f"Housekeeping worker stopped for {self.device_id}")

    # =========================================================================
    #     Individual Housekeeping Functions
    # =========================================================================

    def _hk_product_info(self):
        """Get and log product information."""
        status, product_no = self.get_product_no()
        if status == self.NO_ERR:
            self.logger.debug(f"Product number: {product_no}")
        return status == self.NO_ERR

    def _hk_device_state(self):
        """Get and log device state."""
        (
            status,
            main_hex, main_name,
            dev_hex, dev_names,
            temp_hex, temp_names,
        ) = self.get_device_state()
        if status == self.NO_ERR:
            self.logger.debug(f"Main state: {main_name} ({main_hex})")
            self.logger.debug(
                f"Device state: {', '.join(dev_names)} ({dev_hex})"
            )
            self.logger.debug(
                f"Temperature state: {', '.join(temp_names)} ({temp_hex})"
            )
        return status == self.NO_ERR

    def _hk_general_housekeeping(self):
        """Get and log general housekeeping data."""
        (
            status,
            volt_12v, volt_fans, volt_5v0, volt_3v3,
            volt_3v3p, volt_2v5p, volt_vc, temp_cpu,
        ) = self.get_housekeeping()
        if status == self.NO_ERR:
            self.logger.debug("get_housekeeping() results:")
            self.logger.debug(f"  12V Supply: {volt_12v:.2f}V")
            self.logger.debug(f"  Fan Supply: {volt_fans:.2f}V")
            self.logger.debug(f"  5V Supply: {volt_5v0:.2f}V")
            self.logger.debug(f"  3.3V Supply: {volt_3v3:.2f}V")
            self.logger.debug(f"  3.3V PLL Supply: {volt_3v3p:.2f}V")
            self.logger.debug(f"  2.5V PLL Supply: {volt_2v5p:.2f}V")
            self.logger.debug(f"  Vc Supply: {volt_vc:.2f}V")
            self.logger.debug(f"  CPU Temperature: {temp_cpu:.1f}degC")
        return status == self.NO_ERR

    def _hk_sensor_data(self):
        """Get and log sensor data."""
        status, temp0, temp1, temp2 = self.get_sensor_data()
        if status == self.NO_ERR:
            self.logger.debug("get_sensor_data() results:")
            self.logger.debug(f"  Sensor 0 Temperature: {temp0:.1f}degC")
            self.logger.debug(f"  Sensor 1 Temperature: {temp1:.1f}degC")
            self.logger.debug(f"  Sensor 2 Temperature: {temp2:.1f}degC")
        return status == self.NO_ERR

    def _hk_fan_data(self):
        """Get and log fan data."""
        status, enabled, failed, set_rpm, measured_rpm, pwm = self.get_fan_data()
        if status == self.NO_ERR:
            self.logger.debug("get_fan_data() results:")
            for i in range(self.FAN_COUNT):
                self.logger.debug(
                    f"  Fan {i}: Enabled={enabled[i]}, Failed={failed[i]}, "
                    f"SetRPM={set_rpm[i]}, MeasRPM={measured_rpm[i]}, "
                    f"PWM={pwm[i]} ({pwm[i] / self.FAN_PWM_MAX * 100:.1f}%)"
                )
        return status == self.NO_ERR

    def _hk_led_data(self):
        """Get and log LED data."""
        status, red, green, blue = self.get_led_data()
        if status == self.NO_ERR:
            self.logger.debug(f"LED state: R={red}, G={green}, B={blue}")
        return status == self.NO_ERR

    def _hk_controller_state(self):
        """Get and log controller state."""
        status, state_hex, config, state_names = self.get_state()
        if status == self.NO_ERR:
            self.logger.debug(
                f"Controller state: {', '.join(state_names)} ({state_hex}), "
                f"Config=0x{config:04X}"
            )
        return status == self.NO_ERR

    def _hk_cpu_data(self):
        """Get and log CPU data."""
        status, load, frequency = self.get_cpu_data()
        if status == self.NO_ERR:
            self.logger.debug(
                f"CPU: Load={load * 100:.1f}%, Frequency={frequency / 1e6:.1f}MHz"
            )
        return status == self.NO_ERR

    def _hk_oscillator(self):
        """Get and log oscillator data."""
        status_c, osc_count = self.get_oscillator_count()
        if status_c == self.NO_ERR:
            for i in range(osc_count):
                status_p, period = self.get_oscillator_period(i)
                if status_p == self.NO_ERR:
                    freq = self.DEF_CLOCK / (period + self.OSC_OFFSET) if period > 0 else 0
                    self.logger.debug(
                        f"Oscillator {i}: Period={period}, Frequency={freq:.1f}Hz"
                    )
        return status_c == self.NO_ERR

    def _hk_timer_data(self):
        """Get and log timer data for all timers."""
        status_c, timer_count = self.get_timer_count()
        if status_c == self.NO_ERR:
            for i in range(timer_count):
                status_d, delay = self.get_timer_delay(i)
                status_w, width = self.get_timer_width(i)
                status_b, burst = self.get_timer_burst(i)
                if all(
                    s == self.NO_ERR
                    for s in [status_d, status_w, status_b]
                ):
                    self.logger.debug(
                        f"Timer {i}: Delay={delay}, Width={width}, Burst={burst}"
                    )
        return status_c == self.NO_ERR

    def _hk_switch_data(self):
        """Get and log switch configuration for all switches."""
        for i in range(self.SWITCH_NUM):
            status_ts, trig_src = self.get_switch_trigger_source(i)
            status_es, enb_src = self.get_switch_enable_source(i)
            status_d, rise_d, fall_d = self.get_switch_delay(i)
            status_rf, rise_fine = self.get_switch_rise_delay_fine(i)
            status_ff, fall_fine = self.get_switch_fall_delay_fine(i)
            if all(
                s == self.NO_ERR
                for s in [status_ts, status_es, status_d, status_rf, status_ff]
            ):
                self.logger.debug(
                    f"Switch {i}: TrigSrc=0x{trig_src:02X}, EnbSrc=0x{enb_src:02X}, "
                    f"Delay(rise={rise_d}, fall={fall_d}), "
                    f"FineDelay(rise={rise_fine}, fall={fall_fine})"
                )
        return True

    def hk_monitor(self):
        """
        Perform housekeeping monitoring of SW_HR device data.
        This method executes all individual housekeeping functions.
        """
        try:
            with self.thread_lock:
                self._hk_product_info()
                self._hk_device_state()
                self._hk_general_housekeeping()
                self._hk_sensor_data()
                self._hk_fan_data()
                self._hk_led_data()
                self._hk_controller_state()
                self._hk_cpu_data()
                self._hk_oscillator()
                self._hk_timer_data()
                self._hk_switch_data()

        except Exception as e:
            self.logger.error(f"Housekeeping monitoring failed: {e}")

    # =========================================================================
    #     Housekeeping and Threading Methods
    # =========================================================================

    def start_housekeeping(self, interval=-1, log_to_file=True) -> bool:
        """
        Start housekeeping monitoring. Works automatically in both internal
        and external thread modes.

        - Internal mode (no thread passed to __init__): Creates and manages
          its own thread.
        - External mode (thread passed to __init__): Enables monitoring for
          external thread control.

        Args:
            interval (int): Monitoring interval in seconds
                (default: uses hk_interval from __init__).
            log_to_file (bool): Whether to enable file logging (default: True).

        Returns:
            bool: True if started successfully, False otherwise.
        """
        if not self.connected:
            self.logger.warning("Cannot start housekeeping: device not connected")
            return False

        with self.hk_lock:
            if self.hk_running:
                self.logger.warning("Housekeeping already running")
                return True

            try:
                # Set the monitoring interval
                if interval > 0:
                    self.hk_interval = interval

                # Clear stop event
                self.hk_stop_event.clear()
                self.hk_running = True

                if self.external_thread:
                    # External thread mode - just enable monitoring
                    self.logger.info(
                        "Housekeeping enabled for external thread control"
                    )
                else:
                    # Internal thread mode - start our own thread
                    if not self.hk_thread.is_alive():
                        self.hk_thread = threading.Thread(
                            target=self._hk_worker,
                            name=f"HK_{self.device_id}",
                            daemon=True,
                        )
                    self.hk_thread.start()
                    self.logger.info(
                        f"Housekeeping thread started with {self.hk_interval}s interval"
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
            bool: True if stopped successfully, False otherwise.
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
                        self.logger.warning(
                            "Housekeeping thread did not stop cleanly"
                        )
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
            bool: True if cycle completed successfully, False otherwise.
        """
        if not self.hk_running:
            return False

        try:
            if self.connected:
                self.hk_monitor()
                return True
            else:
                self.logger.warning(
                    "Housekeeping cycle skipped: device not connected"
                )
                return False

        except Exception as e:
            self.logger.error(f"Housekeeping cycle error: {e}")
            return False

    def get_status(self) -> dict:
        """
        Get current SW_HR device status.

        Returns:
            Dict: Dictionary containing device status information.
        """
        return {
            "device_id": self.device_id,
            "com": self.com,
            "stream": self.stream_num,
            "baudrate": self.baudrate,
            "connected": self.connected,
            "hk_running": self.hk_running,
            "hk_interval": self.hk_interval,
            "external_thread": self.external_thread,
            "external_lock": self.external_lock,
        }

    # =========================================================================
