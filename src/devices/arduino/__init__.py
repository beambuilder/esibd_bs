"""
Arduino device communication module.

This module provides the Arduino base class and specialised subclasses
for the pump-locker and trafo-locker Arduinos (serial), plus the
DT-670 depo-stage temperature Arduino (Ethernet/HTTP).
"""

from .arduino import Arduino
from .dt670_arduino import DT670Arduino
from .pump_arduino import PumpArduino
from .trafo_arduino import TrafoArduino

__all__ = ["Arduino", "DT670Arduino", "PumpArduino", "TrafoArduino"]
