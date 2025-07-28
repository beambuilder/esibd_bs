#!/usr/bin/env python3
"""
Example demonstrating how to use the Chiller class with external thread management.
This shows both internal (automatic) and external (manual) thread management approaches.
"""

import threading
import time
from src.devices.chiller.chiller import Chiller


def example_internal_thread_management():
    """
    Example of using the chiller with internal thread management (automatic/easy mode).
    """
    print("=== Internal Thread Management Example ===")
    
    # Create chiller with automatic thread management
    chiller = Chiller(device_id="CHILLER1", port="COM3")
    
    try:
        # Connect to the chiller
        if chiller.connect():
            print("✅ Connected to chiller")
            
            # Start housekeeping with automatic thread management
            # This is the "easy as possible" approach
            if chiller.start_housekeeping(interval=5, log_to_file=True):
                print("✅ Housekeeping started automatically")
                
                # Let it run for a while
                print("🔄 Letting housekeeping run for 20 seconds...")
                time.sleep(20)
                
                # Stop housekeeping
                chiller.stop_housekeeping()
                print("⏹️ Housekeeping stopped")
            
            # Disconnect
            chiller.disconnect()
            print("🔌 Disconnected from chiller")
            
    except Exception as e:
        print(f"❌ Error in internal thread example: {e}")


def example_external_thread_management():
    """
    Example of using the chiller with external thread management (manual/advanced mode).
    """
    print("\n=== External Thread Management Example ===")
    
    # Create external thread and lock objects
    external_thread = threading.Thread(name="MyCustomChillerThread")
    external_lock = threading.Lock()
    
    # Create chiller with external thread management
    chiller = Chiller(
        device_id="CHILLER2", 
        port="COM3",
        external_thread=external_thread,
        external_lock=external_lock
    )
    
    try:
        # Connect to the chiller
        if chiller.connect():
            print("✅ Connected to chiller")
            
            # Start housekeeping (this just enables it, doesn't start a thread)
            if chiller.start_housekeeping(interval=3, log_to_file=True):
                print("✅ Housekeeping enabled for external management")
                
                # Manual housekeeping loop in our own thread
                def housekeeping_worker():
                    print("🧵 External thread started")
                    
                    while chiller.should_continue_housekeeping():
                        # Perform a housekeeping cycle - this is the "easy" method
                        if chiller.do_housekeeping_cycle():
                            print("📊 Housekeeping cycle completed")
                        
                        # Wait for the interval
                        time.sleep(chiller.hk_interval)
                    
                    print("🧵 External thread finished")
                
                # Start our external thread
                external_thread = threading.Thread(
                    target=housekeeping_worker,
                    name="MyCustomChillerThread",
                    daemon=True
                )
                external_thread.start()
                
                # Let it run for a while
                print("🔄 Letting external housekeeping run for 15 seconds...")
                time.sleep(15)
                
                # Stop housekeeping
                chiller.stop_housekeeping()
                print("⏹️ Housekeeping stopped")
                
                # Wait for our thread to finish
                external_thread.join(timeout=5)
            
            # Disconnect
            chiller.disconnect()
            print("🔌 Disconnected from chiller")
            
    except Exception as e:
        print(f"❌ Error in external thread example: {e}")


def example_mixed_usage():
    """
    Example showing how you can switch between internal and external thread management.
    """
    print("\n=== Mixed Usage Example ===")
    
    # Start with internal thread management
    chiller = Chiller(device_id="CHILLER3", port="COM3")
    
    try:
        if chiller.connect():
            print("✅ Connected to chiller")
            
            # Use internal thread management first
            print("📍 Phase 1: Using internal thread management")
            chiller.start_housekeeping(interval=2)
            time.sleep(8)
            chiller.stop_housekeeping()
            
            # Switch to external thread management
            print("📍 Phase 2: Switching to external thread management")
            external_lock = threading.Lock()
            
            # Update the chiller to use external management
            chiller.hk_lock = external_lock
            chiller.external_lock = True
            chiller.external_thread = True
            
            # Enable housekeeping for external management
            chiller.start_housekeeping(interval=1)
            
            # Quick external loop
            for i in range(5):
                if chiller.should_continue_housekeeping():
                    chiller.do_housekeeping_cycle()
                    time.sleep(1)
            
            chiller.stop_housekeeping()
            chiller.disconnect()
            print("✅ Mixed usage example completed")
            
    except Exception as e:
        print(f"❌ Error in mixed usage example: {e}")


if __name__ == "__main__":
    print("🚀 Chiller Threading Examples")
    print("=" * 50)
    
    # Note: These examples assume you have a chiller connected on COM3
    # Modify the port as needed for your setup
    
    # Run the examples (comment out if you don't have hardware)
    # example_internal_thread_management()
    # example_external_thread_management()
    # example_mixed_usage()
    
    print("\n📋 Summary:")
    print("• Internal thread management: chiller.start_housekeeping() - automatic and easy")
    print("• External thread management: Use external_thread/external_lock parameters")
    print("• Easy external monitoring: chiller.do_housekeeping_cycle() and chiller.should_continue_housekeeping()")
    print("• Logging is automatically handled in both modes - 'as easy as possible'!")
