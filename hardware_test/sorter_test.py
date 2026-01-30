import RPi.GPIO as GPIO
import time

# --- CONFIGURATION ---
SERVO_PIN = 23
PWM_FREQ = 50 

# ANGLES
IDLE_ANGLE = 0
SLAP_ANGLE = 90# You confirmed 90 works with the manual script

# TIMING
# 0.3s is enough for 90 degrees (MG996R is fast). 
# If it doesn't reach 90 fully, increase this to 0.4.
MOVE_TIME = 0.5 

GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)
pwm = GPIO.PWM(SERVO_PIN, PWM_FREQ)
pwm.start(0)

def angle_to_duty_cycle(angle):
    # The EXACT formula from your working manual_servo.py
    duty = 2.5 + ((angle + 90) / 18)
    return duty

def move_servo(angle):
    # 1. Calculate Duty
    duty = angle_to_duty_cycle(angle)
    
    # 2. Move
    pwm.ChangeDutyCycle(duty)
    
    # 3. Wait for physical travel
    time.sleep(MOVE_TIME)
    
    # 4. Cut power to stop shaking (The "Secret")
    pwm.ChangeDutyCycle(0)

def slap():
    print(f"   👋 Slapping! (0° -> {SLAP_ANGLE}° -> 0°)")
    
    # Swing Out to 90
    move_servo(SLAP_ANGLE)
    
    # Swing Back to 0
    move_servo(IDLE_ANGLE)

try:
    print("✅ Sorter Test Ready")
    print(f"   Idle: {IDLE_ANGLE}°, Slap: {SLAP_ANGLE}°")
    
    # Reset to 0 immediately on start
    move_servo(IDLE_ANGLE)

    while True:
        item = input("\nScan Item > ").lower().strip()
        
        if item in ["plastic", "can"]:
            slap()
        elif item == "q":
            break
        else:
            print("   (Ignored)")

except KeyboardInterrupt:
    print("\n👋 Exiting...")

finally:
    pwm.stop()
    GPIO.cleanup()