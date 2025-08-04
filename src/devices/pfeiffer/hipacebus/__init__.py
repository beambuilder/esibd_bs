"""
HiPace Bus device module.

This module provides the TPG366 class for communicating with Pfeiffer
TPG366 pressure measurement and control units.
"""

from .hipace300bus import HiPace300Bus

__all__ = ["HiPace300Bus"]