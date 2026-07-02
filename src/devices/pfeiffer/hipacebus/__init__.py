"""
HiPace Bus device module.

This module provides the HiPace300Bus and HiPace80Bus classes for
communicating with Pfeiffer HiPace turbo pumps behind an OmniControl.
The HiPace300Bus class also drives the HiPace450 (same TC400 drive
electronics and parameter set).
"""

from .hipace300bus import HiPace300Bus
from .hipace80bus import HiPace80Bus

__all__ = ["HiPace300Bus", "HiPace80Bus"]
