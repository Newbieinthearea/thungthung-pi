import RPi.GPIO as GPIO
import time

# Use the Broadcom pin mode
GPIO.setmode(GPIO.BCM)

# PIN CONFIGURATION
SENSOR_PIN = 26

# We use PUD_UP to help pull the voltage up slightly 
# This might boost your 1.7V to a safer level for "High"
GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("-----------------------------------")
print("🕵️  SENSOR TEST RUNNING")
print("   Connect Sensor to GPIO 26")
print("   Press Ctrl+C to stop")
print("-----------------------------------")

try:
    while True:
        # Read the pin state
        # 0 (LOW)  = Current flows to ground -> METAL DETECTED
        # 1 (HIGH) = Voltage stays up      -> CLEAR / NO METAL
        input_state = GPIO.input(SENSOR_PIN)
        
        if input_state == 0:
            print("✅ METAL DETECTED! (Signal 0)")
        else:
            print("... clear (Signal 1)")
            
        time.sleep(0.2)

except KeyboardInterrupt:
    print("\n👋 Exiting.")
    GPIO.cleanup()