#!/usr/bin/env python
"""
Test script to demonstrate chiller logging functionality.
"""

import sys
from pathlib import Path
import logging

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from devices.chiller.chiller import Chiller

def test_chiller_logging():
    """Test automatic file logging when no logger is provided."""
    
    print("🧪 Testing Chiller Logging Functionality")
    print("=" * 50)
    
    # Test 1: Create chiller without custom logger (should create log file)
    print("\n1. Creating chiller WITHOUT custom logger...")
    chiller1 = Chiller("test_chiller_01", "COM3")
    print(f"✅ Created chiller: {chiller1.device_id}")
    print(f"   Logger name: {chiller1.logger.name}")
    print(f"   Log file will be saved in: debugging/logs/")
    
    # Test 2: Create chiller with custom logger
    print("\n2. Creating chiller WITH custom logger...")
    custom_logger = logging.getLogger("custom.chiller.logger")
    chiller2 = Chiller("test_chiller_02", "COM4", logger=custom_logger)
    print(f"✅ Created chiller: {chiller2.device_id}")
    print(f"   Using custom logger: {chiller2.logger.name}")
    
    # Test 3: Demonstrate logging functionality
    print("\n3. Testing logging functionality...")
    
    # This will log to the file
    result1 = chiller1.connect()  # This will fail (no real device) but will log
    print(f"   Connection attempt logged to file")
    
    # This will use the custom logger
    result2 = chiller2.connect()  # This will also fail but use custom logger
    print(f"   Connection attempt using custom logger")
    
    print("\n📁 Check the 'debugging/logs/' folder for the log file!")
    print("   Expected filename format: Chiller_test_chiller_01_YYYYMMDD_HHMMSS.log")

if __name__ == "__main__":
    test_chiller_logging()
