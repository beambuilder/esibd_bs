"""
TPG366 device module.

This module provides the TPG366 class for communicating with Pfeiffer
TPG366 pressure measurement and control units.
"""

from .tpg366 import TPG366
from .tpg366_tcp import TPG366TCP

__all__ = ["TPG366", "TPG366TCP"]
