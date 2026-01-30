from gpiozero import AngularServo
from time import sleep

# --- CONFIGURATION ---
# We use GPIO 23 (Physical Pin 16)
SERVO_PIN = 23


# MG996R Motors need a specific pulse range to move full 180 degrees
# If it buzzes at the edges, we can adjust these numbers later.
MIN_PULSE = 0.0005
MAX_PULSE = 0.0025

print(f"🔌 Connecting to Servo on GPIO {SERVO_PIN}...")

try:
    # Setup the servo
    servo = AngularServo(
        SERVO_PIN,
        min_angle=-90,
        max_angle=90,
        min_pulse_width=MIN_PULSE,
        max_pulse_width=MAX_PULSE
    )
    
    print("✅ Servo Ready!")
    print("Type an angle between -90 and 90 (or 'q' to quit)")
    print("-" * 30)

    while True:
        # Ask user for angle
        user_input = input("Enter Angle > ")
        
        if user_input.lower() == 'q':
            break
            
        try:
            angle = float(user_input)
            
            # Check if angle is safe
            if -90 <= angle <= 90:
                print(f"   Moving to {angle}°...")
                servo.angle = angle
                sleep(0.5) # Wait for it to move
                servo.value = None # Stop sending signal (stops buzzing)
            else:
                print("⚠️  Please keep between -90 and 90")
                
        except ValueError:
            print("❌ Please enter a number")

except KeyboardInterrupt:
    print("\n👋 Exiting...")

finally:
    servo.close()