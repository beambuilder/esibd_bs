"""
HiPace300Bus device controller.

This module provides the HiPace300Bus class for communicating with Pfeiffer
HiPace300Bus turbo molecular pumps via serial communication using the 
telegram frame protocol.
"""
from typing import Optional
import logging
import threading

from ..base_device import PfeifferBaseDevice


class HiPace300Bus(PfeifferBaseDevice):
    """
    Pfeiffer HiPace300Bus Turbo Molecular Pump Class.
    
    This class inherits from PfeifferBaseDevice and provides specific functionality
    for controlling HiPace300Bus turbo molecular pumps, including pump control,
    speed monitoring, temperature readings, and status queries.
    
    Example:
        pump = HiPace300Bus("hipace300_01", port="COM7", device_address=1)
        pump.connect()
        pump.start_housekeeping()
        pump.enable_pump()
        pump.disconnect()
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        device_address: int = 1,  # HiPace300Bus standard address
        baudrate: int = 9600,
        timeout: float = 2.0,
        logger: Optional[logging.Logger] = None,
        hk_thread: Optional[threading.Thread] = None,
        thread_lock: Optional[threading.Lock] = None,
        hk_interval: float = 30.0,
        **kwargs,
    ):
        """
        Initialize HiPace300Bus device.

        Args:
            device_id: Unique identifier for the device
            port: Serial port (e.g., 'COM7' on Windows, '/dev/ttyUSB0' on Linux)
            device_address: Pfeiffer device address (1-255, default: 1)
            baudrate: Communication speed (default: 9600)
            timeout: Serial communication timeout in seconds (default: 2.0)
            logger: Optional custom logger. If None, creates file logger in debugging/logs/
            hk_thread: Optional housekeeping thread. If None, creates one automatically
            thread_lock: Optional thread lock. If None, creates one automatically
            hk_interval: Housekeeping monitoring interval in seconds (default: 30.0)
            **kwargs: Additional connection parameters
        """
        super().__init__(
            device_id=device_id,
            port=port,
            device_address=device_address,
            baudrate=baudrate,
            timeout=timeout,
            logger=logger,
            hk_thread=hk_thread,
            thread_lock=thread_lock,
            hk_interval=hk_interval,
            **kwargs
        )
