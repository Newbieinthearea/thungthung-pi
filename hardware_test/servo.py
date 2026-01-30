from gpiozero import AngularServo
from time import sleep

# UPDATE: New gpiozero uses 'min_pulse_width' instead of 'min_pulse'
servo = AngularServo(23, min_pulse_width=0.0005, max_pulse_width=0.0024)

print("Testing Servo...")

try:
    while True:
        print("Moving to -90")
        servo.angle = -90
        sleep(1)
        
        # print("Moving to 0")
        # servo.angle = 0
        # sleep(3)
        
        print("Moving to 90")
        servo.angle = 90
        sleep(1)

except KeyboardInterrupt:
    print("Stopping")