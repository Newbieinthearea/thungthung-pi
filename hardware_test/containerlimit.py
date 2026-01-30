import RPi.GPIO as GPIO
import time

# --- PIN CONFIGURATION ---
TRIG = 23  # Physical Pin 16
ECHO = 24  # Physical Pin 18

# IMPORTANT: Measure your container from sensor to bottom and put value here!
BIN_HEIGHT = 30 # cm

# Setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

def get_distance():
    # 1. Trigger the sensor
    GPIO.output(TRIG, False)
    time.sleep(0.1)
    
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    # 2. Wait for Echo
    pulse_start = time.time()
    pulse_end = time.time()
    timeout = time.time() + 0.1

    # Wait for signal to rise
    while GPIO.input(ECHO) == 0:
        pulse_start = time.time()
        if pulse_start > timeout: return None

    # Wait for signal to fall
    while GPIO.input(ECHO) == 1:
        pulse_end = time.time()
        if pulse_end > timeout: return None

    # 3. Calculate Distance
    duration = pulse_end - pulse_start
    distance = duration * 17150
    return distance

try:
    print(f"--- Trash Monitor Started ---")
    print(f"Container Depth: {BIN_HEIGHT} cm")
    print(f"Trig: GPIO{TRIG} | Echo: GPIO{ECHO}")
    print("-----------------------------")
    
    while True:
        dist = get_distance()
        
        if dist is not None:
            # Filter out crazy values (e.g. if sensor says 2000cm)
            if dist > 400: 
                dist = BIN_HEIGHT 

            # Calculate Fill %
            # If distance is small -> Bin is FULL
            # If distance is large -> Bin is EMPTY
            
            # Clamp values to 0 and BIN_HEIGHT
            valid_dist = max(0, min(dist, BIN_HEIGHT))
            
            fill_amount = BIN_HEIGHT - valid_dist
            percent_full = (fill_amount / BIN_HEIGHT) * 100
            
            # Status Message
            if percent_full > 90:
                status = "🔴 FULL!"
            elif percent_full < 10:
                status = "🟢 Empty"
            else:
                status = "🟡 In Use"

            # Print readable output
            print(f"Distance: {dist:.1f}cm | Full: {percent_full:.0f}% | {status}")
            
        else:
            print("⚠️ Sensor Timeout - Check VCC/GND wires")
            
        time.sleep(1)

except KeyboardInterrupt:
    print("\nCleaning up...")
    GPIO.cleanup()