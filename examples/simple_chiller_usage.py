#!/usr/bin/env python3
"""
Simple examples showing how to use the Chiller class in both threading modes.
"""

import threading
import time
from src.devices.chiller.chiller import Chiller


def example_1_debugging_mode():
    """
    Example 1: Simple debugging mode (no thread passed)
    The chiller class automatically creates and manages its own thread.
    """
    print("=== Example 1: Debugging Mode (Internal Thread) ===")
    
    # Create chiller without passing any thread - automatic mode
    chiller = Chiller(device_id="DEBUG_CHILLER", port="COM3")
    
    try:
        # Connect and start housekeeping - everything is automatic
        if chiller.connect():
            print("✅ Connected to chiller")
            
            # Start housekeeping - thread is created automatically
            chiller.start_housekeeping(interval=5, log_to_file=True)
            print("🔄 Housekeeping started automatically")
            
            # You can still use all read/set functions normally
            # They work alongside the automatic housekeeping thread
            for i in range(3):
                try:
                    temp = chiller.read_temp()
                    set_temp = chiller.read_set_temp()
                    print(f"📊 Manual read {i+1}: Current={temp}°C, Set={set_temp}°C")
                    time.sleep(2)
                except Exception as e:
                    print(f"❌ Read error: {e}")
            
            # Stop housekeeping and disconnect
            chiller.stop_housekeeping()
            chiller.disconnect()
            print("⏹️ Stopped and disconnected")
            
    except Exception as e:
        print(f"❌ Error in debugging mode: {e}")


def example_2_external_thread_mode():
    """
    Example 2: External thread mode with continuous housekeeping
    You manage the thread, but can still use read/set functions normally.
    """
    print("\n=== Example 2: External Thread Mode ===")
    
    # Create external thread and lock
    external_thread = threading.Thread(name="MyChillerThread")
    external_lock = threading.Lock()
    
    # Create chiller with external thread management
    chiller = Chiller(
        device_id="EXTERNAL_CHILLER", 
        port="COM3",
        hk_thread=external_thread,  # Pass your thread
        thread_lock=external_lock   # Pass your lock
    )
    
    try:
        if chiller.connect():
            print("✅ Connected to chiller")
            
            # Enable housekeeping (doesn't start a thread, just enables it)
            chiller.start_housekeeping(interval=3, log_to_file=True)
            print("✅ Housekeeping enabled for external control")
            
            # Your external thread function
            def my_housekeeping_loop():
                print("🧵 External thread started")
                
                while chiller.should_continue_housekeeping():
                    # Easy housekeeping cycle
                    chiller.do_housekeeping_cycle()
                    
                    # Wait for interval
                    time.sleep(chiller.hk_interval)
                
                print("🧵 External thread finished")
            
            # Start your external thread
            my_thread = threading.Thread(
                target=my_housekeeping_loop,
                name="MyChillerThread",
                daemon=True
            )
            my_thread.start()
            
            # Meanwhile, you can still use read/set functions normally
            # The thread lock ensures everything works safely together
            for i in range(5):
                try:
                    # These work normally alongside the external housekeeping thread
                    status = chiller.read_status()
                    running = chiller.read_running()
                    print(f"📊 Manual check {i+1}: Status={status}, Running={running}")
                    time.sleep(2)
                except Exception as e:
                    print(f"❌ Read error: {e}")
            
            # Stop everything
            chiller.stop_housekeeping()
            my_thread.join(timeout=5)
            chiller.disconnect()
            print("⏹️ Stopped and disconnected")
            
    except Exception as e:
        print(f"❌ Error in external thread mode: {e}")


def example_3_mixed_usage():
    """
    Example 3: Shows how read/set functions work normally in both modes
    """
    print("\n=== Example 3: Normal Usage in Both Modes ===")
    
    for mode_name, use_external in [("Internal", False), ("External", True)]:
        print(f"\n--- {mode_name} Thread Mode ---")
        
        if use_external:
            # External mode
            chiller = Chiller(
                device_id=f"{mode_name}_CHILLER", 
                port="COM3",
                hk_thread=threading.Thread(name="ExternalThread"),
                thread_lock=threading.Lock()
            )
        else:
            # Internal mode
            chiller = Chiller(device_id=f"{mode_name}_CHILLER", port="COM3")
        
        try:
            if chiller.connect():
                # Start housekeeping
                chiller.start_housekeeping(interval=10)
                
                # Normal usage - read/set functions work the same in both modes
                print("📋 Testing normal functions...")
                
                # Read functions work normally
                try:
                    temp = chiller.read_temp()
                    pump_level = chiller.read_pump_level()
                    print(f"   Current temp: {temp}°C, Pump level: {pump_level}")
                except Exception as e:
                    print(f"   Read functions simulated (no hardware): {e}")
                
                # Set functions work normally
                try:
                    chiller.set_temperature(25.0)
                    chiller.set_pump_level(3)
                    print("   Set functions completed")
                except Exception as e:
                    print(f"   Set functions simulated (no hardware): {e}")
                
                # Stop and disconnect
                chiller.stop_housekeeping()
                chiller.disconnect()
                print(f"✅ {mode_name} mode completed successfully")
                
        except Exception as e:
            print(f"❌ Error in {mode_name} mode: {e}")


if __name__ == "__main__":
    print("🚀 Chiller Threading Examples - Simplified")
    print("=" * 60)
    
    # Note: These examples assume you have a chiller on COM3
    # Comment out hardware-specific lines if testing without hardware
    
    # Uncomment to run examples:
    # example_1_debugging_mode()
    # example_2_external_thread_mode() 
    # example_3_mixed_usage()
    
    print("\n📋 Summary:")
    print("1. Internal mode: Just create Chiller() - everything automatic")
    print("2. External mode: Pass hk_thread + thread_lock to __init__")
    print("3. Both modes: start_housekeeping() + use read/set functions normally")
    print("4. External control: Use do_housekeeping_cycle() and should_continue_housekeeping()")
    print("5. All read/set functions work identically in both modes!")
