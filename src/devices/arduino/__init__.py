"""
Arduino device communication module.

This module provides the Arduino base class and specialised subclasses
for the pump-locker and trafo-locker Arduinos.
"""

from .arduino import Arduino
from .pump_arduino import PumpArduino
from .trafo_arduino import TrafoArduino

__all__ = ["Arduino", "PumpArduino", "TrafoArduino"]
