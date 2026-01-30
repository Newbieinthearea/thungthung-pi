import RPi.GPIO as GPIO
import time

# --- CONFIGURATION ---
SERVO_PIN = 23          # GPIO 23 (Physical Pin 16)
PWM_FREQ = 50           # 50Hz is standard for servos

# MG996R Physical Limits (from your datasheet)
MAX_ANGLE = 90
MIN_ANGLE = -90

# Setup RPi.GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# Start PWM with 0% duty cycle (Motor off)
pwm = GPIO.PWM(SERVO_PIN, PWM_FREQ)
pwm.start(0)

def angle_to_duty_cycle(angle):
    # Standard Servo Formula:
    # 2.5% = -90 deg, 12.5% = +90 deg
    # Formula: Duty = 2.5 + ( (angle + 90) / 180 ) * 10
    duty = 2.5 + ((angle + 90) / 18)
    return duty

print(f"✅ RPi.GPIO Servo Control Started on Pin {SERVO_PIN}")
print(f"   Limit: {MIN_ANGLE}° to {MAX_ANGLE}°")

try:
    while True:
        user_input = input("\nEnter Angle > ")
        
        if user_input.lower() == 'q':
            break
            
        try:
            target_angle = float(user_input)
            
            # 1. SAFETY CHECK
            if MIN_ANGLE <= target_angle <= MAX_ANGLE:
                print(f"   Moving to {target_angle}°...")
                
                # 2. CALCULATE DUTY CYCLE
                duty = angle_to_duty_cycle(target_angle)
                
                # 3. MOVE (Turn signal ON)
                pwm.ChangeDutyCycle(duty)
                
                # 4. WAIT (Allow physical time to travel)
                time.sleep(0.5)
                
                # 5. RELAX (Turn signal OFF to stop shaking)
                # This is the secret to fixing jitter in RPi.GPIO
                pwm.ChangeDutyCycle(0)
                
            else:
                print(f"⚠️  OUT OF BOUNDS! Please stay between {MIN_ANGLE} and {MAX_ANGLE}")
                
        except ValueError:
            print("❌ Invalid number")

except KeyboardInterrupt:
    print("\n👋 Exiting...")

finally:
    # CRITICAL: Always clean up RPi.GPIO or your pins will stay 'busy'
    pwm.stop()
    GPIO.cleanup()
    print("🧹 GPIO Cleaned up.")