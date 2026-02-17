"""
SW (Switch) device controller.

This module provides the SW class for communicating with CGC HV-AMX-CTRL-4ED
switch devices via the SW base hardware interface with added logging functionality.
"""
from typing import Optional
import logging
import threading
from datetime import datetime
from pathlib import Path

from .sw_base import SWBase


class SW(SWBase):
    """
    SW device communication class with logging functionality.

    This class inherits from SWBase and provides logging capabilities,
    device identification, housekeeping thread management, and enhanced
    function call monitoring similar to other devices in the system.

    The HV-AMX-CTRL-4ED is a switch controller that manages 4 high-voltage
    switches with configurable pulsers, digital I/O, and trigger/enable mappings.

    Example:
        sw = SW("main_sw", com=5, port=0)
        sw.connect()
        sw.set_device_enable(True)
        state = sw.get_main_state()
        sw.disconnect()
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
        Initialize SW device with logging and threading support.
        """
        # Store parameters for SW functionality
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
            logger_name = f"SW_{device_id}_{timestamp}"
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
                log_filename = f"SW_{device_id}_{timestamp}.log"
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
                    f"SW logger initialized for device '{device_id}' on COM{com}, port {port}"
                )
                self.logger.info(f"Baudrate: {baudrate}")

        # Initialize the base class
        super().__init__(com=com, port=port, log=None, idn=device_id)

    def connect(self) -> bool:
        """Connect to the SW device."""
        try:
            self.logger.info(
                f"Connecting to SW device {self.device_id} on COM{self.com}, port {self.port_num}"
            )

            # Open port using base class method
            status = self.open_port(self.com, self.port_num)

            if status == self.NO_ERR:
                # Set communication speed
                baud_status, actual_baud = self.set_baud_rate(self.baudrate)
                if baud_status == self.NO_ERR:
                    self.connected = True
                    self.logger.info(
                        f"Successfully connected to SW device {self.device_id} "
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
        """Disconnect from the SW device."""
        try:
            # Stop housekeeping before disconnecting
            self.stop_housekeeping()

            self.logger.info(f"Disconnecting SW device {self.device_id}")

            # Close port using base class method
            status = self.close_port()

            if status == self.NO_ERR:
                self.connected = False
                self.logger.info(
                    f"Successfully disconnected SW device {self.device_id}"
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

    def _hk_main_state(self):
        """Get and log main device state."""
        status, state_hex, state_name = self.get_main_state()
        if status == self.NO_ERR:
            self.logger.debug(f"Main state: {state_name} ({state_hex})")
        return status == self.NO_ERR

    def _hk_device_state(self):
        """Get and log device state."""
        status, state_hex, state_names = self.get_device_state()
        if status == self.NO_ERR:
            self.logger.debug(
                f"Device state: {', '.join(state_names)} ({state_hex})"
            )
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
        status, state_hex, state_names = self.get_controller_state()
        if status == self.NO_ERR:
            self.logger.debug(
                f"Controller state: {', '.join(state_names)} ({state_hex})"
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
        """Get and log oscillator period."""
        status, period = self.get_oscillator_period()
        if status == self.NO_ERR:
            freq = self.CLOCK / (period + self.OSC_OFFSET) if period > 0 else 0
            self.logger.debug(
                f"Oscillator: Period={period}, Frequency={freq:.1f}Hz"
            )
        return status == self.NO_ERR

    def _hk_pulser_data(self):
        """Get and log pulser data for all pulsers."""
        for i in range(self.PULSER_NUM):
            status_d, delay = self.get_pulser_delay(i)
            status_w, width = self.get_pulser_width(i)
            if status_d == self.NO_ERR and status_w == self.NO_ERR:
                self.logger.debug(
                    f"Pulser {i}: Delay={delay}, Width={width}"
                )
        for i in range(self.PULSER_BURST_NUM):
            status_b, burst = self.get_pulser_burst(i)
            if status_b == self.NO_ERR:
                self.logger.debug(f"Pulser {i} Burst: {burst}")
        return True

    def _hk_switch_data(self):
        """Get and log switch configuration for all switches."""
        for i in range(self.SWITCH_NUM):
            status_tc, trig_cfg = self.get_switch_trigger_config(i)
            status_ec, enb_cfg = self.get_switch_enable_config(i)
            status_td, rise_d, fall_d = self.get_switch_trigger_delay(i)
            status_ed, enb_delay = self.get_switch_enable_delay(i)
            if all(
                s == self.NO_ERR
                for s in [status_tc, status_ec, status_td, status_ed]
            ):
                self.logger.debug(
                    f"Switch {i}: TrigCfg=0x{trig_cfg:02X}, EnbCfg=0x{enb_cfg:02X}, "
                    f"TrigDelay(rise={rise_d}, fall={fall_d}), EnbDelay={enb_delay}"
                )
        return True

    def hk_monitor(self):
        """
        Perform housekeeping monitoring of SW device data.
        This method executes all individual housekeeping functions.
        """
        try:
            with self.thread_lock:
                self._hk_product_info()
                self._hk_main_state()
                self._hk_device_state()
                self._hk_general_housekeeping()
                self._hk_sensor_data()
                self._hk_fan_data()
                self._hk_led_data()
                self._hk_controller_state()
                self._hk_cpu_data()
                self._hk_oscillator()
                self._hk_pulser_data()
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
        Get current SW device status.

        Returns:
            Dict: Dictionary containing device status information.
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

    # =========================================================================
    #     Override Key Methods with Logging
    # =========================================================================

    def set_device_enable(self, enable):
        """Set device enable with logging."""
        self.logger.info(f"Setting device enable to {enable}")
        try:
            status = super().set_device_enable(enable)
            if status == self.NO_ERR:
                self.logger.info(f"Device enable set to {enable}")
            else:
                self.logger.error(
                    f"Failed to set device enable: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting device enable: {e}")
            raise

    def set_controller_config(self, config):
        """Set controller configuration with logging."""
        self.logger.info(f"Setting controller config to 0x{config:02X}")
        try:
            status = super().set_controller_config(config)
            if status == self.NO_ERR:
                self.logger.info("Controller config set successfully")
            else:
                self.logger.error(
                    f"Failed to set controller config: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting controller config: {e}")
            raise

    def set_oscillator_period(self, period):
        """Set oscillator period with logging."""
        freq = self.CLOCK / (period + self.OSC_OFFSET) if period > 0 else 0
        self.logger.info(
            f"Setting oscillator period to {period} (~{freq:.1f}Hz)"
        )
        try:
            status = super().set_oscillator_period(period)
            if status == self.NO_ERR:
                self.logger.info("Oscillator period set successfully")
            else:
                self.logger.error(
                    f"Failed to set oscillator period: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting oscillator period: {e}")
            raise

    def set_pulser_delay(self, pulser_no, delay):
        """Set pulser delay with logging."""
        self.logger.info(f"Setting pulser {pulser_no} delay to {delay}")
        try:
            status = super().set_pulser_delay(pulser_no, delay)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Pulser {pulser_no} delay set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set pulser {pulser_no} delay: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting pulser delay: {e}")
            raise

    def set_pulser_width(self, pulser_no, width):
        """Set pulser width with logging."""
        self.logger.info(f"Setting pulser {pulser_no} width to {width}")
        try:
            status = super().set_pulser_width(pulser_no, width)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Pulser {pulser_no} width set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set pulser {pulser_no} width: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting pulser width: {e}")
            raise

    def set_pulser_burst(self, pulser_no, burst):
        """Set pulser burst size with logging."""
        self.logger.info(f"Setting pulser {pulser_no} burst to {burst}")
        try:
            status = super().set_pulser_burst(pulser_no, burst)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Pulser {pulser_no} burst set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set pulser {pulser_no} burst: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting pulser burst: {e}")
            raise

    def set_pulser_config(self, pulser_cfg_no, config):
        """Set pulser configuration with logging."""
        self.logger.info(
            f"Setting pulser config {pulser_cfg_no} to 0x{config:02X}"
        )
        try:
            status = super().set_pulser_config(pulser_cfg_no, config)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Pulser config {pulser_cfg_no} set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set pulser config {pulser_cfg_no}: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting pulser config: {e}")
            raise

    def set_switch_trigger_config(self, switch_no, config):
        """Set switch trigger configuration with logging."""
        self.logger.info(
            f"Setting switch {switch_no} trigger config to 0x{config:02X}"
        )
        try:
            status = super().set_switch_trigger_config(switch_no, config)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Switch {switch_no} trigger config set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set switch {switch_no} trigger config: "
                    f"status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting switch trigger config: {e}")
            raise

    def set_switch_enable_config(self, switch_no, config):
        """Set switch enable configuration with logging."""
        self.logger.info(
            f"Setting switch {switch_no} enable config to 0x{config:02X}"
        )
        try:
            status = super().set_switch_enable_config(switch_no, config)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Switch {switch_no} enable config set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set switch {switch_no} enable config: "
                    f"status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting switch enable config: {e}")
            raise

    def set_switch_trigger_delay(self, switch_no, rise_delay, fall_delay):
        """Set switch trigger delay with logging."""
        self.logger.info(
            f"Setting switch {switch_no} trigger delay: "
            f"rise={rise_delay}, fall={fall_delay}"
        )
        try:
            status = super().set_switch_trigger_delay(
                switch_no, rise_delay, fall_delay
            )
            if status == self.NO_ERR:
                self.logger.info(
                    f"Switch {switch_no} trigger delay set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set switch {switch_no} trigger delay: "
                    f"status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting switch trigger delay: {e}")
            raise

    def set_switch_enable_delay(self, switch_no, delay):
        """Set switch enable delay with logging."""
        self.logger.info(
            f"Setting switch {switch_no} enable delay to {delay}"
        )
        try:
            status = super().set_switch_enable_delay(switch_no, delay)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Switch {switch_no} enable delay set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set switch {switch_no} enable delay: "
                    f"status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting switch enable delay: {e}")
            raise

    def set_switch_trigger_mapping(self, mapping_no, mapping):
        """Set switch trigger mapping with logging."""
        self.logger.info(
            f"Setting switch trigger mapping {mapping_no} to 0x{mapping:02X}"
        )
        try:
            status = super().set_switch_trigger_mapping(mapping_no, mapping)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Switch trigger mapping {mapping_no} set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set switch trigger mapping {mapping_no}: "
                    f"status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting switch trigger mapping: {e}")
            raise

    def set_switch_enable_mapping(self, mapping_no, mapping):
        """Set switch enable mapping with logging."""
        self.logger.info(
            f"Setting switch enable mapping {mapping_no} to 0x{mapping:02X}"
        )
        try:
            status = super().set_switch_enable_mapping(mapping_no, mapping)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Switch enable mapping {mapping_no} set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set switch enable mapping {mapping_no}: "
                    f"status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting switch enable mapping: {e}")
            raise

    def set_switch_trigger_mapping_enable(self, enable):
        """Set switch trigger mapping enable with logging."""
        self.logger.info(f"Setting switch trigger mapping enable to {enable}")
        try:
            status = super().set_switch_trigger_mapping_enable(enable)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Switch trigger mapping enable set to {enable}"
                )
            else:
                self.logger.error(
                    f"Failed to set trigger mapping enable: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting trigger mapping enable: {e}")
            raise

    def set_switch_enable_mapping_enable(self, enable):
        """Set switch enable mapping enable with logging."""
        self.logger.info(f"Setting switch enable mapping enable to {enable}")
        try:
            status = super().set_switch_enable_mapping_enable(enable)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Switch enable mapping enable set to {enable}"
                )
            else:
                self.logger.error(
                    f"Failed to set enable mapping enable: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting enable mapping enable: {e}")
            raise

    def set_input_config(self, output_enable, termination_enable):
        """Set digital I/O configuration with logging."""
        self.logger.info(
            f"Setting input config: OutputEnable=0x{output_enable:02X}, "
            f"TerminationEnable=0x{termination_enable:02X}"
        )
        try:
            status = super().set_input_config(output_enable, termination_enable)
            if status == self.NO_ERR:
                self.logger.info("Input config set successfully")
            else:
                self.logger.error(
                    f"Failed to set input config: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting input config: {e}")
            raise

    def set_output_config(self, output_no, configuration):
        """Set output configuration with logging."""
        self.logger.info(
            f"Setting output {output_no} config to 0x{configuration:02X}"
        )
        try:
            status = super().set_output_config(output_no, configuration)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Output {output_no} config set successfully"
                )
            else:
                self.logger.error(
                    f"Failed to set output {output_no} config: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting output config: {e}")
            raise

    def restart(self):
        """Restart device with logging."""
        self.logger.info("Restarting SW device")
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

    # =========================================================================
    #     Automatic Logging Fallback
    # =========================================================================

    def __getattr__(self, name):
        """
        Automatically wrap base class methods with logging.

        This method is called when an attribute is not found in the current
        class. It will look for the method in the base class and wrap it
        with logging.
        """
        if hasattr(SWBase, name):
            base_method = getattr(SWBase, name)

            if callable(base_method):
                def logged_method(*args, **kwargs):
                    """Wrapper method that adds logging to base class methods."""
                    self.logger.info(
                        f"Calling {name} with args={args[1:]} kwargs={kwargs}"
                    )
                    try:
                        result = base_method(self, *args, **kwargs)

                        if isinstance(result, tuple) and len(result) >= 1:
                            status = result[0]
                            if status == self.NO_ERR:
                                self.logger.info(
                                    f"{name} completed successfully"
                                )
                            else:
                                self.logger.warning(
                                    f"{name} returned status {status}"
                                )
                        else:
                            self.logger.info(f"{name} completed")

                        return result

                    except Exception as e:
                        self.logger.error(f"Error in {name}: {e}")
                        raise

                return logged_method
            else:
                return base_method

        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )
