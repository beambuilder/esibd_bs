"""
ESIBD Lab Device Management System.

This package provides device-specific communication protocols and control
interfaces for various laboratory instruments and devices.
"""

from .devices.arduino import Arduino
from .devices.chiller import Chiller

__version__ = "0.1.0"
__author__ = "Niclas Przybylla"
__all__ = ['Arduino', 'Chiller']
