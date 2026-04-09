"""
ESI controller device wrapper.

Provides the ESI class for communicating with CGC ESI-CTRL devices via the
ESIBase hardware interface, with added logging and housekeeping support.
"""
from typing import Optional
import logging
import threading
from datetime import datetime
from pathlib import Path

from .esi_base import ESIBase


class ESI(ESIBase):
    """
    ESI controller device class with logging functionality.

    This class inherits from ESIBase and provides logging, device
    identification, housekeeping thread management, and enhanced function-call
    monitoring similar to other CGC devices in the system.

    Note
    ----
    The ESI-CTRL DLL is single-instance: it does not take a port argument, so
    only one ESI controller can be opened per process.

    Example
    -------
    >>> esi = ESI("main_esi", com=7)
    >>> esi.connect()
    >>> esi.set_activation_state(True)
    >>> esi.disconnect()
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
        """Initialize ESI device with logging and threading support."""
        self.device_id = device_id
        self.com = com
        self.baudrate = baudrate
        self.hk_interval = hk_interval

        self.connected = False

        # Housekeeping setup
        self.hk_running = False
        self.hk_stop_event = threading.Event()

        # Internal vs. external thread/lock management
        self.external_thread = hk_thread is not None
        self.external_lock = thread_lock is not None

        self.thread_lock = thread_lock if thread_lock is not None else threading.Lock()
        self.hk_lock = threading.Lock()

        if hk_thread is not None:
            self.hk_thread = hk_thread
        else:
            self.hk_thread = threading.Thread(
                target=self._hk_worker, name=f"HK_{device_id}", daemon=True
            )

        # Logger setup
        if logger is not None:
            adapter = logging.LoggerAdapter(logger, {"device_id": device_id})
            adapter.process = lambda msg, kwargs: (f"{device_id} - {msg}", kwargs)
            self.logger = adapter
            self._external_logger_provided = True
        else:
            self._external_logger_provided = False
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger_name = f"ESI_{device_id}_{timestamp}"
            self.logger = logging.getLogger(logger_name)

            if not self.logger.handlers:
                logs_dir = (
                    Path(__file__).parent.parent.parent.parent.parent
                    / "debugging" / "logs"
                )
                logs_dir.mkdir(parents=True, exist_ok=True)

                log_filename = f"ESI_{device_id}_{timestamp}.log"
                log_filepath = logs_dir / log_filename

                file_handler = logging.FileHandler(log_filepath)
                formatter = logging.Formatter(
                    f"%(asctime)s - {device_id} - %(levelname)s - %(message)s"
                )
                file_handler.setFormatter(formatter)

                self.logger.addHandler(file_handler)
                self.logger.setLevel(logging.DEBUG)

                self.logger.info(
                    f"ESI logger initialized for device '{device_id}' on COM{com}"
                )
                self.logger.info(f"Baudrate: {baudrate}")

        # Initialize base class
        super().__init__(com=com, log=None, idn=device_id)

    # =========================================================================
    #     Connection
    # =========================================================================

    def connect(self) -> bool:
        """Connect to the ESI controller."""
        try:
            self.logger.info(
                f"Connecting to ESI device {self.device_id} on COM{self.com}"
            )
            status = self.open_port(self.com)

            if status == self.NO_ERR:
                baud_status, actual_baud = self.set_comspeed(self.baudrate)
                if baud_status == self.NO_ERR:
                    self.connected = True
                    self.logger.info(
                        f"Successfully connected to ESI device {self.device_id} "
                        f"(baud rate: {actual_baud})"
                    )
                    return True
                self.logger.error(f"Failed to set baud rate: status {baud_status}")
                return False
            self.logger.error(f"Failed to open port: status {status}")
            return False
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            return False

    def disconnect(self) -> bool:
        """Disconnect from the ESI controller."""
        try:
            self.stop_housekeeping()
            self.logger.info(f"Disconnecting ESI device {self.device_id}")
            status = self.close_port()
            if status == self.NO_ERR:
                self.connected = False
                self.logger.info(
                    f"Successfully disconnected ESI device {self.device_id}"
                )
                return True
            self.logger.error(f"Failed to close port: status {status}")
            return False
        except Exception as e:
            self.logger.error(f"Disconnection error: {e}")
            return False

    # =========================================================================
    #     Housekeeping worker
    # =========================================================================

    def _hk_worker(self):
        """Internal housekeeping worker thread function."""
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

    # =========================================================================
    #     Individual housekeeping functions
    # =========================================================================

    def _hk_product_info(self):
        status, product_no = self.get_product_no()
        if status == self.NO_ERR:
            self.logger.info(f"Product number: {product_no}")
        return status == self.NO_ERR

    def _hk_main_state(self):
        status, state_hex, state_name = self.get_main_state()
        if status == self.NO_ERR:
            self.logger.info(f"Main state: {state_name} ({state_hex})")
        return status == self.NO_ERR

    def _hk_device_state(self):
        status, state_hex, state_names = self.get_device_state()
        if status == self.NO_ERR:
            self.logger.info(
                f"Device state: {', '.join(state_names)} ({state_hex})"
            )
        return status == self.NO_ERR

    def _hk_voltage_state(self):
        status, state_hex, state_names = self.get_voltage_state()
        if status == self.NO_ERR:
            self.logger.info(
                f"Voltage state: {', '.join(state_names) or 'NONE'} ({state_hex})"
            )
        return status == self.NO_ERR

    def _hk_temperature_state(self):
        status, state_hex, state_names = self.get_temperature_state()
        if status == self.NO_ERR:
            self.logger.info(
                f"Temperature state: {', '.join(state_names) or 'NONE'} ({state_hex})"
            )
        return status == self.NO_ERR

    def _hk_fan_state(self):
        status, state_hex, state_names = self.get_fan_state()
        if status == self.NO_ERR:
            self.logger.info(
                f"Fan state: {', '.join(state_names) or 'NONE'} ({state_hex})"
            )
        return status == self.NO_ERR

    def _hk_interlock_state(self):
        status, state_hex, state_names = self.get_interlock_state()
        if status == self.NO_ERR:
            self.logger.info(
                f"Interlock state: {', '.join(state_names) or 'NONE'} ({state_hex})"
            )
        return status == self.NO_ERR

    def _hk_general_housekeeping(self):
        status, v24, v5, v3, tcpu, tpsu = self.get_housekeeping()
        if status == self.NO_ERR:
            self.logger.info("get_housekeeping() results:")
            self.logger.info(f"  24V Supply: {v24:.2f}V")
            self.logger.info(f"  5V Supply:  {v5:.2f}V")
            self.logger.info(f"  3.3V Supply:{v3:.2f}V")
            self.logger.info(f"  CPU Temp:   {tcpu:.1f}degC")
            self.logger.info(f"  PSU Temp:   {tpsu:.1f}degC")
        return status == self.NO_ERR

    def _hk_cpu_data(self):
        status, load, freq = self.get_cpu_data()
        if status == self.NO_ERR:
            self.logger.info(
                f"CPU: Load={load * 100:.1f}%, Frequency={freq / 1e6:.1f}MHz"
            )
        return status == self.NO_ERR

    def _hk_fan_data(self):
        status, failed, max_rpm, set_rpm, meas_rpm, pwm = self.get_fan_data()
        if status == self.NO_ERR:
            self.logger.info(
                f"Fan: Failed={failed}, MaxRPM={max_rpm}, SetRPM={set_rpm}, "
                f"MeasRPM={meas_rpm}, PWM={pwm:.2f}"
            )
        return status == self.NO_ERR

    def _hk_led_data(self):
        status, red, green, blue = self.get_led_data()
        if status == self.NO_ERR:
            self.logger.info(f"LED state: R={red}, G={green}, B={blue}")
        return status == self.NO_ERR

    def _hk_heat_ctrl_monitoring(self):
        status, valid, vout, vmon, imon, tmon = self.get_heat_ctrl_monitoring()
        if status == self.NO_ERR and valid:
            self.logger.info(
                f"HeatCtrl: Vout={vout:.2f}V, Vmon={vmon:.2f}V, "
                f"Imon={imon:.3f}A, Tmon={tmon:.1f}degC"
            )
        return status == self.NO_ERR

    def _hk_modules(self):
        status, valid, max_mod, presence = self.get_module_presence()
        if status == self.NO_ERR:
            self.logger.info(
                f"Modules: valid={valid}, max={max_mod}, presence={presence}"
            )
            # Log HV-PSU module data for any present HV supply modules
            for address in range(self.MODULE_NUM):
                if presence[address] != self.MODULE_PRESENT:
                    continue
                st_v, valid_v, voltage = self.get_hv_supply_output_voltage(address)
                st_i, valid_i, current = self.get_hv_supply_output_current(address)
                if st_v == self.NO_ERR and st_i == self.NO_ERR:
                    self.logger.info(
                        f"HV module {address}: V={voltage:.2f}V (valid={valid_v}), "
                        f"I={current:.3e}A (valid={valid_i})"
                    )
        return status == self.NO_ERR

    def hk_monitor(self):
        """Perform one full housekeeping cycle."""
        try:
            with self.thread_lock:
                self._hk_product_info()
                self._hk_main_state()
                self._hk_device_state()
                self._hk_voltage_state()
                self._hk_temperature_state()
                self._hk_fan_state()
                self._hk_interlock_state()
                self._hk_general_housekeeping()
                self._hk_cpu_data()
                self._hk_fan_data()
                self._hk_led_data()
                self._hk_heat_ctrl_monitoring()
                self._hk_modules()
        except Exception as e:
            self.logger.error(f"Housekeeping monitoring failed: {e}")

    # =========================================================================
    #     Housekeeping control
    # =========================================================================

    def start_housekeeping(self, interval=-1, log_to_file=True) -> bool:
        """Start housekeeping monitoring (internal or external thread mode)."""
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
                    self.logger.info(
                        "Housekeeping enabled for external thread control"
                    )
                else:
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
        """Stop housekeeping monitoring."""
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
        """Perform one housekeeping cycle (for external thread use)."""
        if not self.hk_running:
            return False
        try:
            if self.connected:
                self.hk_monitor()
                return True
            self.logger.warning(
                "Housekeeping cycle skipped: device not connected"
            )
            return False
        except Exception as e:
            self.logger.error(f"Housekeeping cycle error: {e}")
            return False

    def get_status(self) -> dict:
        """Return current ESI device status."""
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

    # =========================================================================
    #     Logged overrides of key setters
    # =========================================================================

    def set_activation_state(self, activation_state):
        """Set device activation state with logging."""
        self.logger.info(f"Setting device activation state to {activation_state}")
        try:
            status = super().set_activation_state(activation_state)
            if status == self.NO_ERR:
                self.logger.info(f"Activation state set to {activation_state}")
            else:
                self.logger.error(f"Failed to set activation state: status {status}")
            return status
        except Exception as e:
            self.logger.error(f"Error setting activation state: {e}")
            raise

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

    def set_interlock_enable(self, interlock_enable):
        """Set interlock enable mask with logging."""
        self.logger.info(f"Setting interlock enable mask to 0x{interlock_enable:02X}")
        try:
            status = super().set_interlock_enable(interlock_enable)
            if status == self.NO_ERR:
                self.logger.info("Interlock enable mask set successfully")
            else:
                self.logger.error(
                    f"Failed to set interlock enable mask: status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting interlock enable mask: {e}")
            raise

    def set_hv_supply_target_output_voltage(self, address, voltage):
        """Set HV-PSU target output voltage with logging."""
        self.logger.info(
            f"Setting HV module {address} target voltage to {voltage:.2f}V"
        )
        try:
            status = super().set_hv_supply_target_output_voltage(address, voltage)
            if status == self.NO_ERR:
                self.logger.info(
                    f"HV module {address} target voltage set to {voltage:.2f}V"
                )
            else:
                self.logger.error(
                    f"Failed to set HV module {address} target voltage: "
                    f"status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting HV supply target voltage: {e}")
            raise

    def set_module_activation_state(self, address, activation_state):
        """Set module activation state with logging."""
        self.logger.info(
            f"Setting module {address} activation state to {activation_state}"
        )
        try:
            status = super().set_module_activation_state(address, activation_state)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Module {address} activation state set to {activation_state}"
                )
            else:
                self.logger.error(
                    f"Failed to set module {address} activation state: "
                    f"status {status}"
                )
            return status
        except Exception as e:
            self.logger.error(f"Error setting module activation state: {e}")
            raise

    def set_heat_ctrl_heater_temperature(self, heater_temp):
        """Set heat controller heater temperature with logging."""
        self.logger.info(f"Setting heat-ctrl heater temperature to {heater_temp:.1f}degC")
        try:
            status, actual = super().set_heat_ctrl_heater_temperature(heater_temp)
            if status == self.NO_ERR:
                self.logger.info(
                    f"Heat-ctrl heater temperature set (actual={actual:.1f}degC)"
                )
            else:
                self.logger.error(
                    f"Failed to set heater temperature: status {status}"
                )
            return status, actual
        except Exception as e:
            self.logger.error(f"Error setting heater temperature: {e}")
            raise

    def restart(self):
        """Restart ESI controller with logging."""
        self.logger.info("Restarting ESI controller")
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
    #     Automatic logging fallback
    # =========================================================================

    def __getattr__(self, name):
        """Automatically wrap ESIBase methods with logging."""
        if hasattr(ESIBase, name):
            base_method = getattr(ESIBase, name)
            if callable(base_method):
                def logged_method(*args, **kwargs):
                    self.logger.info(
                        f"Calling {name} with args={args} kwargs={kwargs}"
                    )
                    try:
                        result = base_method(self, *args, **kwargs)
                        if isinstance(result, tuple) and len(result) >= 1:
                            status = result[0]
                            if status == self.NO_ERR:
                                self.logger.info(f"{name} completed successfully")
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
            return base_method
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )
