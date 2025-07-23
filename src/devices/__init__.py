"""
Device management package for laboratory equipment.

This package provides device-specific communication protocols and control
interfaces for various laboratory instruments and devices.
"""

from .arduino.arduino import Arduino
from .chiller.chiller import Chiller

__all__ = ['Arduino', 'Chiller']
