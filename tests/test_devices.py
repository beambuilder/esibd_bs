"""
Unit tests for device classes.
"""

import unittest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devices.arduino.arduino import Arduino
from devices.chiller.chiller import Chiller


class TestArduino(unittest.TestCase):
    """Test cases for Arduino device class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.arduino = Arduino("test_arduino", port="COM3", baudrate=9600)
    
    def test_init(self):
        """Test Arduino initialization."""
        self.assertEqual(self.arduino.device_id, "test_arduino")
        self.assertEqual(self.arduino.port, "COM3")
        self.assertEqual(self.arduino.baudrate, 9600)
        self.assertFalse(self.arduino.is_connected)
    
    def test_get_status(self):
        """Test get_status method."""
        status = self.arduino.get_status()
        self.assertIn("device_id", status)
        self.assertIn("port", status)
        self.assertIn("connected", status)
        self.assertEqual(status["device_id"], "test_arduino")
        self.assertEqual(status["port"], "COM3")
    
    # Add more tests as implementation is completed


class TestChiller(unittest.TestCase):
    """Test cases for Chiller device class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.chiller = Chiller("test_chiller", communication_type="serial", port="COM4")
    
    def test_init(self):
        """Test Chiller initialization."""
        self.assertEqual(self.chiller.device_id, "test_chiller")
        self.assertEqual(self.chiller.communication_type, "serial")
        self.assertIn("port", self.chiller.connection_params)
        self.assertFalse(self.chiller.is_connected)
    
    def test_get_status(self):
        """Test get_status method."""
        status = self.chiller.get_status()
        self.assertIn("device_id", status)
        self.assertIn("communication_type", status)
        self.assertIn("connected", status)
        self.assertEqual(status["device_id"], "test_chiller")
        self.assertEqual(status["communication_type"], "serial")
    
    def test_multiple_instances(self):
        """Test creating multiple chiller instances."""
        chiller1 = Chiller("chiller_01", communication_type="serial", port="COM4")
        chiller2 = Chiller("chiller_02", communication_type="ethernet", ip="192.168.1.100")
        
        self.assertNotEqual(chiller1.device_id, chiller2.device_id)
        self.assertEqual(chiller1.communication_type, "serial")
        self.assertEqual(chiller2.communication_type, "ethernet")
    
    # Add more tests as implementation is completed


if __name__ == '__main__':
    unittest.main()
