import RPi.GPIO as GPIO
import time
from hx711 import HX711

# --- NEW PIN CONFIGURATION ---
# DT is now on Pin 16 (GPIO 23)
# SCK is now on Pin 18 (GPIO 24)
hx = HX711(23, 24)

print("Starting Diagnostic on NEW PINS (16 & 18)...")
print("Press Ctrl+C to stop.")

hx.reset()

try:
    while True:
        # Read raw bytes
        val = hx.read_long()
        
        if val is not None:
            # If we get a valid reading, print it
            print(f"Raw Value: {val}")
        else:
            # -1 or None usually means the sensor is not responding
            print("Raw Value: Timeout (Check wires)")
            
        time.sleep(0.3)

except KeyboardInterrupt:
    print("\nCleaning up...")
    GPIO.cleanup()