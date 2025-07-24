"""
Chiller device controller.

This module provides the Chiller class for communicating with temperature
control and chilling systems via various communication protocols.
"""

from typing import Any, Dict, Optional, Union
import logging

import serial


class Chiller:
    """
    Chiller (Lauda) device communication class.
    
    This class handles communication with chiller devices, providing
    methods for temperature control, monitoring, and system management.
    
    Example:
        chiller = Chiller("main_chiller", communication_type="serial", port="COM4")
        chiller.connect()
        chiller.set_temperature(20.0)
        temp = chiller.get_temperature()
        chiller.disconnect()
    """
    
    def __init__(
        self,
        device_id: str,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.0,
        **kwargs,
    ):
        """
        Initialize Chiller device.
        
        Args:
            device_id: Unique identifier for the chiller
            communication_type: Type of communication ('serial', 'ethernet', 'usb')
            **connection_params: Communication-specific parameters
        """
        self.device_id = device_id
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_connected = False
        self.serial_connection: Optional[serial.Serial] = None
        self.current_temperature: Optional[float] = None
        self.target_temperature: Optional[float] = None
        self.is_cooling: bool = False
        self.logger = logging.getLogger(f"Chiller_{device_id}")
        
    def connect(self) -> bool:
        """
        Establish connection to the chiller.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.logger.info(f"Connecting to chiller {self.device_id} on {self.port}")
            self.serial_connection = serial.Serial(
                self.port, self.baudrate, timeout=self.timeout
            )
            self.is_connected = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to chiller: {e}")
            return False
    
    def disconnect(self) -> bool:
        """
        Disconnect from the chiller.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        try:
            if self.serial_connection:
                self.serial_connection.close()
            self.is_connected = False
            self.logger.info(f"Disconnected from chiller {self.device_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disconnect from chiller: {e}")
            return False
